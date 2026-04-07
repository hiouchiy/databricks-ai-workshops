import asyncio
import logging
import os

import mlflow
from dotenv import load_dotenv
from mlflow.genai.agent_server import get_invoke_function
from mlflow.genai.scorers import (
    Completeness,
    ConversationalSafety,
    ConversationCompleteness,
    Fluency,
    KnowledgeRetention,
    RelevanceToQuery,
    Safety,
    ToolCallCorrectness,
    UserFrustration,
)

from mlflow.genai.simulators import ConversationSimulator
from mlflow.types.responses import ResponsesAgentRequest

# .envファイルが存在する場合、環境変数を読み込む
load_dotenv(dotenv_path=".env", override=True)

# 評価用 Experiment に切り替え（モニタリング用と分離するため）
_eval_exp_id = os.environ.get("MLFLOW_EVAL_EXPERIMENT_ID")
if _eval_exp_id:
    os.environ["MLFLOW_EXPERIMENT_ID"] = _eval_exp_id

# 評価時は Delta Table への送信を無効化
os.environ.pop("MLFLOW_TRACING_DESTINATION", None)

logging.getLogger("mlflow.utils.autologging_utils").setLevel(logging.ERROR)

# @invokeデコレータで登録された関数を見つけるために、agentモジュールをインポートする必要がある
from agent_server import agent  # noqa: F401

# 評価データセットを作成する
# 評価に関するドキュメント:
# スコアラー: https://docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/concepts/scorers
# 事前定義LLMスコアラー: https://mlflow.org/docs/latest/genai/eval-monitor/scorers/llm-judge/predefined
# カスタムスコアラーの定義: https://docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/custom-scorers
test_cases = [
    {
        "goal": "オーガニック青果の在庫と価格を確認する",
        "persona": "健康志向でオーガニック商品を好む、価格にも敏感なお客様。",
        "simulation_guidelines": [
            "青果コーナーにどんなオーガニック商品があるか聞く。",
            "通常商品とオーガニック商品の価格を比較してみる。",
            "短いメッセージで会話する。",
        ],
    },
    {
        "goal": "フレッシュマートの生鮮食品の返品・返金ポリシーを理解する",
        "persona": "昨日買った牛乳が傷んでいて、返金してほしいと困っているお客様。",
        "simulation_guidelines": [
            "傷んだ牛乳を購入した問題を説明する。",
            "返金を受けるための具体的な手順を聞く。",
            "生鮮食品の返品期限について確認する。",
        ],
    },
    {
        "goal": "4人家族の1週間分の買い物リストを予算内で計画する",
        "persona": "忙しい共働き家庭で、週¥15,000の食費予算でやりくりしたいお客様。",
        "simulation_guidelines": [
            "予算に合う定番商品のおすすめを聞く。",
            "現在のお買い得商品やキャンペーンについて聞く。",
            "短いメッセージで会話する。",
        ],
    },
]

# ──────────────────────────────────────────────────────────────────────
# ConversationSimulator（会話シミュレータ）とは？
#
# AIエージェントを自動テストするための仕組みです。
# 人間の代わりに「模擬ユーザー（別のLLM）」がエージェントと会話し、
# エージェントの受け答えが適切かを自動で評価します。
#
# 仕組み：
#   1. テストケース（test_cases）で「お客様の目的」「性格」「会話の進め方」を定義
#   2. シミュレータが模擬ユーザーを生成し、エージェントとマルチターンの会話を実施
#   3. 模擬ユーザーはテストケースの指示に従い、目的が達成されるか
#      最大ターン数（max_turns）に達するまで会話を続ける
#   4. すべての会話は MLflow にトレースとして記録される
#   5. 記録された会話をスコアラー（Completeness, Safety 等）が自動採点
#
# イメージ：
#   模擬ユーザー（LLM）: 「オーガニック野菜はありますか？」
#           ↓
#   テスト対象エージェント: 「はい！有機バナナ ¥198、有機アボカド ¥148が...」
#           ↓
#   模擬ユーザー: 「通常のバナナと価格を比較できますか？」
#           ↓
#   ... （max_turns まで繰り返し）
#           ↓
#   スコアラーが会話全体を採点 → 「完全性: 0.9, 流暢性: 1.0, ...」
#
# 参照:
#   https://mlflow.org/docs/latest/genai/eval-monitor/running-evaluation/conversation-simulation/
#   https://docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/conversation-simulation
# ──────────────────────────────────────────────────────────────────────
simulator = ConversationSimulator(
    test_cases=test_cases,
    max_turns=5,
    user_model="databricks:/databricks-claude-sonnet-4-5",
)

# エージェント内で@invokeデコレータにより登録された呼び出し関数を取得する
invoke_fn = get_invoke_function()
assert invoke_fn is not None, (
    "@invokeデコレータで登録された関数が見つかりません。"
    "`@invoke()`デコレータが付与された関数が存在することを確認してください。"
)

# 呼び出し関数が非同期の場合、同期関数でラップする。
# シミュレータが既にイベントループを実行している可能性があるため、nest_asyncioを使用して
# ネストされたrun_until_complete()呼び出しがデッドロックしないようにする。
if asyncio.iscoroutinefunction(invoke_fn):
    import nest_asyncio

    nest_asyncio.apply()

    def predict_fn(input: list[dict], **kwargs) -> dict:
        req = ResponsesAgentRequest(input=input)
        loop = asyncio.get_event_loop()
        response = loop.run_until_complete(invoke_fn(req))
        return response.model_dump()
else:

    def predict_fn(input: list[dict], **kwargs) -> dict:
        req = ResponsesAgentRequest(input=input)
        response = invoke_fn(req)
        return response.model_dump()


def evaluate():
    mlflow.genai.evaluate(
        data=simulator,
        predict_fn=predict_fn,
        scorers=[
            Completeness(),
            ConversationCompleteness(),
            ConversationalSafety(),
            KnowledgeRetention(),
            UserFrustration(),
            Fluency(),
            RelevanceToQuery(),
            Safety(),
            ToolCallCorrectness(),
        ],
    )
