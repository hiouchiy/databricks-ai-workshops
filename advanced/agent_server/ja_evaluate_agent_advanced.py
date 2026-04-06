import asyncio
import logging
import re

import mlflow
from dotenv import load_dotenv
from mlflow.entities import Feedback, SpanType
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
    ToolCallEfficiency,
    UserFrustration,
    scorer,
)

from mlflow.genai.simulators import ConversationSimulator
from mlflow.types.responses import ResponsesAgentRequest

# .envファイルが存在する場合、環境変数を読み込む
load_dotenv(dotenv_path=".env", override=True)
logging.getLogger("mlflow.utils.autologging_utils").setLevel(logging.ERROR)

# @invoke登録された関数を見つけるためにagentをインポートする必要がある
from agent_server import agent  # noqa: F401

# ---------------------------------------------------------------------------
# フレッシュマート向け20件のテストケース
# 対象: 構造化データ（Genie）、非構造化データ（Vector Search）、
#       複合クエリ、メモリ・パーソナライズ
# ---------------------------------------------------------------------------
test_cases = [
    # ── 構造化データ（Genie）── 1-7
    {
        "goal": "オーガニック青果の在庫状況を確認する",
        "persona": "健康志向でオーガニック商品を好むお客様。",
        "simulation_guidelines": [
            "青果コーナーのオーガニック商品について聞く。",
            "いくつかの商品の価格を聞く。",
            "短いメッセージで会話する。",
        ],
    },
    {
        "goal": "先月のフレッシュマートでの支出を確認する",
        "persona": "家計を見直している節約志向のお客様。",
        "simulation_guidelines": [
            "先月の合計支出を聞く。",
            "カテゴリ別や来店日別の内訳を聞く。",
            "短いメッセージで会話する。",
        ],
    },
    {
        "goal": "渋谷駅に近いフレッシュマートの店舗を探す",
        "persona": "初めて利用する、便利な店舗を探しているお客様。",
        "simulation_guidelines": [
            "渋谷の近くにある店舗を聞く。",
            "営業時間とサービス内容を聞く。",
            "短いメッセージで会話する。",
        ],
    },
    {
        "goal": "¥200以下のベーカリー商品を探す",
        "persona": "手頃なパンやお菓子を探しているお客様。",
        "simulation_guidelines": [
            "¥200以下のベーカリー商品を聞く。",
            "人気の商品を聞く。",
            "短いメッセージで会話する。",
        ],
    },
    {
        "goal": "直近3回の注文内容を確認する",
        "persona": "いつも買う商品をリピート購入したい常連のお客様。",
        "simulation_guidelines": [
            "最近の注文履歴を見せてもらう。",
            "ある注文の詳細を聞く。",
            "短いメッセージで会話する。",
        ],
    },
    {
        "goal": "登録されている支払い方法を確認する",
        "persona": "まとめ買いの前に支払い手段を確認したいお客様。",
        "simulation_guidelines": [
            "アカウントに登録されている支払い方法を聞く。",
            "モバイル決済が使えるか聞く。",
            "短いメッセージで会話する。",
        ],
    },
    {
        "goal": "在庫が少ない乳製品を確認する",
        "persona": "売り切れる前に乳製品を買いたいお客様。",
        "simulation_guidelines": [
            "在庫が少ない乳製品を聞く。",
            "入荷の予定について聞く。",
            "短いメッセージで会話する。",
        ],
    },
    # ── 非構造化データ（Vector Search ポリシー）── 8-14
    {
        "goal": "昨日買った傷んだいちごの返品方法を理解する",
        "persona": "傷んだいちごを買ってしまい、困っているお客様。",
        "simulation_guidelines": [
            "傷んだいちごの問題を説明する。",
            "生鮮食品の返品期限を聞く。",
            "レシートがない場合の返金方法を聞く。",
        ],
    },
    {
        "goal": "Gold会員ランクの特典を知る",
        "persona": "Silver会員で、もっと使ってGoldに上がるべきか検討しているお客様。",
        "simulation_guidelines": [
            "Gold会員の特典を聞く。",
            "Gold会員になるための条件を聞く。",
            "Goldのポイント付与率を聞く。",
        ],
    },
    {
        "goal": "ほうれん草のリコール情報を確認する",
        "persona": "小さい子どもにほうれん草を食べさせた直後で心配な保護者。",
        "simulation_guidelines": [
            "心配を伝え、ほうれん草のリコールについて聞く。",
            "対象のロット番号やブランドを聞く。",
            "すでに食べてしまった場合の対処法を聞く。",
        ],
    },
    {
        "goal": "Silver会員の当日配送の料金を確認する",
        "persona": "今日中に食料品を届けてほしいSilver会員のお客様。",
        "simulation_guidelines": [
            "当日配送のオプションと料金を聞く。",
            "送料無料になる最低注文金額を聞く。",
            "配送時間帯を聞く。",
        ],
    },
    {
        "goal": "フレッシュマートの価格保証ポリシーを理解する",
        "persona": "競合店のチラシでもっと安い価格を見つけた賢いお客様。",
        "simulation_guidelines": [
            "フレッシュマートが他店の価格に合わせてくれるか聞く。",
            "制限や条件を聞く。",
            "短いメッセージで会話する。",
        ],
    },
    {
        "goal": "冷凍食品の返品期限を確認する",
        "persona": "3週間前に買った冷凍アイスが冷凍焼けしていたお客様。",
        "simulation_guidelines": [
            "冷凍焼けしたアイスの問題を説明する。",
            "冷凍食品の返品期限を聞く。",
            "レシートが必要かどうか聞く。",
        ],
    },
    {
        "goal": "配送で間違った商品が届いた場合の対応を知る",
        "persona": "配送で間違った商品が届いて困っているお客様。",
        "simulation_guidelines": [
            "間違った商品が届いた状況を説明する。",
            "返金や交換について聞く。",
            "お詫びクレジットなどの補償について聞く。",
        ],
    },
    # ── 複合質問（構造化 + 非構造化）── 15-18
    {
        "goal": "Gold会員の配送特典を確認してから、青果の在庫を見る",
        "persona": "大量注文を配送で計画しているGold会員のお客様。",
        "simulation_guidelines": [
            "Gold会員の配送料割引について聞く。",
            "次に青果の在庫を聞く。",
            "店頭受取（カーブサイドピックアップ）を代替案として聞く。",
        ],
    },
    {
        "goal": "クランチタイム ピーナッツバタークラッカーが安全か確認する",
        "persona": "乳アレルギーの子どもがいて、クランチタイムのクラッカーを買ったお客様。",
        "simulation_guidelines": [
            "乳アレルギーの心配とクラッカーについて聞く。",
            "この商品にリコールがかかっているか聞く。",
            "リコール商品の返金方法を聞く。",
        ],
    },
    {
        "goal": "レシートなしで返品する方法と選択肢を理解する",
        "persona": "2週間前に買った常温商品のレシートをなくしたお客様。",
        "simulation_guidelines": [
            "レシートをなくしたことを説明し、返品したいと伝える。",
            "レシートなし返品の上限や返金方法を聞く。",
            "ポイントカードの購入履歴で対応できるか聞く。",
        ],
    },
    {
        "goal": "Platinum会員としてオーガニック商品のベストな買い方を探す",
        "persona": "オーガニック商品だけを買う忠実なPlatinum会員のお客様。",
        "simulation_guidelines": [
            "Platinum限定の特典と割引について聞く。",
            "現在購入できるオーガニック商品を見せてもらう。",
            "プライベートブランドのPlatinum割引について聞く。",
        ],
    },
    # ── メモリ・パーソナライズ ── 19-20
    {
        "goal": "食事制限を保存して、パーソナライズされた商品提案を受ける",
        "persona": "ナッツアレルギーがあり、グルテンフリーの食事をしているお客様。",
        "simulation_guidelines": [
            "ナッツアレルギーとグルテンフリーの好みを伝える。",
            "この情報を覚えておくよう頼む。",
            "制限に合った商品のおすすめを聞く。",
        ],
    },
    {
        "goal": "8人分のディナーパーティーの食材と営業時間を確認する",
        "persona": "週末のディナーパーティーを計画していて、食材探しに助けが欲しい料理好きのお客様。",
        "simulation_guidelines": [
            "ディナーパーティーの計画を伝え、食材の提案を求める。",
            "特定の食材の在庫状況を聞く。",
            "買い物に行く時間を計画するため営業時間を聞く。",
        ],
    },
]


