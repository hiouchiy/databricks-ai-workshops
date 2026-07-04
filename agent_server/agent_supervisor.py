"""フレッシュマート食品スーパー AI エージェント（Supervisor API 版）。

`agent.py`（LangGraph 版）のミニマル対比実装。エージェントループを Databricks
Supervisor API に任せる形なので、LangGraph の checkpointer / store / MCP client /
tool binding などが不要になり、コード量が大幅に減っている。

差分（LangGraph 版 vs Supervisor 版）：
  - Genie / Vector Search は Supervisor 組み込みツールとして宣言するだけ。
    tool_call/tool_result の往復はサーバー側で完結する。
  - **長期メモリ：Databricks Managed Memory（UC memory-store）**を使用。
    5 個の memory tool を Supervisor に function として declare し、client 側で
    UC の REST API を叩く（`DATABRICKS_MEMORY_STORE` env var が set され、
    リクエストの custom_inputs.user_id で scope が解決できた場合のみ有効化）。
  - 短期記憶（thread state）は無し。会話履歴は毎ターン client が丸ごと送る想定。
    Supervisor の `conversations` API は現時点で auto-continue しないため。
  - LLM モデルは Supervisor が対応するモデル名を使う（例：
    `system.ai.claude-sonnet-4-6`）。

参考:
  https://docs.databricks.com/aws/ja/generative-ai/agent-bricks/supervisor-api
  https://docs.databricks.com/aws/en/agents/agent-memory/managed-memory
"""

import logging
import os
from typing import Any, AsyncGenerator, Optional

import mlflow
from databricks.sdk import WorkspaceClient
from mlflow.genai.agent_server import invoke, stream
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
)
from openai import OpenAI

from agent_server import managed_memory
from agent_server.utils_memory import get_user_id

logger = logging.getLogger(__name__)
logging.getLogger("mlflow.utils.autologging_utils").setLevel(logging.ERROR)
mlflow.openai.autolog()

############################################
# Configuration
############################################
LLM_MODEL = os.getenv("LLM_MODEL_SERVICE_SUPERVISOR", "system.ai.claude-sonnet-4-6")
GENIE_SPACE_ID = os.getenv("GENIE_SPACE_ID", "")
VECTOR_SEARCH_INDEX = os.getenv("VECTOR_SEARCH_INDEX", "")
MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "2048"))

# client-side function-call loop の暴走防止（Supervisor が function_call を吐き続け
# たときに無限ループしないための保険）
MAX_TOOL_ITERATIONS = int(os.getenv("SUPERVISOR_MAX_TOOL_ITERATIONS", "8"))

_BASE_PROMPT = """あなたはフレッシュマートの親切で知識豊富なお買い物アシスタントです。お客様の食料品のお買い物をサポートし、商品や購入履歴、店舗ポリシーに関するご質問にお答えするのがあなたの役割です。日本語で会話してください。

## 使えるツール
- **retail_grocery（Genie）** — 商品・顧客・取引・店舗のリアルタイムデータを自然言語で検索
- **policy_docs（Vector Search）** — 返品・会員・配送・リコール・プライバシー等の店舗ポリシー文書を検索

## ガイドライン
- 商品や購入履歴について聞かれたら retail_grocery ツールを使う
- 店舗ポリシー・返品・会員制度などについて聞かれたら policy_docs ツールを使う
- 温かく、親切で、会話を楽しめるトーンで
- 具体的な数字（返品期限、料金、ポイント数など）は必ずポリシー文書から引用する
"""


def _build_system_prompt(memory_enabled: bool) -> str:
    if memory_enabled:
        return _BASE_PROMPT + "\n\n" + managed_memory.MEMORY_INSTRUCTIONS
    return _BASE_PROMPT


############################################
# Auth（agent.py と同じハイブリッドパターン）
############################################
sp_workspace_client = WorkspaceClient()
_auth_type = getattr(sp_workspace_client.config, "auth_type", "")
if _auth_type in ("oauth-m2m", "model_serving_user_credentials"):
    _token = sp_workspace_client.config.oauth_token().access_token
else:
    _headers = sp_workspace_client.config.authenticate()
    _token = _headers.get("Authorization", "").replace("Bearer ", "")
_host = sp_workspace_client.config.host

