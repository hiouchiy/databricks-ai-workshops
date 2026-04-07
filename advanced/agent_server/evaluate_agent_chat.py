"""RAG ベースの評価データセット + MCP/ネイティブ切り替え対応エージェント評価スクリプト。

コマンドライン引数 --mode で MCP 版とネイティブ VS 版を切り替えて評価する。

モード:
  native (デフォルト):
    - Vector Search のみネイティブ（DatabricksVectorSearch）、Genie は MCP
    - RETRIEVER スパンが自動生成 → RetrievalSufficiency 評価可能
    - Lakebase なし、直接呼び出し（サーバー不要）

  mcp:
    - 全ツール MCP（Vector Search + Genie + Code Interpreter）+ Lakebase メモリ
    - RETRIEVER スパンなし → RetrievalSufficiency は除外
    - サーバー経由（`uv run start-server` で事前起動が必要）
    - Lakebase の async pool と mlflow.genai.evaluate のデッドロック回避のため

使い方:
    uv run agent-evaluate-chat                # ネイティブ版（デフォルト）
    uv run agent-evaluate-chat --mode native  # 同上
    uv run agent-evaluate-chat --mode mcp     # MCP 版（要サーバー起動）

参照:
    https://docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/build-eval-dataset
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess

import mlflow
from databricks.sdk import WorkspaceClient
from databricks_langchain import (
    ChatDatabricks,
    DatabricksMCPServer,
    DatabricksMultiServerMCPClient,
    DatabricksVectorSearch,
)
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AnyMessage
from langchain_core.tools import tool
from langgraph.graph.message import add_messages
from mlflow.genai.scorers import (
    Correctness,
    Fluency,
    RelevanceToQuery,
    RetrievalSufficiency,
    Safety,
)
from typing import Annotated
from typing_extensions import TypedDict

# .envファイルが存在する場合、環境変数を読み込む
load_dotenv(dotenv_path=".env", override=True)

# 評価用 Experiment に切り替え（モニタリング用と分離するため）
_eval_exp_id = os.environ.get("MLFLOW_EVAL_EXPERIMENT_ID")
if _eval_exp_id:
    os.environ["MLFLOW_EXPERIMENT_ID"] = _eval_exp_id

logging.getLogger("mlflow.utils.autologging_utils").setLevel(logging.ERROR)

# 逐次実行（デッドロック回避）
os.environ["MLFLOW_GENAI_EVAL_SKIP_TRACE_VALIDATION"] = "true"
os.environ["MLFLOW_GENAI_EVAL_MAX_WORKERS"] = "1"

from agent_server.utils import get_databricks_host_from_env  # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# 共通: システムプロンプト（agent.py と同一のフル版）
# ──────────────────────────────────────────────────────────────────────
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


# ──────────────────────────────────────────────────────────────────────
# 共通: 評価データセット
# ──────────────────────────────────────────────────────────────────────

simple_questions = [
    {
        "inputs": {"query": "生鮮食品の返品期限は何時間ですか？"},
        "expectations": {
            "expected_facts": [
                "生鮮食品の返品期限は購入日より48時間以内",
                "青果・乳製品・精肉・ベーカリー・惣菜が対象",
                "品質に不満がある場合は商品の状態を問わず返品可能",
            ],
        },
    },
    {
        "inputs": {"query": "Gold会員の配送料無料の条件を教えてください。"},
        "expectations": {
            "expected_facts": [
                "Gold会員は¥5,000以上のご注文で配送料無料",
                "通常の配送料は¥400",
            ],
        },
    },
    {
        "inputs": {"query": "フレッシュマートの営業時間を教えてください。"},
        "expectations": {
            "expected_facts": [
                "通常営業は9:00～22:00",
                "日曜・祝日は9:00～21:00",
            ],
        },
    },
]

complex_questions = [
    {
        "inputs": {"query": "Silver会員です。冷凍食品が冷凍焼けしていたので返品したいのですが、レシートをなくしました。返品できますか？また、配送で届いた商品の場合はどうすればいいですか？"},
        "expectations": {
            "expected_facts": [
                "冷凍食品の返品期限は購入日より30日以内",
                "冷凍焼けや包装の破損など品質上の問題が確認できることが条件",
                "¥1,500を超える返金にはレシートが必要",
                "レシートがない場合はポイントカードの履歴で確認可能な場合がある",
                "配送注文の場合はカスタマーサポートに連絡すれば返品不要で返金される",
            ],
        },
    },
    {
        "inputs": {"query": "Platinum会員の特典をすべて教えてください。ポイント付与率、配送、年間特典、カスタマーサービスの優遇も含めて詳しく知りたいです。"},
        "expectations": {
            "expected_facts": [
                "ポイント付与率は¥100につき3ポイント",
                "全注文で配送料無料（金額制限なし）",
                "プライベートブランド商品15%オフ",
                "年間特典として¥5,000分のギフトカード",
                "Platinum専用カスタマーサービスダイヤルがある",
                "パーソナルショッパーサービス（月2回まで）",
            ],
        },
    },
    {
        "inputs": {"query": "現在リコールされている商品はありますか？もし対象商品を食べてしまった場合、どうすればいいですか？返金方法も教えてください。"},
        "expectations": {
            "expected_facts": [
                "サンブライト有機ベビーほうれん草が大腸菌汚染の可能性でリコール中",
                "はっぴーファーム とろけるチーズが大豆アレルゲン表示漏れでリコール中",
                "クランチタイム ピーナッツバタークラッカーが乳アレルゲン表示漏れでリコール中",
                "摂取してしまった場合は直ちに使用を中止し医療機関に相談",
                "リコール商品は購入時期に関わらず全額返金",
                "レシート不要でポイントカードの履歴で確認可能",
            ],
        },
    },
]

out_of_scope_questions = [
    {
        "inputs": {"query": "フレッシュマートの株価は今いくらですか？来期の業績予想も教えてください。"},
        "expectations": {
            "expected_facts": [
                "株価や業績予想に関する情報は提供できない、または対応範囲外であることを伝える",
                "推測や虚偽の情報を提供しない",
            ],
        },
    },
    {
        "inputs": {"query": "隣のスーパーマーケット「ライフ」の今週の特売情報を教えてください。"},
        "expectations": {
            "expected_facts": [
                "他社の特売情報は提供できないことを伝える",
                "フレッシュマートの商品やサービスについてであれば案内できることを伝える",
            ],
        },
    },
    {
        "inputs": {"query": "この前買った牛肉を使ったレシピを5つ教えてください。調理時間と材料も詳しくお願いします。"},
        "expectations": {
            "expected_facts": [
                "詳細なレシピの提供はエージェントの主な機能ではないことを示唆する",
                "商品検索や店舗情報などフレッシュマートに関する案内であれば対応可能であることを伝える",
            ],
        },
    },
]

eval_data = simple_questions + complex_questions + out_of_scope_questions


# ──────────────────────────────────────────────────────────────────────
# Native モード: LangGraph + ネイティブ VectorSearch（直接呼び出し）
# ──────────────────────────────────────────────────────────────────────

class SimpleEvalState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def _create_native_agent():
    """ネイティブ VS + MCP Genie の LangGraph エージェントを作成する（Lakebase なし）。"""
    from datetime import datetime

    ws = WorkspaceClient()
    host_name = get_databricks_host_from_env()

    LLM_ENDPOINT_NAME = "databricks-claude-sonnet-4-5"
    GENIE_SPACE_ID = os.getenv("GENIE_SPACE_ID", "")
    VECTOR_SEARCH_INDEX = os.getenv("VECTOR_SEARCH_INDEX", "")

    # 認証トークン取得
    _headers = ws.config.authenticate()
    _token = _headers.get("Authorization", "").replace("Bearer ", "")
    if not _token:
        _result = subprocess.run(
            ["databricks", "auth", "token", "--profile",
             os.getenv("DATABRICKS_CONFIG_PROFILE", "DEFAULT"), "-o", "json"],
            capture_output=True, text=True,
        )
        _token = json.loads(_result.stdout)["access_token"]

    # ネイティブ Vector Search（RETRIEVER スパン自動生成）
    _vector_store = DatabricksVectorSearch(
        index_name=VECTOR_SEARCH_INDEX,
        columns=["chunk_id", "doc_name", "content"],
        client_args={
            "workspace_url": ws.config.host,
            "personal_access_token": _token,
            "disable_notice": True,
        },
    )
    _retriever = _vector_store.as_retriever(search_kwargs={"k": 5})

    @tool
    def policy_search(query: str) -> str:
        """フレッシュマートのポリシー文書を検索します。"""
        docs = _retriever.invoke(query)
        if not docs:
            return "関連するポリシー情報が見つかりませんでした。"
        results = []
        for doc in docs:
            doc_name = doc.metadata.get("doc_name", "不明")
            results.append(f"【{doc_name}】\n{doc.page_content}")
        return "\n\n---\n\n".join(results)

    @tool
    def get_current_time() -> str:
        """Get the current date and time."""
        return datetime.now().isoformat()

    # MCP ツール（Genie + Code Interpreter）
    mcp_client = DatabricksMultiServerMCPClient(
        [
            DatabricksMCPServer(
                name="system-ai",
                url=f"{host_name}/api/2.0/mcp/functions/system/ai",
                workspace_client=ws,
            ),
            DatabricksMCPServer(
                name="retail-grocery-genie",
                url=f"{host_name}/api/2.0/mcp/genie/{GENIE_SPACE_ID}",
                workspace_client=ws,
            ),
        ]
    )
    loop = asyncio.new_event_loop()
    mcp_tools = loop.run_until_complete(mcp_client.get_tools())
    loop.close()

    all_tools = [get_current_time, policy_search] + mcp_tools
    llm = ChatDatabricks(endpoint=LLM_ENDPOINT_NAME)

    return create_agent(
        model=llm,
        tools=all_tools,
        system_prompt=SYSTEM_PROMPT,
        state_schema=SimpleEvalState,
    )


def _native_predict(query: str) -> str:
    """ネイティブ版エージェントを直接呼び出す。"""
    result = _native_agent.invoke(
        {"messages": [{"role": "user", "content": query}]}
    )
    for msg in reversed(result["messages"]):
        if hasattr(msg, "content") and msg.content:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                continue
            if isinstance(msg.content, str) and len(msg.content) > 0:
                return msg.content
    return str(result)


# ──────────────────────────────────────────────────────────────────────
# MCP モード: サーバー経由で agent_mcp.py（または agent.py）を呼び出す
# ──────────────────────────────────────────────────────────────────────
# Lakebase の async pool が evaluate プロセスのイベントループとデッドロックするため、
# MCP + Lakebase のエージェントは別プロセスのサーバーとして起動し、HTTP 経由で呼ぶ。
# サーバーは `uv run start-server` で事前に起動しておく必要がある。
#
# @mlflow.trace により evaluate プロセス内でトレースが生成されるため、
# expected_facts の紐付けも正常に動作する。

import json
import urllib.request
import urllib.error

AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8000/invocations")


@mlflow.trace
def _mcp_predict(query: str) -> str:
    """MCP 版エージェントサーバーに HTTP 経由で質問を送る。

    前提: `uv run start-server` で localhost:8000 にサーバーが起動していること。
    @mlflow.trace により、evaluate プロセス内でトレースが生成される。
    """
    payload = json.dumps({
        "input": [{"role": "user", "content": query}],
    }).encode("utf-8")

    req = urllib.request.Request(
        AGENT_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return f"エラー: HTTP {e.code}"
    except Exception as e:
        return f"エラー: {e}"

    for item in data.get("output", []):
        if item.get("type") == "message" and item.get("role") == "assistant":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content.get("text", "")
    return json.dumps(data, ensure_ascii=False)[:500]


# ──────────────────────────────────────────────────────────────────────
# 評価実行
# ──────────────────────────────────────────────────────────────────────

# エージェントは evaluate() 内で遅延初期化
_native_agent = None


def evaluate():
    """コマンドライン引数に応じてモードを切り替えて評価を実行する。"""
    global _native_agent

    parser = argparse.ArgumentParser(description="RAG ベースのエージェント評価")
    parser.add_argument(
        "--mode",
        choices=["native", "mcp"],
        default="native",
        help="評価モード: native（ネイティブ VS、デフォルト）/ mcp（MCP 版、要サーバー起動）",
    )
    args = parser.parse_args()
    mode = args.mode

    # モードに応じた設定
    if mode == "native":
        print("モード: native（ネイティブ VectorSearch + MCP Genie、直接呼び出し）")
        _native_agent = _create_native_agent()
        predict_fn = _native_predict
        scorers = [Correctness(), RelevanceToQuery(), RetrievalSufficiency(), Safety(), Fluency()]
    else:
        print("モード: mcp（サーバー経由）")
        print(f"  サーバー URL: {AGENT_URL}")
        print("  ※ 事前に `uv run start-server` でサーバーを起動してください")
        predict_fn = _mcp_predict
        # MCP 版は RETRIEVER スパンがないため RetrievalSufficiency を除外
        scorers = [Correctness(), RelevanceToQuery(), Safety(), Fluency()]

    # 事前チェック
    print()
    print("=" * 60)
    print("事前チェック: エージェントの動作確認")
    print("=" * 60)
    test_query = simple_questions[0]["inputs"]["query"]
    print(f"  質問: {test_query}")
    try:
        test_response = predict_fn(test_query)
        if not test_response or len(test_response) < 10:
            print(f"  ❌ レスポンスが短すぎます: {test_response}")
            return
        print(f"  ✅ 正常レスポンス（先頭100文字）: {test_response[:100]}...")
    except Exception as e:
        print(f"  ❌ 例外発生: {e}")
        import traceback
        traceback.print_exc()
        print("\n  ヒント: .env の設定と Databricks CLI の認証を確認してください。")
        return

    # 評価実行
    print()
    print("=" * 60)
    print(f"RAG ベース評価を開始します（{mode} モード）")
    print(f"  シンプルな質問: {len(simple_questions)} 件")
    print(f"  複雑な質問:     {len(complex_questions)} 件")
    print(f"  スコープ外:     {len(out_of_scope_questions)} 件")
    print(f"  合計:           {len(eval_data)} 件")
    print(f"  スコアラー:     {', '.join(type(s).__name__ for s in scorers)}")
    print("=" * 60)

    results = mlflow.genai.evaluate(
        data=eval_data,
        predict_fn=predict_fn,
        scorers=scorers,
    )

    # 結果サマリー
    print("\n" + "=" * 60)
    print(f"評価結果サマリー（{mode} モード）")
    print("=" * 60)
    if hasattr(results, "metrics") and results.metrics:
        for metric_name, metric_value in results.metrics.items():
            print(f"  {metric_name}: {metric_value}")

    print(f"\n✅ 評価完了！MLflow Experiments UI で詳細を確認してください。")