# ---------------------------------------------------------------------------
# カスタムスコアラー
# ---------------------------------------------------------------------------

# フレッシュマートの日本語ポリシー文書に含まれる具体的な値。
# エージェントが曖昧な回答ではなく具体的な数字を引用しているかチェックに使用。
POLICY_KEYWORDS = [
    "48時間", "90日", "30日", "7日",
    "¥800", "¥600", "¥400",
    "¥5,000", "¥7,500", "¥10,000", "¥3,000", "¥3,500", "¥2,500",
    "bronze", "silver", "gold", "platinum",
    "¥100につき1ポイント", "1.5ポイント", "2ポイント", "3ポイント",
    "100ポイント", "500ポイント", "1,000ポイント",
    "ダブルフレッシュ保証",
    "サンブライト", "はっぴーファーム", "クランチタイム",
    "大腸菌", "大豆アレルゲン", "乳アレルゲン",
    "0120-", "24時間", "48時間",
    "5〜7営業日", "3〜5営業日",
    "14:00", "16:00", "10km", "15km",
    "9:00", "22:00", "21:00",
    "消費期限", "賞味期限",
    "特定原材料",
]


# ──────────────────────────────────────────────────────────────────────
# カスタムスコアラー ① tool_routing_accuracy（ツールルーティング精度）
#
# 何を測るか：
#   エージェントが「質問の種類に応じて正しいツールを選んでいるか」を評価します。
#
# なぜ重要か：
#   このエージェントには3種類のツールがあります：
#     ・Genie       → 商品・顧客・取引などの「データベース検索」用
#     ・Vector Search → 返品ポリシーや会員制度などの「ポリシー文書検索」用
#     ・Memory tools  → ユーザーの好みや過去の会話の「記憶」用
#   例えば「返品ポリシーを教えて」という質問に対して Genie を使ったら不適切です。
#   正しいツールが選ばれているかを MLflow のトレースから自動チェックします。
#
# 評価方法：
#   MLflow のトレースに記録されたツール呼び出しのスパン（span）を分析し、
#   ツール名に "genie", "vector", "memory" が含まれるかを確認します。
#   適切なツールが1つでも使われていれば "yes"、そうでなければ "no" を返します。
# ──────────────────────────────────────────────────────────────────────
@scorer
def tool_routing_accuracy(*, outputs=None, trace=None) -> Feedback:
    """エージェントがクエリを正しいMCPツールにルーティングしているかチェックする。

    Genie（retail-grocery-genie）は構造化データクエリ
    （商品、顧客、取引、店舗、支払い）に使用されるべき。
    Vector Search（retail-policy-docs）はポリシーに関する質問
    （返品、会員制度、配送、リコール、プライバシー、カスタマーサービス、店舗運営）に使用されるべき。
    """
    if trace is None:
        return Feedback(
            name="tool_routing_accuracy",
            value="unknown",
            rationale="トレースが利用できないため、ツール呼び出しを確認できません。",
        )

    tool_spans = trace.search_spans(span_type=SpanType.TOOL)
    if not tool_spans:
        return Feedback(
            name="tool_routing_accuracy",
            value="no_tools",
            rationale="このやり取りではツール呼び出しが行われませんでした。",
        )

    tool_names = [span.name for span in tool_spans]

    used_genie = any("genie" in n.lower() for n in tool_names)
    used_vector = any(
        "vector" in n.lower() or "policy" in n.lower() or "search" in n.lower()
        for n in tool_names
    )
    used_memory = any("memory" in n.lower() for n in tool_names)

    tools_summary = ", ".join(set(tool_names))
    rationale_parts = []
    if used_genie:
        rationale_parts.append("構造化データクエリにGenieを使用")
    if used_vector:
        rationale_parts.append("ポリシー検索にVector Searchを使用")
    if used_memory:
        rationale_parts.append("パーソナライズにメモリツールを使用")
    if not rationale_parts:
        rationale_parts.append("その他のツールを使用")

    return Feedback(
        name="tool_routing_accuracy",
        value="yes" if (used_genie or used_vector or used_memory) else "no",
        rationale=f"呼び出されたツール: [{tools_summary}]. {'；'.join(rationale_parts)}。",
    )