# Supervisor API は /ai-gateway/mlflow/v1/responses に居る。
# OpenAI SDK の Responses API を base_url 差し替えでそのまま使える。
_client = OpenAI(
    api_key=_token,
    base_url=f"{_host}/ai-gateway/mlflow/v1",
)


############################################
# Helpers
############################################
def _resolve_scope(request: ResponsesAgentRequest) -> Optional[str]:
    """Managed Memory の scope（誰の記憶か）を解決する。

    LangGraph 版の `get_user_id` を再利用して、`custom_inputs.user_id`
    または `context.user_id` から取得する。**未設定なら None を返し、
    memory tool 自体を declare しない**（fail-closed）。

    ⚠ Databricks Apps の production では、client-supplied な値ではなく
    forwarded OBO token（`X-Forwarded-Access-Token`）から `current_user.me().id`
    を取るのが本筋。本ワークショップではデモ簡便化のため client 側の user_id
    を使うが、実運用では forwarded token 経路への差し替えを推奨する。
    """
    user_id = get_user_id(request)
    if not user_id:
        return None
    user_id = user_id.strip()
    return user_id or None


def _build_tools(memory_enabled: bool) -> list[dict]:
    """Supervisor 用のツール定義を組み立てる。"""
    tools: list[dict] = []
    if GENIE_SPACE_ID:
        tools.append({
            "type": "genie_space",
            "name": "retail_grocery",
            "description": "商品・顧客・取引・店舗のリアルタイム情報を自然言語クエリで検索",
            "genie_space": {"space_id": GENIE_SPACE_ID},
        })
    if VECTOR_SEARCH_INDEX:
        tools.append({
            "type": "vector_search_index",
            "name": "policy_docs",
            "description": "返品・会員・配送・リコール・プライバシー等の店舗ポリシー文書を検索",
            "vector_search_index": {
                "name": VECTOR_SEARCH_INDEX,
                "columns": ["doc_name", "content"],
            },
        })
    if memory_enabled:
        tools.extend(managed_memory.MEMORY_TOOL_SCHEMAS)
    return tools


def _request_to_input(request: ResponsesAgentRequest, system_prompt: str) -> list[dict]:
    """ResponsesAgentRequest.input → Responses API input 形式に変換。
    先頭にシステムプロンプトを挿入する（システムメッセージが未挿入なら）。"""
    items = [i.model_dump(exclude_none=True) for i in request.input]
    first_role = items[0].get("role") if items else None
    if first_role != "system":
        items = [{"role": "system", "content": system_prompt}] + items
    return items


def _extract_memory_calls(output_items: list[Any]) -> list[Any]:
    """Supervisor が emit した function_call のうち memory tool 相当を抽出。
    server-side tools（Genie / VS）は Supervisor 内で完結するので出てこない。"""
    calls = []
    for item in output_items or []:
        item_type = getattr(item, "type", None)
        if item_type != "function_call":
            continue
        name = getattr(item, "name", None)
        if name in managed_memory.MEMORY_TOOL_NAMES:
            calls.append(item)
    return calls


def _item_to_dict(item: Any) -> dict:
    """OpenAI SDK の item を dict に。"""
    if hasattr(item, "model_dump"):
        return item.model_dump(exclude_none=True)
    if isinstance(item, dict):
        return dict(item)
    return {}


