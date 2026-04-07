"""フレッシュマート食品スーパー AI エージェント。

LangGraph ベースの会話エージェントで、以下の機能を提供します：
  - 構造化データクエリ（Genie MCP 経由）— 商品・顧客・取引・店舗情報の検索
  - ポリシー文書検索（DatabricksVectorSearch ネイティブ）— 返品・会員・配送等のポリシー検索
  - コード実行（Code Interpreter MCP 経由）— Python による計算・分析
  - 長期記憶（Lakebase）— ユーザーの好み・タスク履歴・会話サマリーの永続化
  - 短期記憶（Lakebase AsyncCheckpointSaver）— スレッド内の会話ステートの永続化

Vector Search に DatabricksVectorSearch（ネイティブ実装）を使用している理由：
  MCP 経由で Vector Search を呼ぶと MLflow のスパンタイプが TOOL になるが、
  DatabricksVectorSearch + as_retriever() を使うと RETRIEVER スパンが自動生成される。
  これにより MLflow の RetrievalSufficiency スコアラーによる検索品質の評価が可能になる。
  Genie と Code Interpreter は RETRIEVER スパンが不要なため MCP のまま。

ツール一覧：
  - policy_search（async）— DatabricksVectorSearch で店舗ポリシーを検索
  - get_current_time — 現在日時を取得
  - memory_tools（7つ）— ユーザーメモリ・タスク・会話サマリーの保存/検索/削除
  - Genie MCP — 構造化データへの自然言語クエリ
  - Code Interpreter MCP — Python コード実行
"""

import json
import logging
import os
import subprocess
from datetime import datetime
from typing import Any, AsyncGenerator, Optional, Sequence, TypedDict

import mlflow
from databricks.sdk import WorkspaceClient
from databricks_langchain import (
    AsyncCheckpointSaver,
    AsyncDatabricksStore,
    ChatDatabricks,
    DatabricksMCPServer,
    DatabricksMultiServerMCPClient,
    DatabricksVectorSearch,
)
from fastapi import HTTPException
from langchain.agents import create_agent
from langchain_core.messages import AnyMessage
from langchain_core.tools import tool
from langgraph.graph.message import add_messages
from langgraph.store.base import BaseStore
from mlflow.genai.agent_server import invoke, stream
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
    to_chat_completions_input,
)
from typing_extensions import Annotated

from agent_server.utils import (
    _get_or_create_thread_id,
    get_databricks_host_from_env,
    get_session_id,
    get_user_workspace_client,
    process_agent_astream_events,
)
from agent_server.utils_memory import (
    get_lakebase_access_error_message,
    get_user_id,
    memory_tools,
    resolve_lakebase_instance_name,
)

logger = logging.getLogger(__name__)
logging.getLogger("mlflow.utils.autologging_utils").setLevel(logging.ERROR)
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
mlflow.langchain.autolog(run_tracer_inline=True)

# トレース送信先の切り替え
# MLFLOW_TRACING_DESTINATION が設定されていれば Unity Catalog Delta Table に送信
# 未設定（デフォルト）の場合は MLflow Experiment に記録
_tracing_dest = os.getenv("MLFLOW_TRACING_DESTINATION", "")
if _tracing_dest and "." in _tracing_dest:
    from mlflow.entities import UCSchemaLocation
    _catalog, _schema = _tracing_dest.split(".", 1)
    mlflow.tracing.set_destination(UCSchemaLocation(catalog_name=_catalog, schema_name=_schema))
    logger.info(f"Tracing destination: Unity Catalog ({_tracing_dest})")
else:
    logger.info("Tracing destination: MLflow Experiment (default)")

sp_workspace_client = WorkspaceClient()


@tool
def get_current_time() -> str:
    """Get the current date and time."""
    return datetime.now().isoformat()


############################################
# Configuration（agent.py と同一）
############################################
LLM_ENDPOINT_NAME = "databricks-claude-sonnet-4-5"
_LAKEBASE_INSTANCE_NAME_RAW = os.getenv("LAKEBASE_INSTANCE_NAME") or None
EMBEDDING_ENDPOINT = "databricks-gte-large-en"
EMBEDDING_DIMS = 1024
LAKEBASE_AUTOSCALING_PROJECT = os.getenv("LAKEBASE_AUTOSCALING_PROJECT") or None
LAKEBASE_AUTOSCALING_BRANCH = os.getenv("LAKEBASE_AUTOSCALING_BRANCH") or None

