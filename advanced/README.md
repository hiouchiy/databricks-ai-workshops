**[日本語](#databricks-ai-エージェントワークショップ長期記憶を持つ食品スーパーアシスタント)** | **[English](#databricks-ai-agent-workshop-retail-grocery-assistant-with-long-term-memory)**

---

# Databricks AI エージェントワークショップ：長期記憶を持つ食品スーパーアシスタント

Databricks 上で、リアルタイムデータクエリ・ドキュメント検索・永続的なユーザーメモリを組み合わせた AI 会話エージェントを構築し、フルスタック Databricks App としてデプロイします。

---

## アーキテクチャ概要

![Databricks Advanced Workshop Architecture](docs/architecture.png)

ワークショップは以下の2パートで構成されています（半日で完了可能）：

- **Part 1 — エージェント構築**：MCP ツール（Genie、Code Interpreter）・ネイティブ Vector Search・Lakebase メモリを備えた LangGraph エージェントを構築し、ローカルで動作確認します。
- **Part 2 — 評価とモニタリング**：MLflow Traces・定義済み/カスタムスコアラー・ConversationSimulator を使ってエージェントを評価します。トレースは MLflow Experiment または Unity Catalog Delta Table に記録できます。

---

## 構築するもの

以下の機能を備えた **FreshMart 食品スーパーショッピングアシスタント** を構築します：

| 機能 | 利用技術 | 説明 |
|------|----------|------|
| **構造化データクエリ** | Genie Space（MCP） | 顧客アカウント・商品・取引・店舗を自然言語から SQL で検索 |
| **ポリシー文書検索** | Vector Search（MCP） | 返品・会員制度・配送・リコール・プライバシーなどの店舗ポリシーに対する RAG |
| **長期ユーザーメモリ** | Lakebase + Embeddings | ユーザーの好み・食事制限・過去のやり取りをセッションをまたいで記憶 |
| **タスク・会話履歴** | Lakebase + Embeddings | エージェントが対応したタスクを追跡し、過去の会話を要約 |
| **コード実行** | system.ai Code Interpreter | Python による計算・データ分析・グラフ生成 |
| **ストリーミングチャット UI** | React + Vercel AI SDK | Databricks OAuth 認証付きのリアルタイムストリーミングレスポンス |

---

## プロジェクト構成

```
advanced/
├── agent_server/                    # Python エージェントバックエンド
│   ├── agent.py                     # コアエージェントロジック（LangGraph + MCP ツール）
│   ├── utils_memory.py              # 7つのメモリツール（取得/保存/削除 + タスク/会話）
│   ├── utils.py                     # 認証・スレッド管理・ストリーミングヘルパー
│   ├── start_server.py              # MLflow AgentServer 起動
│   ├── evaluate_agent_multi_turn.py           # マルチターン評価（会話シミュレータ、3テストケース）
│   ├── evaluate_agent_multi_turn_advanced.py  # マルチターン高度な評価（20テストケース + カスタムスコアラー）
│   └── evaluate_agent_chat.py                 # チャット評価（expected_facts、ネイティブ/MCP 切替可能）
│
├── e2e-chatbot-app-next/            # フルスタックチャット UI
│   ├── client/                      # React + Vite フロントエンド
│   ├── server/                      # Express.js バックエンド
│   ├── packages/                    # 共有ライブラリ（auth, db, core, ai-sdk）
│   └── scripts/                     # DB マイグレーションスクリプト
│
├── scripts/                         # セットアップ・ユーティリティスクリプト
│   ├── quickstart.py                # 対話式セットアップウィザード
│   ├── start_app.py                 # フロントエンド + バックエンドを同時起動
│   ├── discover_tools.py            # 利用可能な Databricks ツールの検出
│   ├── grant_sp_permissions.py       # デプロイ後の SP 権限一括付与（UC + Lakebase）
│   ├── grant_lakebase_permissions.py # Lakebase PostgreSQL 内部権限の個別付与
│   ├── grant_team_access.py          # チームメンバーへのリソース共有
│   └── register_prompt.py           # 日本語システムプロンプトを Prompt Registry に登録
│
├── .claude/skills/                  # Claude Code 用 AI 開発支援スキル
├── databricks.yml                   # Databricks Asset Bundle 設定
├── app.yaml                         # Databricks App マニフェスト
├── pyproject.toml                   # Python 依存関係（uv）
├── .env.example                     # 環境変数テンプレート
└── requirements.txt                 # uv による依存関係管理への参照
```

---

## 技術スタック

| レイヤー | 技術 |
|----------|------|
| **LLM** | Claude Sonnet 4.5（Databricks Foundation Model API 経由） |
| **エージェントフレームワーク** | LangGraph（ステートフルなマルチツールオーケストレーション） |
| **ツールプロトコル** | MCP（Model Context Protocol）— Genie、Vector Search、Code Interpreter |
| **メモリストア** | Lakebase（マネージド PostgreSQL）+ セマンティック Embeddings |
| **トレーシング・評価** | MLflow 3（自動ログ、10 種のスコアラー、会話シミュレーター） |
| **フロントエンド** | React + TypeScript + Vite + Vercel AI SDK |
| **バックエンド API** | FastAPI（MLflow AgentServer 経由、OpenAI Responses API 互換） |
| **認証** | Databricks OAuth（U2M）+ On-Behalf-Of（OBO）ユーザーパススルー |
| **デプロイ** | Databricks Apps（Asset Bundles 経由） |
| **パッケージマネージャー** | uv（Python）、npm workspaces（Node.js） |

---

## 前提条件

- 以下にアクセスできる **Databricks ワークスペース**：
  - Foundation Model API エンドポイント
  - Genie Spaces
  - Vector Search
  - Lakebase（**オートスケーリングのみ対応**。Provisioned インスタンスは本コンテンツではサポートしていません）
  - Databricks Apps
- **ローカルツール**：
  - [uv](https://docs.astral.sh/uv/getting-started/installation/)（Python パッケージマネージャー）
  - [nvm](https://github.com/nvm-sh/nvm) + Node.js 20 LTS
  - [Databricks CLI](https://docs.databricks.com/aws/en/dev-tools/cli/install) **v0.297 以上**（Apps デプロイのリソースバインディングに必要）
- **任意**：[Claude Code](https://docs.anthropic.com/en/docs/claude-code)（AI 支援開発用）

---

## はじめ方

### 方法 1：クイックスタート（推奨）

CUI（コマンドライン）版と GUI（デスクトップアプリ）版の2つが用意されています。実行内容は同じです。

```bash
# リポジトリをクローン
git clone https://github.com/hiouchiy/databricks-ai-workshops.git
cd databricks-ai-workshops/advanced

# CUI 版（ターミナルで対話式に実行）
uv run quickstart

# GUI 版（デスクトップウィザードが起動）
uv run quickstart-ui
```

GUI 版はステップごとに1画面ずつ設定を進めるウィザード形式で、カタログの一覧選択・名前のバリデーション・進捗バー表示などの機能があります。ターミナル操作に不慣れな場合は GUI 版をお勧めします。

クイックスタートが以下を対話式で実行します：
1. 前提条件チェック（`uv`、`Node.js`、`Databricks CLI`）
2. Databricks 認証
3. カタログ名・スキーマ名・SQL ウェアハウス・Vector Search エンドポイントの入力
4. カタログ・スキーマの作成
5. 構造化データの生成（6テーブル、日本語。既存の場合はスキップ）
6. ポリシー文書のチャンク生成 + CDF 有効化
7. Vector Search インデックスの作成（READY まで自動待機）
8. Genie Space の作成
9. Lakebase のセットアップ（メモリ用）
10. MLflow 実験を2つ作成（モニタリング用 + 評価用）
11. `.env` / `databricks.yml` / `app.yaml` の生成・更新
12. トレース送信先の選択（MLflow Experiment または Unity Catalog Delta Table）
13. Prompt Registry の選択（オプション：Unity Catalog でプロンプトをバージョン管理）
14. Python / Node.js 依存関係のインストール

セットアップ完了後は、いつでも以下で起動できます：

```bash
uv run start-app
```

チャット UI は **http://localhost:3000** 、API は **http://localhost:8000** でアクセスできます。

> **次のステップ：** アプリが動作したら、**[ステップ 10：エージェントの評価](WORKSHOP_INSTRUCTIONS.md#ステップ-10オプションエージェントの評価)** に進んでください。評価・トレース設定・Databricks Apps へのデプロイの手順が記載されています。

#### Delta Table トレースを選択した場合

クイックスタートで「Unity Catalog Delta Table にトレースを送信する」を選択した場合、トレーステーブルの初期作成が **クイックスタート内で自動実行** されます（Databricks 上でサーバーレスの one-time run を使用）。手動でノートブックを開く必要はありません。

> 自動実行に失敗した場合のみ、手動手順がフォールバックとして表示されます。

#### チームでハンズオンを実施する場合

代表者がクイックスタートでリソースを作成した後、チームメンバーにリソースを共有して使わせたい場合は、ローカルから以下を実行してください：

```bash
uv run grant-team-access member1@company.com member2@company.com
```

Unity Catalog、MLflow Experiment、Genie Space、Lakebase、SQL Warehouse への権限が一括で付与されます。後からメンバーを追加する場合も同じコマンドを再実行するだけで OK です（べき等）。

実行後、メンバーに以下の情報を共有してください（コマンド実行後にまとめて表示されます）：
- カタログ名・スキーマ名
- Genie Space ID
- Lakebase プロジェクト名・ブランチ名
- MLflow Experiment ID（モニタリング + 評価）

メンバーはクイックスタートを実行し、MLflow Experiment の設定で「既存の ID を入力」を選択すれば、すぐにステップ 9（ローカル実行）から始められます。

詳細は [WORKSHOP_INSTRUCTIONS.md の「チーム利用時の権限共有」](WORKSHOP_INSTRUCTIONS.md#チーム利用時の権限共有代表者が実施) を参照してください。

### 方法 2：手動セットアップ

ステップバイステップの詳細手順は **[ワークショップインストラクション（日本語）](WORKSHOP_INSTRUCTIONS.md#ja)** を参照してください。データ生成・Vector Search 作成・Lakebase セットアップ・評価・デプロイまで、全手順が記載されています。

### 方法 3：Claude Code を使う

[Claude Code](https://docs.anthropic.com/en/docs/claude-code) がインストール済みであれば、`.claude/skills/` に AI 支援開発用のスキルが同梱されています。

```bash
# プロジェクトディレクトリで Claude Code を起動
cd databricks-ai-workshops/advanced
claude
```

以下のプロンプトを使用します（プレースホルダーを実際の値に置き換えてください）：

```
ローカルでエージェントアプリをセットアップして起動してください。
以下のリソースは手動で作成済みです：

- Databricks CLI プロファイル: <PROFILE_NAME>
- MLflow モニタリング Experiment ID: <MONITORING_EXPERIMENT_ID>
- MLflow 評価 Experiment ID: <EVAL_EXPERIMENT_ID>
- Genie Space ID: <GENIE_SPACE_ID>
- Vector Search Index: <CATALOG>.<SCHEMA>.policy_docs_index
- Lakebase プロジェクト: <PROJECT_NAME>
- Lakebase ブランチ: <BRANCH_NAME>

手順：
1. .env にすべての値を設定（PGHOST は Lakebase ブランチのエンドポイントから取得）
2. uv run start-app を実行し、フロントエンド（3000）とバックエンド（8000）が起動することを確認
3. curl で /invocations にリクエストを送って動作確認
```

> **次のステップ：** アプリが動作したら、**[ステップ 10：エージェントの評価](WORKSHOP_INSTRUCTIONS.md#ステップ-10オプションエージェントの評価)** に進んでください。

---

## ワークショップの詳細手順

**[WORKSHOP_INSTRUCTIONS.md（日本語）](WORKSHOP_INSTRUCTIONS.md#ja)** にステップバイステップの実施手順があります：

- ステップ 1〜3：データ生成（構造化データ + ポリシー文書チャンク）
- ステップ 4〜6：Vector Search・Genie Space・Lakebase の作成
- ステップ 7〜8：MLflow 実験の作成・環境変数の設定
- ステップ 9：ローカル実行と動作確認
- ステップ 10：エージェントの評価（3種類の評価方法）
- ステップ 11：Databricks Apps へのデプロイ（オプション）

---

## 主要コンポーネント

### エージェントアーキテクチャ

| コンポーネント | ファイル | 説明 |
|---|---|---|
| コアエージェント | `agent_server/agent.py` | LangGraph オーケストレーション・MCP ツール・ネイティブ Vector Search |
| メモリツール | `agent_server/utils_memory.py` | 7つのメモリツール（ユーザー好み・タスク・会話サマリー） |
| ユーティリティ | `agent_server/utils.py` | 認証・スレッド管理・ストリーミング |

### ツール構成

| ツール | 接続方式 | 用途 |
|---|---|---|
| Genie | MCP | 構造化データへの自然言語クエリ |
| Code Interpreter | MCP | Python コード実行 |
| Vector Search | ネイティブ（DatabricksVectorSearch） | ポリシー文書の検索（RETRIEVER スパン対応） |
| メモリ（7種） | Lakebase | ユーザー好み・タスク・会話の永続化 |

### 評価コマンド

```bash
uv run agent-evaluate            # マルチターン評価（3テストケース）
uv run agent-evaluate-advanced   # マルチターン高度評価（20テストケース + カスタムスコアラー）
uv run agent-evaluate-chat       # チャット評価（expected_facts ベース）
```

詳細は [WORKSHOP_INSTRUCTIONS.md のステップ 10](WORKSHOP_INSTRUCTIONS.md#ステップ-10オプションエージェントの評価) を参照してください。

---

## API リファレンス

エージェントは MLflow の ResponsesAgent を通じて [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses) インターフェースを実装しています。

### ストリーミングリクエスト

```bash
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{"input": [{"role": "user", "content": "オーガニック野菜はありますか？"}], "stream": true}'
```

### 非ストリーミングリクエスト

```bash
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{"input": [{"role": "user", "content": "返品ポリシーを教えてください"}]}'
```

### ユーザーコンテキスト付きリクエスト（メモリ有効化）

```bash
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{
    "input": [{"role": "user", "content": "オーガニック野菜が好きだと覚えておいて"}],
    "context": {"user_id": "workshop-user@example.com"}
  }'
```

---

## エージェントのカスタマイズ

### LLM の変更

`agent_server/agent.py` の `LLM_ENDPOINT_NAME` を編集します：

```python
LLM_ENDPOINT_NAME = "databricks-claude-sonnet-4-5"  # Foundation Model API の任意のエンドポイント
```

### 新しい MCP ツールの追加

`agent_server/agent.py` の `init_mcp_client()` 関数にエントリを追加します：

```python
DatabricksMCPServer(
    name="my-new-tool",
    url=f"{host_name}/api/2.0/mcp/...",
    workspace_client=workspace_client,
)
```

### システムプロンプトのカスタマイズ

`agent_server/agent.py` の `SYSTEM_PROMPT` 変数を編集し、エージェントの性格・機能・ガイドラインを変更します。

### Python 依存関係の追加

```bash
uv add <パッケージ名>
```

---

## Databricks Apps へのデプロイ

```bash
# 1. バンドルデプロイ
databricks bundle deploy -t dev --profile DEFAULT

# 2. アプリ起動（初回は 3〜5 分かかります）
databricks bundle run retail_grocery_ltm_memory -t dev --profile DEFAULT

# 3. SP 権限付与（UC + Lakebase を一括）
uv run grant-sp-permissions

# 4. アプリ再起動
databricks apps stop $APP_NAME --profile DEFAULT
databricks apps start $APP_NAME --profile DEFAULT
```

詳細な手順は [WORKSHOP_INSTRUCTIONS.md のステップ 11](WORKSHOP_INSTRUCTIONS.md#ステップ-11オプションdatabricks-apps-へのデプロイ) を参照してください。

---

## トラブルシューティング

| 問題 | 解決策 |
|------|--------|
| `python3: command not found` | Python 3.11 以上がインストールされているか確認。`python` でも動く場合あり |
| `uv sync` で PyPI 接続エラー | インターネット接続を確認。社内ネットワークの場合は PyPI ミラー/プロキシを設定 |
| `npm install` が Apps 上でクラッシュ | `package-lock.json` に社内プロキシ URL が含まれている。`rm -f package-lock.json && npm install` で再生成 |
| `Lakebase configuration is required` | `.env` に `LAKEBASE_AUTOSCALING_PROJECT` と `LAKEBASE_AUTOSCALING_BRANCH`（またはプロビジョニング済みの場合は `LAKEBASE_INSTANCE_NAME`）を設定 |
| `couldn't get a connection after 30 sec` | Lakebase SP 権限未付与。`uv run grant-sp-permissions` を実行しアプリを再起動 |
| `checkpoint_migrations` duplicate key | 初回起動時の並行初期化で発生（無害）。リトライで自動回復 |
| `tool_use without tool_result` | チェックポイント破損。自動でチェックポイント削除＆リトライされる |
| `302 redirect when querying deployed agent` | PAT ではなく OAuth トークンを使用。`databricks auth token` を実行 |
| 502 Bad Gateway（デプロイ後） | フロントエンドの npm build に 3〜5 分かかる。待ってからリトライ |
| `bundle deploy` リソースエラー | Databricks CLI を v0.297 以上に更新（`brew upgrade databricks`） |
| Apps UI でリソースが空表示 | CLI が古い。v0.297 以上ならリソースバインディングが正しく反映される |

---

## よくある質問

**Q：別の LLM を使えますか？**
はい。`agent_server/agent.py` の `LLM_ENDPOINT_NAME` を Foundation Model API の任意のエンドポイント（例：`databricks-meta-llama-3-3-70b-instruct`）に変更してください。

**Q：独自のツールを追加できますか？**
はい。UC Functions、Genie Spaces、Vector Search Indexes、カスタム MCP サーバーを追加できます。詳しくは [Agent Framework Tools のドキュメント](https://docs.databricks.com/aws/en/generative-ai/agent-framework/agent-tool)を参照してください。

**Q：On-Behalf-Of（OBO）認証はどう動きますか？**
`agent_server.utils` の `get_user_workspace_client()` を使うと、アプリのサービスプリンシパルではなくリクエスト元ユーザーとして認証できます。詳しくは [OBO のドキュメント](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth)を参照してください。

**Q：カスタムトレーシングを追加するには？**
MLflow の自動ログが LLM 呼び出しを自動キャプチャします。カスタムスパンは `@mlflow.trace` または MLflow トレーシング API で追加できます。詳しくは [MLflow トレーシングのドキュメント](https://docs.databricks.com/aws/en/mlflow3/genai/tracing/app-instrumentation/)を参照してください。

---

## リソースのクリーンアップ

ワークショップで作成したリソースを一括削除するには：

```bash
uv run cleanup
```

Databricks App、MLflow Experiments、Vector Search、Genie Space、Lakebase、スキーマ、ローカルファイルを一つずつ確認しながら削除します。詳細は [WORKSHOP_INSTRUCTIONS.md](WORKSHOP_INSTRUCTIONS.md#リソースのクリーンアップ) を参照してください。

---

## 参考リソース

- [Databricks Agent Framework](https://docs.databricks.com/aws/en/generative-ai/agent-framework/)
- [MLflow ResponsesAgent](https://mlflow.org/docs/latest/genai/flavors/responses-agent-intro/)
- [Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/)
- [Lakebase ドキュメント](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/lakebase)
- [Databricks 上の MCP](https://docs.databricks.com/aws/en/generative-ai/agent-framework/agent-tool)
- [LangGraph ドキュメント](https://docs.langchain.com/oss/python/langgraph/quickstart)

---

**[日本語](#databricks-ai-エージェントワークショップ長期記憶を持つ食品スーパーアシスタント)** | **[English](#databricks-ai-agent-workshop-retail-grocery-assistant-with-long-term-memory)**

---

# Databricks AI Agent Workshop: Retail Grocery Assistant with Long-Term Memory

Build an AI-powered conversational agent on Databricks that combines real-time data querying, document retrieval, and persistent user memory — deployed as a full-stack Databricks App.

---

## Architecture Overview

![Databricks Advanced Workshop Architecture](docs/architecture.png)

The workshop consists of two parts (completable in half a day):

- **Part 1 — Agent Building**: Build a LangGraph agent with MCP tools (Genie, Code Interpreter), native Vector Search, and Lakebase memory. Test locally.
- **Part 2 — Evaluation & Monitoring**: Evaluate the agent using MLflow Traces, predefined/custom scorers, and ConversationSimulator. Traces can be recorded to MLflow Experiment or Unity Catalog Delta Tables.

---

## What You'll Build

A **FreshMart Grocery Shopping Assistant** with the following capabilities:

| Capability | Powered By | Description |
|---|---|---|
| **Structured data queries** | Genie Space (MCP) | Query customer accounts, products, transactions, stores via natural language to SQL |
| **Policy document lookup** | Vector Search (native DatabricksVectorSearch) | RAG over store policies — returns, memberships, delivery, recalls, privacy |
| **Long-term user memory** | Lakebase + Embeddings | Remembers user preferences, dietary restrictions, and past interactions across sessions |
| **Task & conversation history** | Lakebase + Embeddings | Tracks what the agent helped with and summarizes past conversations |
| **Code execution** | system.ai Code Interpreter | Runs Python for calculations, data analysis, chart generation |
| **Streaming chat UI** | React + Vercel AI SDK | Real-time streaming responses with Databricks OAuth authentication |

---

## Project Structure

```
advanced/
├── agent_server/                    # Python agent backend
│   ├── agent.py                     # Core agent logic (LangGraph + MCP tools)
│   ├── utils_memory.py              # 7 memory tools (get/save/delete + task/conversation)
│   ├── utils.py                     # Auth, thread management, streaming helpers
│   ├── start_server.py              # MLflow AgentServer bootstrap
│   ├── evaluate_agent_multi_turn.py           # Multi-turn evaluation (conversation simulator, 3 test cases)
│   ├── evaluate_agent_multi_turn_advanced.py  # Advanced multi-turn evaluation (20 test cases + custom scorers)
│   └── evaluate_agent_chat.py                 # Chat evaluation (expected_facts, native/MCP switchable)
│
├── e2e-chatbot-app-next/            # Full-stack chat UI
│   ├── client/                      # React + Vite frontend
│   ├── server/                      # Express.js backend
│   ├── packages/                    # Shared libs (auth, db, core, ai-sdk)
│   └── scripts/                     # DB migration scripts
│
├── scripts/                         # Setup & utility scripts
│   ├── quickstart.py                # Interactive setup wizard
│   ├── start_app.py                 # Starts both frontend + backend
│   ├── discover_tools.py            # Discovers available Databricks tools
│   ├── grant_sp_permissions.py       # Post-deploy SP permissions (UC + Lakebase)
│   ├── grant_lakebase_permissions.py # Lakebase PostgreSQL internal permissions
│   ├── grant_team_access.py          # Share resources with team members
│   └── register_prompt.py           # Register Japanese system prompt to Prompt Registry
│
├── .claude/skills/                  # Claude Code skills for AI-assisted development
├── databricks.yml                   # Databricks Asset Bundle config
├── app.yaml                         # Databricks App manifest
├── pyproject.toml                   # Python dependencies (uv)
├── .env.example                     # Environment variable template
└── requirements.txt                 # Points to uv for dependency management
```

---

## Technology Stack

| Layer | Technology |
|---|---|
| **LLM** | Claude Sonnet 4.5 (via Databricks Foundation Model API) |
| **Agent Framework** | LangGraph (stateful multi-tool orchestration) |
| **Tool Protocol** | MCP (Genie, Code Interpreter) + native DatabricksVectorSearch |
| **Memory Store** | Lakebase (managed PostgreSQL) with semantic embeddings |
| **Tracing & Eval** | MLflow 3 (autologging, 10 predefined scorers, conversation simulator) |
| **Frontend** | React + TypeScript + Vite + Vercel AI SDK |
| **Backend API** | FastAPI via MLflow AgentServer (OpenAI Responses API compatible) |
| **Auth** | Databricks OAuth (U2M) + On-Behalf-Of (OBO) user passthrough |
| **Deployment** | Databricks Apps via Asset Bundles |
| **Package Manager** | uv (Python), npm workspaces (Node.js) |

---

## Prerequisites

- **Databricks workspace** with access to:
  - Foundation Model API endpoints
  - Genie Spaces
  - Vector Search
  - Lakebase (**autoscaling only** — provisioned instances are not supported in this workshop)
  - Databricks Apps
- **Local tools**:
  - [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)
  - [nvm](https://github.com/nvm-sh/nvm) + Node.js 20 LTS
  - [Databricks CLI](https://docs.databricks.com/aws/en/dev-tools/cli/install) **v0.297+** (required for resource bindings in Apps deployment)
- **Optional**: [Claude Code](https://docs.anthropic.com/en/docs/claude-code) for AI-assisted development

---

## Getting Started

### Option 1: Quick Start (Recommended)

Both a CUI (command-line) and GUI (desktop app) version are available. They perform the same setup.

```bash
# Clone the repository
git clone https://github.com/hiouchiy/databricks-ai-workshops.git
cd databricks-ai-workshops/advanced

# CUI version (interactive terminal wizard)
uv run quickstart

# GUI version (desktop wizard with step-by-step pages)
uv run quickstart-ui
```

The GUI version guides you through one setting per page, with features like catalog dropdown selection, name validation, and a progress bar. Recommended if you prefer a visual interface.

The quickstart will interactively walk you through:
1. Prerequisites check (`uv`, `Node.js`, `Databricks CLI`)
2. Databricks authentication
3. Input catalog name, schema name, SQL warehouse, and Vector Search endpoint
4. Create catalog and schema
5. Generate structured data (6 tables, Japanese; skipped if already exists)
6. Generate policy document chunks + enable CDF
7. Create Vector Search index (auto-waits until READY)
8. Create Genie Space
9. Set up Lakebase (for memory)
10. Create 2 MLflow experiments (monitoring + evaluation)
11. Generate/update `.env` / `databricks.yml` / `app.yaml`
12. Select trace destination (MLflow Experiment or Unity Catalog Delta Table)
13. Select Prompt Registry (optional: version-managed prompts in Unity Catalog)
14. Install Python / Node.js dependencies

After setup, start the app anytime with:

```bash
uv run start-app
```

The chat UI will be available at **http://localhost:3000** and the API at **http://localhost:8000**.

> **Next step:** Once the app is running, proceed to **[Step 10: Agent Evaluation](WORKSHOP_INSTRUCTIONS.md#step-10-optional-agent-evaluation)** for evaluation, trace configuration, and Databricks Apps deployment instructions.

#### If you selected Delta Table tracing

If you chose to send traces to a Unity Catalog Delta Table, the quickstart will **automatically create the trace tables** by running a serverless one-time job on Databricks. No manual notebook execution is required.

> If the automatic setup fails, fallback manual instructions will be displayed.

#### Team workshop setup

If running the workshop as a team, the representative should run:

```bash
uv run grant-team-access member1@company.com member2@company.com
```

This grants access to Unity Catalog, MLflow Experiments, Genie Space, Lakebase, and SQL Warehouse. Members can be added later by re-running the same command (idempotent).

After running the command, share the following info with team members (displayed at the end of the command output):
- Catalog name and schema name
- Genie Space ID
- Lakebase project name and branch name
- MLflow Experiment IDs (monitoring + evaluation)

Team members then run quickstart, select "use existing Experiment ID", and start from Step 9.

### Option 2: Manual Setup

For step-by-step detailed instructions, see **[Workshop Instructions (English)](WORKSHOP_INSTRUCTIONS.md#en)**. It covers everything from data generation, Vector Search creation, Lakebase setup, evaluation, to deployment.

### Option 3: Using Claude Code

If you have [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed, the repository includes built-in skills in `.claude/skills/` for AI-assisted development.

```bash
# Start Claude Code in the project directory
cd databricks-ai-workshops/advanced
claude
```

Then use this prompt (replace placeholders with your actual values):

```
Set up and run the agent app locally. I have already created the following
resources manually:

- Databricks CLI profile: <PROFILE_NAME>
- MLflow Monitoring Experiment ID: <MONITORING_EXPERIMENT_ID>
- MLflow Evaluation Experiment ID: <EVAL_EXPERIMENT_ID>
- Genie Space ID: <GENIE_SPACE_ID>
- Vector Search Index: <CATALOG>.<SCHEMA>.policy_docs_index
- Lakebase Project: <PROJECT_NAME>
- Lakebase Branch: <BRANCH_NAME>

Steps:
1. Update .env with all the above values (resolve PGHOST from the Lakebase
   branch endpoint)
2. Run `uv run start-app` and verify both frontend (port 3000) and backend
   (port 8000) are healthy
3. Smoke test the agent with a curl POST to /invocations
```

> **Next step:** Once the app is running, proceed to **[Step 10: Agent Evaluation](WORKSHOP_INSTRUCTIONS.md#step-10-optional-agent-evaluation)**.

---

## Workshop Detailed Steps

For step-by-step workshop instructions, see **[WORKSHOP_INSTRUCTIONS.md (English)](WORKSHOP_INSTRUCTIONS.md#en)**:

- Steps 1-3: Data generation (structured data + policy document chunks)
- Steps 4-6: Create Vector Search, Genie Space, and Lakebase
- Steps 7-8: Create MLflow experiments and configure environment variables
- Step 9: Local execution and verification
- Step 10: Agent evaluation (3 types of evaluation)
- Step 11: Deploy to Databricks Apps (optional)

---

## Key Components

### Agent Architecture

| Component | File | Description |
|---|---|---|
| Core Agent | `agent_server/agent.py` | LangGraph orchestration, MCP tools, native Vector Search |
| Memory Tools | `agent_server/utils_memory.py` | 7 memory tools (user preferences, tasks, conversation summaries) |
| Utilities | `agent_server/utils.py` | Auth, thread management, streaming |

### Tool Configuration

| Tool | Connection | Purpose |
|---|---|---|
| Genie | MCP | Natural language queries on structured data |
| Code Interpreter | MCP | Python code execution |
| Vector Search | Native (DatabricksVectorSearch) | Policy document retrieval (RETRIEVER span support) |
| Memory (7 types) | Lakebase | Persist user preferences, tasks, and conversations |

### Evaluation Commands

```bash
uv run agent-evaluate            # Multi-turn evaluation (3 test cases)
uv run agent-evaluate-advanced   # Advanced multi-turn evaluation (20 test cases + custom scorers)
uv run agent-evaluate-chat       # Chat evaluation (expected_facts based)
```

For details, see [Step 10](WORKSHOP_INSTRUCTIONS.md#step-10-optional-agent-evaluation) in WORKSHOP_INSTRUCTIONS.md.

---

## API Reference

The agent implements the [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses) interface via MLflow's ResponsesAgent.

### Streaming Request

```bash
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{"input": [{"role": "user", "content": "What organic produce do you have?"}], "stream": true}'
```

### Non-Streaming Request

```bash
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{"input": [{"role": "user", "content": "What are your return policies?"}]}'
```

### Request with User Context (enables memory)

```bash
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{
    "input": [{"role": "user", "content": "Remember that I prefer organic produce"}],
    "context": {"user_id": "workshop-user@example.com"}
  }'
```

---

## Customization

### Change the LLM

Edit `LLM_ENDPOINT_NAME` in `agent_server/agent.py`:

```python
LLM_ENDPOINT_NAME = "databricks-claude-sonnet-4-5"  # Any Foundation Model API endpoint
```

### Add New MCP Tools

Add entries to the `init_mcp_client()` function in `agent_server/agent.py`:

```python
DatabricksMCPServer(
    name="my-new-tool",
    url=f"{host_name}/api/2.0/mcp/...",
    workspace_client=workspace_client,
)
```

### Customize the System Prompt

Edit the `SYSTEM_PROMPT` variable in `agent_server/agent.py` to change the agent's personality, capabilities, and guidelines.

### Add Python Dependencies

```bash
uv add <package_name>
```

---

## Deploying to Databricks Apps

```bash
# 1. Bundle deploy
databricks bundle deploy -t dev --profile DEFAULT

# 2. Start app (takes 3-5 minutes on first run)
databricks bundle run retail_grocery_ltm_memory -t dev --profile DEFAULT

# 3. Grant SP permissions (UC + Lakebase in one command)
uv run grant-sp-permissions

# 4. Restart app
databricks apps stop $APP_NAME --profile DEFAULT
databricks apps start $APP_NAME --profile DEFAULT
```

For detailed deployment instructions, see [Step 11](WORKSHOP_INSTRUCTIONS.md#step-11-optional-deploying-to-databricks-apps) in WORKSHOP_INSTRUCTIONS.md.

---

## Troubleshooting

| Issue | Solution |
|---|---|
| `python3: command not found` | Ensure Python 3.11+ is installed. `python` may also work |
| `uv sync` PyPI connection error | Check internet. For corporate networks, configure PyPI mirror/proxy |
| `npm install` crashes in Apps | `package-lock.json` contains corporate proxy URLs. Run `rm -f package-lock.json && npm install` to regenerate with public registry |
| `delta.enableChangeDataFeed` error | CDF not enabled. Run `ALTER TABLE` in SQL editor |
| VS index not becoming READY | Check status in Catalog Explorer. Ensure endpoint is ONLINE |
| `couldn't get a connection after 30 sec` | Lakebase SP permissions missing. Run `uv run grant-sp-permissions` and restart app |
| `checkpoint_migrations` duplicate key | Harmless on first startup (concurrent init). Auto-recovered on retry |
| `tool_use without tool_result` | Corrupted checkpoint. Auto-recovered by deleting checkpoint and retrying |
| `302 redirect when querying deployed agent` | Use OAuth token, not PAT. Run `databricks auth token` |
| 502 Bad Gateway after deploy | Frontend npm build takes 3-5 minutes. Wait and retry |
| `bundle deploy` resource errors | Update Databricks CLI to v0.297+ (`brew upgrade databricks`) |
| Apps UI shows empty resources | CLI too old. v0.297+ correctly reflects resource bindings |

---

## FAQ

**Q: Can I use a different LLM?**
Yes. Change `LLM_ENDPOINT_NAME` in `agent_server/agent.py` to any Foundation Model API endpoint (e.g., `databricks-meta-llama-3-3-70b-instruct`).

**Q: Can I add my own tools?**
Yes. Add UC Functions, Genie Spaces, Vector Search Indexes, or custom MCP servers. See the [Agent Framework Tools docs](https://docs.databricks.com/aws/en/generative-ai/agent-framework/agent-tool).

**Q: How does On-Behalf-Of (OBO) auth work?**
Use `get_user_workspace_client()` from `agent_server.utils` to authenticate as the requesting user instead of the app service principal. See [OBO docs](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth).

**Q: How do I add custom tracing?**
MLflow autologging captures LLM calls automatically. Add custom spans with `@mlflow.trace` or the MLflow tracing API. See [MLflow tracing docs](https://docs.databricks.com/aws/en/mlflow3/genai/tracing/app-instrumentation/).

---

## Cleanup

To delete all resources created during the workshop:

```bash
uv run cleanup
```

Interactively deletes: Databricks App, MLflow Experiments, Vector Search, Genie Space, Lakebase, schema, workspace bundle files, and local files. See [Resource Cleanup](WORKSHOP_INSTRUCTIONS.md#resource-cleanup) in WORKSHOP_INSTRUCTIONS.md for details.

---

## Resources

- [Databricks Agent Framework](https://docs.databricks.com/aws/en/generative-ai/agent-framework/)
- [MLflow ResponsesAgent](https://mlflow.org/docs/latest/genai/flavors/responses-agent-intro/)
- [Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/)
- [Lakebase Documentation](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/lakebase)
- [MCP on Databricks](https://docs.databricks.com/aws/en/generative-ai/agent-framework/agent-tool)
- [LangGraph Documentation](https://docs.langchain.com/oss/python/langgraph/quickstart)