# ──────────────────────────────────────────────────────────────────────
# カスタムスコアラー ② policy_specificity（ポリシー回答の具体性）
#
# 何を測るか：
#   エージェントがポリシーに関する質問に対して「具体的な数字や条件を引用して
#   回答しているか」を評価します。
#
# なぜ重要か：
#   「返品できますよ」だけでは不十分です。良い回答は
#   「生鮮食品は購入日より48時間以内に返品可能です。¥3,000以下の場合は
#    レシート不要で、ポイントカードの履歴で確認できます」のように
#   具体的な数字・条件・金額を含むべきです。
#
# 評価方法：
#   POLICY_KEYWORDS リスト（「48時間」「¥800」「Gold」「ダブルフレッシュ保証」等）
#   に含まれるキーワードが回答中にいくつ出現するかをカウントします。
#     ・0個 → スコア 0.0（曖昧な回答）
#     ・1個 → スコア 0.33
#     ・2個 → スコア 0.67
#     ・3個以上 → スコア 1.0（具体的で良い回答）
# ──────────────────────────────────────────────────────────────────────
@scorer
def policy_specificity(*, inputs=None, outputs=None) -> Feedback:
    """エージェントが曖昧な回答ではなく具体的なポリシー詳細を提供しているかチェックする。

    フレッシュマートのポリシー文書に含まれる具体的な数値、ランク名、
    金額、期間などの引用を確認する。
    """
    if outputs is None:
        return Feedback(
            name="policy_specificity",
            value=0.0,
            rationale="評価対象の出力がありません。",
        )

    # 出力からテキストを抽出
    response_text = str(outputs).lower()

    # 具体的なポリシーキーワードの出現数をカウント
    found = [kw for kw in POLICY_KEYWORDS if kw.lower() in response_text]
    score = min(len(found) / 3.0, 1.0)  # 3件以上の具体的な詳細で満点

    if not found:
        rationale = "回答にポリシーの具体的な詳細（数字、ランク名、金額、期限など）が含まれていません。"
    else:
        rationale = f"{len(found)}件の具体的なポリシー詳細が見つかりました：{', '.join(found[:5])}。"

    return Feedback(
        name="policy_specificity",
        value=score,
        rationale=rationale,
    )