GENIE_SPACE_ID = os.getenv("GENIE_SPACE_ID", "")
PROMPT_REGISTRY_NAME = os.getenv("PROMPT_REGISTRY_NAME", "")

_VECTOR_SEARCH_INDEX_RAW = os.getenv("VECTOR_SEARCH_INDEX", "")
# MCP 用（スラッシュ形式）— Genie と Code Interpreter で使用
VECTOR_SEARCH_INDEX_MCP = (
    _VECTOR_SEARCH_INDEX_RAW.replace(".", "/")
    if "." in _VECTOR_SEARCH_INDEX_RAW and "/" not in _VECTOR_SEARCH_INDEX_RAW
    else _VECTOR_SEARCH_INDEX_RAW
)
# ネイティブ用（ドット形式）— DatabricksVectorSearch で使用
VECTOR_SEARCH_INDEX_NATIVE = _VECTOR_SEARCH_INDEX_RAW
############################################

_has_autoscaling = LAKEBASE_AUTOSCALING_PROJECT and LAKEBASE_AUTOSCALING_BRANCH
if not _LAKEBASE_INSTANCE_NAME_RAW and not _has_autoscaling:
    raise ValueError(
        "Lakebase configuration is required but not set. "
        "Please set one of the following in your environment:\n"
        "  Option 1 (provisioned): LAKEBASE_INSTANCE_NAME=<your-instance-name>\n"
        "  Option 2 (autoscaling): LAKEBASE_AUTOSCALING_PROJECT=<project> and LAKEBASE_AUTOSCALING_BRANCH=<branch>\n"
    )

LAKEBASE_INSTANCE_NAME = resolve_lakebase_instance_name(_LAKEBASE_INSTANCE_NAME_RAW) if _LAKEBASE_INSTANCE_NAME_RAW else None


class StatefulAgentState(TypedDict, total=False):
    messages: Annotated[Sequence[AnyMessage], add_messages]
    custom_inputs: dict[str, Any]
    custom_outputs: dict[str, Any]


# ── システムプロンプト ─────────────────────────────────────────────────
# PROMPT_REGISTRY_NAME は上部の Configuration セクション（84行目付近）で定義済み