############################################
# Handlers
############################################
@invoke()
async def invoke_handler(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    scope = _resolve_scope(request)
    # Memory は env var 設定 + scope 解決の両方が必要
    memory_enabled = managed_memory.is_enabled() and scope is not None
    if managed_memory.is_enabled() and scope is None:
        logger.warning(
            "Managed memory is configured but scope (user_id) is missing; "
            "memory tools are not declared for this request."
        )

    tools = _build_tools(memory_enabled)
    system_prompt = _build_system_prompt(memory_enabled)
    input_items = _request_to_input(request, system_prompt)

    all_outputs: list[dict[str, Any]] = []

    for _iteration in range(MAX_TOOL_ITERATIONS):
        response = _client.responses.create(
            model=LLM_MODEL,
            input=input_items,
            tools=tools if tools else None,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        iter_items = list(response.output or [])

        # このイテレーションの出力を全部積む（message / server-side function_call /
        # server-side function_call_output / client-side function_call など）
        for item in iter_items:
            all_outputs.append(_item_to_dict(item))

        # client-side memory tool の function_call があれば実行して次イテへ。
        # なければ agent は最終回答を出したので終了。
        memory_calls = _extract_memory_calls(iter_items) if memory_enabled else []
        if not memory_calls:
            break

        # 次イテの input は「今までの全 items + このイテの output items +
        # 各 memory_call に対する function_call_output」。previous_response_id を
        # 使う手もあるが、input で送る方が context がクリアで挙動が読める。
        input_items.extend(_item_to_dict(i) for i in iter_items)
        for call in memory_calls:
            args = getattr(call, "arguments", "") or ""
            name = getattr(call, "name", "")
            call_id = getattr(call, "call_id", "")
            result = managed_memory.execute_tool(name, args, scope or "")
            fco = {
                "type": "function_call_output",
                "call_id": call_id,
                "output": result,
            }
            input_items.append(fco)
            all_outputs.append(fco)
    else:
        logger.warning(
            f"Supervisor client-side tool loop hit MAX_TOOL_ITERATIONS={MAX_TOOL_ITERATIONS}; "
            "returning partial output."
        )

    custom = {"user_id": scope} if scope else {}
    return ResponsesAgentResponse(output=all_outputs, custom_outputs=custom)


@stream()
async def stream_handler(
    request: ResponsesAgentRequest,
) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    scope = _resolve_scope(request)
    memory_enabled = managed_memory.is_enabled() and scope is not None
    if managed_memory.is_enabled() and scope is None:
        logger.warning(
            "Managed memory is configured but scope (user_id) is missing; "
            "memory tools are not declared for this stream."
        )

    tools = _build_tools(memory_enabled)
    system_prompt = _build_system_prompt(memory_enabled)
    input_items = _request_to_input(request, system_prompt)

    for _iteration in range(MAX_TOOL_ITERATIONS):
        stream_iter = _client.responses.create(
            model=LLM_MODEL,
            input=input_items,
            tools=tools if tools else None,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            stream=True,
        )

        iter_items: list[Any] = []  # このイテで完成した output items を蓄積

        for event in stream_iter:
            payload = event.model_dump(exclude_none=True) if hasattr(event, "model_dump") else dict(event)
            # OpenAI Responses API の完了イベントで output_item を拾う
            etype = payload.get("type", "")
            if etype == "response.output_item.done":
                item = payload.get("item")
                if item is not None:
                    iter_items.append(item)
            elif etype == "response.completed":
                # stream 完了時にレスポンス全体が入る場合の保険（output_item.done
                # が抜けたケースの補完）
                resp = payload.get("response") or {}
                if not iter_items and resp.get("output"):
                    iter_items.extend(resp["output"])
            # イベントは全て frontend に転送
            yield ResponsesAgentStreamEvent(**payload)

        # memory tool の function_call を実行
        memory_calls = (
            [i for i in iter_items
             if (i.get("type") if isinstance(i, dict) else getattr(i, "type", None)) == "function_call"
             and (i.get("name") if isinstance(i, dict) else getattr(i, "name", None)) in managed_memory.MEMORY_TOOL_NAMES]
            if memory_enabled else []
        )
        if not memory_calls:
            return

        # 次イテの input: これまでの input + 今回の iter items + 各 tool の output
        input_items.extend(iter_items if isinstance(iter_items[0], dict) else [_item_to_dict(i) for i in iter_items])
        for call in memory_calls:
            args_val = call.get("arguments") if isinstance(call, dict) else getattr(call, "arguments", "")
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
            call_id = call.get("call_id") if isinstance(call, dict) else getattr(call, "call_id", "")
            result = managed_memory.execute_tool(name, args_val or "", scope or "")
            fco = {
                "type": "function_call_output",
                "call_id": call_id,
                "output": result,
            }
            input_items.append(fco)
            # frontend にも tool result を可視化
            yield ResponsesAgentStreamEvent(type="response.output_item.done", item=fco)

    logger.warning(
        f"Supervisor client-side tool loop hit MAX_TOOL_ITERATIONS={MAX_TOOL_ITERATIONS}; stopping."
    )