# ──────────────────────────────────────────────────────────────────────
# カスタムスコアラー ③ retail_tone_appropriateness（接客トーンの適切さ）
#
# 何を測るか：
#   エージェントの回答が「スーパーの店員として適切な接客トーン」で
#   書かれているかを評価します。
#
# なぜ重要か：
#   AIエージェントであっても、お客様対応では人間の店員と同じように
#   丁寧で温かみのある対応が求められます。特にクレーム対応では
#   共感を示しつつ、具体的な解決策を提示することが重要です。
#
# 評価方法（4つの観点、合計 1.0 点満点）：
#
#   ① 共感的な表現（0.35点）
#      「申し訳」「ご不便」「お手伝い」「承知」等の表現があるか
#      → クレームへの共感や、お客様の気持ちに寄り添う姿勢
#
#   ② 具体的なアクション提示（0.35点）
#      「サービスカウンター」「お持ちください」「手順」「おすすめ」等の表現があるか
#      → 「こうすれば解決できます」という次のステップの提示
#
#   ③ 温かみのあるトーン（0.30点）
#      「いらっしゃいませ」「ありがとう」「お気軽に」「またのご来店」等の表現があるか
#      → あいさつや締めくくりの温かさ
#
#   ④ 責任転嫁の表現（-0.50点のペナルティ）
#      「お客様のせい」「お客様が悪い」「対応できません」等の表現があれば減点
#      → お客様を不快にさせる表現は大幅減点
#
# 例：
#   良い回答（スコア 1.0）：
#     「ご不便をおかけして申し訳ございません。傷んだいちごは、
#      サービスカウンターにお持ちいただければ即時返金いたします。
#      他にご質問はございますか？」
#
#   悪い回答（スコア 0.0）：
#     「返品は自分でやってください。」
# ──────────────────────────────────────────────────────────────────────
@scorer
def retail_tone_appropriateness(*, inputs=None, outputs=None) -> Feedback:
    """回答がフレンドリーでプロフェッショナルな小売カスタマーサービスのトーンを維持しているか評価する。

    チェック項目: クレームへの共感、顧客への責任転嫁がないこと、
    具体的な次のアクションの提示、温かみのある言葉遣い。
    """
    if outputs is None:
        return Feedback(
            name="retail_tone_appropriateness",
            value=0.0,
            rationale="評価対象の出力がありません。",
        )

    response_text = str(outputs).lower()

    score = 0.0
    reasons = []

    # 共感的な表現のチェック
    empathy_phrases = [
        "申し訳", "お詫び", "ご不便", "ご心配", "お気持ち",
        "お手伝い", "ご案内", "承知", "かしこまり",
        "もちろん", "ぜひ", "喜んで",
    ]
    empathy_count = sum(1 for p in empathy_phrases if p in response_text)
    if empathy_count > 0:
        score += 0.35
        reasons.append(f"共感的な表現を検出（{empathy_count}個）")
    else:
        reasons.append("共感的な表現が検出されませんでした")

    # 具体的な次のアクションの提示チェック
    action_phrases = [
        "いただけます", "手順", "方法", "サービスカウンター",
        "お持ちください", "ご連絡", "お電話",
        "おすすめ", "ご提案", "ご確認",
        "ステップ", "以下の",
    ]
    action_count = sum(1 for p in action_phrases if p in response_text)
    if action_count > 0:
        score += 0.35
        reasons.append(f"具体的なアクション提示を検出（{action_count}個）")
    else:
        reasons.append("具体的なアクション提示が見つかりませんでした")

    # 温かみのあるトーンのチェック（あいさつ、締めくくり）
    warm_phrases = [
        "いらっしゃいませ", "ありがとう", "お越し",
        "お気軽に", "何でもお聞き", "他にご質問",
        "お待ちして", "またのご来店", "お役に立て",
    ]
    warm_count = sum(1 for p in warm_phrases if p in response_text)
    if warm_count > 0:
        score += 0.30
        reasons.append(f"温かみのあるトーンを検出（{warm_count}個）")
    else:
        reasons.append("温かみのあるトーンが検出されませんでした")

    # 責任転嫁の表現（ペナルティ）
    blame_phrases = [
        "お客様のせい", "お客様が悪い", "お客様の責任",
        "対応できません", "当店は関係",
    ]
    blame_count = sum(1 for p in blame_phrases if p in response_text)
    if blame_count > 0:
        score = max(score - 0.5, 0.0)
        reasons.append(f"ペナルティ：責任転嫁の表現を検出（{blame_count}個）")

    return Feedback(
        name="retail_tone_appropriateness",
        value=round(score, 2),
        rationale="；".join(reasons),
    )