SYSTEM_PROMPT = """あなたはフレッシュマートの親切で知識豊富なお買い物アシスタントです。お客様の食料品のお買い物をサポートし、商品や購入履歴に関するご質問にお答えし、店舗のポリシーについてご案内するのがあなたの役割です。お客様とは日本語で会話してください。

## あなたの機能

### 構造化データクエリ（Genie ツール経由）
以下のリアルタイム情報を検索できます：
- **お客様アカウント：** 会員ランク、購入履歴、お好み
- **商品：** 価格、在庫状況、カテゴリ、売り場
- **取引：** 過去の注文、支払い方法、注文ステータス
- **店舗：** 所在地、営業時間、連絡先
- **支払い履歴：** 登録済みの支払い方法

お客様が購入履歴、アカウント情報、商品の在庫、取引履歴について質問された場合は、Genie ツールを使ってデータを検索してください。クエリはできるだけ具体的に——お客様ID、商品名、日付範囲などを含めてください。

### ポリシー・手続きの検索（Vector Search ツール経由）
以下の店舗ポリシー文書を検索できます：
- **返品・返金** — 返品期限、生鮮食品のルール、レシートなし返品
- **会員・ポイントプログラム** — ランク特典（Bronze/Silver/Gold/Platinum）、ポイント、リワード
- **配送・受け取り** — 当日配送、店頭受取、ランク別配送料
- **商品の安全性・リコール** — 現在のリコール情報、リコール商品の返品方法
- **プライバシーポリシー** — 個人情報の収集、オプトアウト、データ削除
- **カスタマーサービス** — 問い合わせ窓口、エスカレーション、対応時間
- **店舗運営** — 営業時間、祝日営業、価格保証、支払い方法

お客様がポリシーについて質問された場合は、Vector Search ツールで該当するポリシーの詳細を検索してください。曖昧に答えるのではなく、具体的な数字（返品期限、料金、ポイント数など）を引用してお答えください。

### メモリ（長期記憶）
会話をまたいでお客様の情報を記憶できます：
- **get_user_memory** を使って、以前保存したお好み、食事制限、その他の個人的な情報を呼び出す
- **save_user_memory** を使って、お客様が共有した情報を記憶する（例：「ベジタリアンです」「オーガニック商品が好きです」「いつも渋谷店を使っています」）
- **delete_user_memory** を使って、お客様が忘れてほしいと言った情報を削除する

会話の最初に関連する記憶がないか確認し、パーソナライズされた応答を心がけてください。

### タスク・会話サマリー（長期記憶）
対応したタスクや会話の内容も記憶できます：

**タスクサマリー** — 個別のタスクを完了した後（例：商品に関する質問への回答、注文の検索、ポリシーの説明）：
- **save_task_summary** をサイレントに呼び出し（お客様には言及しない）、簡潔なタイトルと完了した内容のサマリーを保存する
- 何を「完了タスク」とするかはあなたの判断に任せます——質問への回答、問題の解決、おすすめの提示など

**会話サマリー** — お客様が会話の終了を示した場合（例：「ありがとう」「それで全部です」「また来ます」「さようなら」）：
- お別れの返答の前に **save_conversation_summary** をサイレントに呼び出し、会話全体のサマリーと話題のリストを保存する
- お客様にはこの保存について言及しない

**過去の履歴検索** — クエリに応じて適切なツールを選択：
- お好みや個人情報に関する質問（例：「私の好みは？」「アレルギーあったっけ？」）→ **get_user_memory**
- 過去の特定タスクに関する質問（例：「前回何を調べてもらった？」「返品について聞いたことある？」）→ **search_task_history**
- 会話履歴全般に関する質問（例：「今まで何を話した？」「過去のやり取りをまとめて」）→ **search_past_conversations**
- どちらに該当するか不明な場合は、**search_task_history** と **search_past_conversations** の両方を検索

## ガイドライン
- 温かく、親切で、会話を楽しめるトーンで——あなたはフレンドリーなお買い物アシスタントです
- 商品をおすすめする際は、お客様の食事の好みや過去の購入履歴を考慮してください
- 注文、返品、返金の手続きについて聞かれた場合は、手順をご説明しつつ、実際の手続きは店頭、アプリ、またはカスタマーサービスで行う必要があることをお伝えください
- 在庫切れの商品について聞かれた場合は、商品データを確認し、同じカテゴリの代替商品をご提案ください
- 該当する場合は、ポイントプログラムの特典を積極的にお伝えください（例：「Gold会員のお客様は、¥5,000以上のご注文で配送料が無料になります！」）
- 回答に十分な情報がない場合は、推測せずに確認のご質問をしてください"""


def load_system_prompt() -> str:
    """Prompt Registry が設定されていればそこから読み込み、なければハードコード版を使う。"""
    if PROMPT_REGISTRY_NAME:
        prompt = mlflow.genai.load_prompt(f"prompts:/{PROMPT_REGISTRY_NAME}@production")
        return prompt.format()
    return SYSTEM_PROMPT


# ── Vector Search ネイティブリトリーバー ──────────────────────────────
# DatabricksVectorSearch を使うことで、MLflow が RETRIEVER スパンを自動生成する。
# これが agent.py（MCP 版）との唯一の違い。

# 認証トークンを取得（VectorSearchClient が必要とする）
_headers = sp_workspace_client.config.authenticate()
_token = _headers.get("Authorization", "").replace("Bearer ", "")
if not _token:
    _result = subprocess.run(
        ["databricks", "auth", "token", "--profile",
         os.getenv("DATABRICKS_CONFIG_PROFILE", "DEFAULT"), "-o", "json"],
        capture_output=True, text=True,
    )
    _token = json.loads(_result.stdout)["access_token"]

_vector_store = DatabricksVectorSearch(
    index_name=VECTOR_SEARCH_INDEX_NATIVE,
    columns=["chunk_id", "doc_name", "content"],
    client_args={
        "workspace_url": sp_workspace_client.config.host,
        "personal_access_token": _token,
        "disable_notice": True,
    },
)
_retriever = _vector_store.as_retriever(search_kwargs={"k": 5})


@tool
async def policy_search(query: str) -> str:
    """フレッシュマートのポリシー文書を検索します。
    返品・配送・会員制度・リコール・プライバシー・カスタマーサービス・店舗運営に
    関する質問に回答するために使用してください。"""
    docs = await _retriever.ainvoke(query)
    if not docs:
        return "関連するポリシー情報が見つかりませんでした。"
    results = []
    for doc in docs:
        doc_name = doc.metadata.get("doc_name", "不明")
        results.append(f"【{doc_name}】\n{doc.page_content}")
    return "\n\n---\n\n".join(results)


