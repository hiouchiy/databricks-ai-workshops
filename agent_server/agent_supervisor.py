"""フレッシュマート食品スーパー AI エージェント（Supervisor API 版）。

`agent.py`（LangGraph 版）のミニマル対比実装。エージェントループを Databricks
Supervisor API に任せる形なので、LangGraph の checkpointer / store / MCP client /
tool binding などが不要になり、コード量が大幅に減っている。

差分（LangGraph 版 vs Supervisor 版）：
  - Genie / Vector Search は Supervisor 組み込みツールとして宣言するだけ。
    tool_call/tool_result の往復はサーバー側で完結する。
  - 長期メモリ（Lakebase 由来）は無し。
  - 短期記憶（thread state / checkpointer）は無し。会話履歴は毎ターン
    クライアントが input として丸ごと送る想定。
  - LLM モデルは Supervisor が対応するモデル名を使う（例：
    `databricks-claude-sonnet-4-6`）。Gateway 用の `system.ai.*` 名は不可。

参考: https://docs.databricks.com/aws/ja/generative-ai/agent-bricks/supervisor-api
"""

import logging
import os
from typing import Any, AsyncGenerator

import mlflow
from databricks.sdk import WorkspaceClient
from mlflow.genai.agent_server import invoke, stream
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
)
from openai import OpenAI

logger = logging.getLogger(__name__)
logging.getLogger("mlflow.utils.autologging_utils").setLevel(logging.ERROR)
mlflow.openai.autolog()

############################################
# Configuration
############################################
# Supervisor API が対応するモデル名（Foundation Model API の serving endpoint 名形式）。
# system.ai.* 系ではないので注意。
LLM_MODEL = os.getenv("LLM_MODEL_SUPERVISOR", "databricks-claude-sonnet-4-6")
GENIE_SPACE_ID = os.getenv("GENIE_SPACE_ID", "")
VECTOR_SEARCH_INDEX = os.getenv("VECTOR_SEARCH_INDEX", "")
MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "2048"))

SYSTEM_PROMPT = """あなたはフレッシュマートの親切で知識豊富なお買い物アシスタントです。お客様の食料品のお買い物をサポートし、商品や購入履歴、店舗ポリシーに関するご質問にお答えするのがあなたの役割です。日本語で会話してください。

## 使えるツール
- **retail_grocery（Genie）** — 商品・顧客・取引・店舗のリアルタイムデータを自然言語で検索
- **policy_docs（Vector Search）** — 返品・会員・配送・リコール・プライバシー等の店舗ポリシー文書を検索

## ガイドライン
- 商品や購入履歴について聞かれたら retail_grocery ツールを使う
- 店舗ポリシー・返品・会員制度などについて聞かれたら policy_docs ツールを使う
- 温かく、親切で、会話を楽しめるトーンで
- 具体的な数字（返品期限、料金、ポイント数など）は必ずポリシー文書から引用する
"""

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


def _build_tools() -> list[dict]:
    """Supervisor 用のツール定義を組み立てる。GENIE_SPACE_ID や
    VECTOR_SEARCH_INDEX が未設定の場合は該当ツールを外す。"""
    tools = []
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
    return tools


def _request_to_input(request: ResponsesAgentRequest) -> list[dict]:
    """ResponsesAgentRequest.input → Responses API input 形式に変換。
    先頭にシステムプロンプトを挿入する（システムメッセージが未挿入なら）。"""
    items = [i.model_dump(exclude_none=True) for i in request.input]
    # 先頭に system プロンプトが無ければ追加
    first_role = items[0].get("role") if items else None
    if first_role != "system":
        items = [{"role": "system", "content": SYSTEM_PROMPT}] + items
    return items


############################################
# Handlers
############################################
@invoke()
async def invoke_handler(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    tools = _build_tools()
    input_items = _request_to_input(request)

    response = _client.responses.create(
        model=LLM_MODEL,
        input=input_items,
        tools=tools if tools else None,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    # response.output は Responses API item のリスト（message / function_call /
    # function_call_output 等）で、MLflow AgentServer がそのまま扱える形。
    outputs: list[dict[str, Any]] = [
        item.model_dump(exclude_none=True) if hasattr(item, "model_dump") else dict(item)
        for item in (response.output or [])
    ]
    return ResponsesAgentResponse(output=outputs, custom_outputs={})


@stream()
async def stream_handler(
    request: ResponsesAgentRequest,
) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    tools = _build_tools()
    input_items = _request_to_input(request)

    stream_iter = _client.responses.create(
        model=LLM_MODEL,
        input=input_items,
        tools=tools if tools else None,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        stream=True,
    )
    for event in stream_iter:
        # OpenAI Responses API のストリームイベントは type + 任意の追加フィールドを
        # 持つ。ResponsesAgentStreamEvent は additionalProperties=True なので
        # そのまま **event.model_dump() でパススルーできる。
        payload = event.model_dump(exclude_none=True) if hasattr(event, "model_dump") else dict(event)
        yield ResponsesAgentStreamEvent(**payload)