# ---------------------------------------------------------------------------
# シミュレータと予測関数
# ---------------------------------------------------------------------------

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
# 参照:
#   https://mlflow.org/docs/latest/genai/eval-monitor/running-evaluation/conversation-simulation/
# ──────────────────────────────────────────────────────────────────────
simulator = ConversationSimulator(
    test_cases=test_cases,
    max_turns=5,
    user_model="databricks:/databricks-claude-sonnet-4-5",
)

# エージェントで@invokeデコレータにより登録されたinvoke関数を取得
invoke_fn = get_invoke_function()
assert invoke_fn is not None, (
    "@invokeデコレータで登録された関数が見つかりません。"
    "@invoke()デコレータが付与された関数があることを確認してください。"
)

# invoke関数が非同期の場合、同期関数でラップする。
# シミュレータが既にイベントループを実行している可能性があるため、
# nest_asyncioを使用してネストされたrun_until_complete()呼び出しを
# デッドロックなしで許可する。
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
            # 定義済みスコアラー
            Completeness(),
            ConversationCompleteness(),
            ConversationalSafety(),
            KnowledgeRetention(),
            UserFrustration(),
            Fluency(),
            RelevanceToQuery(),
            Safety(),
            ToolCallCorrectness(),
            ToolCallEfficiency(),
            # カスタムスコアラー
            tool_routing_accuracy,
            policy_specificity,
            retail_tone_appropriateness,
        ],
    )