# ── MCP クライアント（Genie + Code Interpreter のみ）─────────────────
# Vector Search は上記のネイティブ policy_search ツールに置き換え済み
def init_mcp_client(workspace_client: WorkspaceClient) -> DatabricksMultiServerMCPClient:
    host_name = get_databricks_host_from_env()
    return DatabricksMultiServerMCPClient(
        [
            DatabricksMCPServer(
                name="system-ai",
                url=f"{host_name}/api/2.0/mcp/functions/system/ai",
                workspace_client=workspace_client,
            ),
            DatabricksMCPServer(
                name="retail-grocery-genie",
                url=f"{host_name}/api/2.0/mcp/genie/{GENIE_SPACE_ID}",
                workspace_client=workspace_client,
            ),
            # Vector Search は MCP から除外 → policy_search ツール（ネイティブ）に置き換え
        ]
    )


async def init_agent(
    store: BaseStore,
    workspace_client: Optional[WorkspaceClient] = None,
    checkpointer: Optional[Any] = None,
):
    mcp_client = init_mcp_client(workspace_client or sp_workspace_client)
    # MCP ツール（Genie + Code Interpreter）+ ネイティブ policy_search + メモリ + 時刻
    tools = [get_current_time, policy_search] + memory_tools() + await mcp_client.get_tools()

    return create_agent(
        model=ChatDatabricks(endpoint=LLM_ENDPOINT_NAME),
        tools=tools,
        system_prompt=load_system_prompt(),
        store=store,
        checkpointer=checkpointer,
        state_schema=StatefulAgentState,
    )


# ── ハンドラー（agent.py と同一）────────────────────────────────────
@invoke()
async def invoke_handler(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    thread_id = _get_or_create_thread_id(request)
    request.custom_inputs = dict(request.custom_inputs or {})
    request.custom_inputs["thread_id"] = thread_id

    outputs = [
        event.item
        async for event in stream_handler(request)
        if event.type == "response.output_item.done"
    ]

    user_id = get_user_id(request)
    custom_outputs = {"thread_id": thread_id}
    if user_id:
        custom_outputs["user_id"] = user_id
    return ResponsesAgentResponse(output=outputs, custom_outputs=custom_outputs)


@stream()
async def stream_handler(
    request: ResponsesAgentRequest,
) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    thread_id = _get_or_create_thread_id(request)
    if session_id := get_session_id(request):
        mlflow.update_current_trace(metadata={"mlflow.trace.session": session_id})
    mlflow.update_current_trace(metadata={"mlflow.trace.session": thread_id})

    user_id = get_user_id(request)

    if not user_id:
        logger.warning("No user_id provided - memory features will not be available")

    input_state: dict[str, Any] = {
        "messages": to_chat_completions_input([i.model_dump() for i in request.input]),
        "custom_inputs": dict(request.custom_inputs or {}),
    }

    try:
        async with AsyncCheckpointSaver(
            instance_name=LAKEBASE_INSTANCE_NAME,
            project=LAKEBASE_AUTOSCALING_PROJECT,
            branch=LAKEBASE_AUTOSCALING_BRANCH,
        ) as checkpointer:
            async with AsyncDatabricksStore(
                instance_name=LAKEBASE_INSTANCE_NAME,
                project=LAKEBASE_AUTOSCALING_PROJECT,
                branch=LAKEBASE_AUTOSCALING_BRANCH,
                embedding_endpoint=EMBEDDING_ENDPOINT,
                embedding_dims=EMBEDDING_DIMS,
            ) as store:
                await store.setup()
                config: dict[str, Any] = {"configurable": {"thread_id": thread_id, "store": store}}
                if user_id:
                    config["configurable"]["user_id"] = user_id

                agent = await init_agent(
                    workspace_client=sp_workspace_client,
                    store=store,
                    checkpointer=checkpointer,
                )
                async for event in process_agent_astream_events(
                    agent.astream(input_state, config, stream_mode=["updates", "messages"])
                ):
                    yield event
    except Exception as e:
        error_msg = str(e).lower()
        if any(keyword in error_msg for keyword in ["permission"]):
            logger.error(f"Lakebase access error: {e}")
            lakebase_desc = LAKEBASE_INSTANCE_NAME or f"{LAKEBASE_AUTOSCALING_PROJECT}/{LAKEBASE_AUTOSCALING_BRANCH}"
            raise HTTPException(
                status_code=503, detail=get_lakebase_access_error_message(lakebase_desc)
            ) from e
        raise
