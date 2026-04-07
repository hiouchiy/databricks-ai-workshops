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
│   ├── grant_lakebase_permissions.py
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
| **トレーシング・評価** | MLflow 3（自動ログ、9 種のスコアラー、会話シミュレーター） |
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
  - Lakebase
  - Databricks Apps
- **ローカルツール**：
  - [uv](https://docs.astral.sh/uv/getting-started/installation/)（Python パッケージマネージャー）
  - [nvm](https://github.com/nvm-sh/nvm) + Node.js 20 LTS
  - [Databricks CLI](https://docs.databricks.com/aws/en/dev-tools/cli/install)
- **任意**：[Claude Code](https://docs.anthropic.com/en/docs/claude-code)（AI 支援開発用）

---

## はじめ方

### 方法 1：クイックスタート（推奨）

```bash
# リポジトリをクローン
git clone https://github.com/hiouchiy/databricks-ai-workshops.git
cd databricks-ai-workshops

# 対話式セットアップウィザードを実行
uv run quickstart
```

クイックスタートスクリプトが以下を実行します：
1. `uv`、`nvm`、Databricks CLI のインストールを確認
2. Databricks OAuth 認証を設定
3. MLflow 実験を2つ作成・リンク（モニタリング用 + 評価用）
4. メモリストレージ用に Lakebase を設定
5. `.env` ファイルを生成
6. エージェントサーバーとチャットアプリを起動

セットアップ完了後は、いつでも以下で起動できます：

```bash
uv run start-app
```

チャット UI は **http://localhost:3000** 、API は **http://localhost:8000** でアクセスできます。

### 方法 2：Claude Code を使う

[Claude Code](https://docs.anthropic.com/en/docs/claude-code) がインストール済みであれば、`.claude/skills/` に AI 支援開発用のスキルが同梱されています。

#### 前提条件

Claude Code を使う前に、Databricks ワークスペースで以下のリソースを手動で作成してください：

1. **Databricks CLI プロファイル** — `databricks auth login` で設定
2. **MLflow 実験** — UI または CLI で作成
3. **Genie Space** — 作成してスペース ID を控える
4. **Vector Search インデックス** — 作成してフルネームを控える（`catalog.schema.index_name`）
5. **Prompt Registry** — システムプロンプトを登録（`catalog.schema.prompt_name`）
6. **Lakebase オートスケーリングインスタンス** — プロジェクトとブランチを作成

#### ローカル開発

```bash
# プロジェクトディレクトリで Claude Code を起動
cd databricks-ai-workshops/advanced
claude
```

以下のプロンプトを使用します（プレースホルダーを実際の値に置き換えてください）：

```
Set up and run the agent app locally. I have already created the following
resources manually:

- Databricks CLI profile: <PROFILE_NAME>
- MLflow Experiment ID: <EXPERIMENT_ID>
- Genie Space ID: <GENIE_SPACE_ID>
- Vector Search Index: <CATALOG>.<SCHEMA>.<INDEX_NAME>
- Prompt Registry: <CATALOG>.<SCHEMA>.<PROMPT_NAME>
- Lakebase Autoscaling Project: <PROJECT_NAME>
- Lakebase Autoscaling Branch: <BRANCH_NAME>

Steps:
1. Update .env with all the above values (resolve PGHOST from the autoscaling
   branch endpoint)
2. Run `uv run start-app` and verify both frontend (port 3000) and backend
   (port 8000) are healthy
3. Smoke test the agent with a curl POST to /invocations
```

チャット UI は **http://localhost:3000**、API は **http://localhost:8000** でアクセスできます。

#### Databricks Apps へのデプロイ

ローカルでアプリの動作を確認したら、以下のプロンプトでデプロイします：

```
Deploy the agent app to Databricks Apps. I have the following resources:

- Databricks CLI profile: <PROFILE_NAME>
- MLflow Experiment ID: <EXPERIMENT_ID>
- Genie Space ID: <GENIE_SPACE_ID>
- Vector Search Index: <CATALOG>.<SCHEMA>.<INDEX_NAME>
- Prompt Registry: <CATALOG>.<SCHEMA>.<PROMPT_NAME>
- Lakebase Autoscaling Project: <PROJECT_NAME>
- Lakebase Autoscaling Branch: <BRANCH_NAME>

Steps:
1. Update databricks.yml with all the above resource IDs (replace all
   <placeholder> values)
2. Run `databricks bundle deploy -p <PROFILE_NAME>` to deploy the bundle
3. Run `databricks apps start retail-grocery-ltm-memory -p <PROFILE_NAME>`
   to start the app
4. Verify the app is running and share the app URL
```

### 方法 3：手動セットアップ

ステップバイステップの詳細手順は **[ワークショップインストラクション](WORKSHOP_INSTRUCTIONS.md)** を参照してください。データ生成・Vector Search 作成・Lakebase セットアップ・評価・デプロイまで、全手順が記載されています。

---

## ワークショップの詳細手順

**[WORKSHOP_INSTRUCTIONS.md](WORKSHOP_INSTRUCTIONS.md)** にステップバイステップの実施手順があります：

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

詳細は [WORKSHOP_INSTRUCTIONS.md](WORKSHOP_INSTRUCTIONS.md) のステップ 10 を参照してください。

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

詳細な手順は [WORKSHOP_INSTRUCTIONS.md](WORKSHOP_INSTRUCTIONS.md) のステップ 11 を参照してください。

---

## トラブルシューティング

| 問題 | 解決策 |
|------|--------|
| `Lakebase configuration is required` | `.env` に `LAKEBASE_AUTOSCALING_PROJECT` と `LAKEBASE_AUTOSCALING_BRANCH`（またはプロビジョニング済みの場合は `LAKEBASE_INSTANCE_NAME`）を設定 |
| `302 redirect when querying deployed agent` | PAT ではなく OAuth トークンを使用。`databricks auth token` を実行 |
| `Permission denied on Lakebase` | `uv run python scripts/grant_lakebase_permissions.py` を実行 |
| `Streaming 200 OK but error in stream` | 想定どおり — 200 はストリーム確立を示す。エラー内容を確認 |
| `GENIE_SPACE_ID not set` | `.env` に設定するか `uv run quickstart` で指定 |
| `nvm: command not found` | nvm をインストール：`curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh \| bash` |

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

A **FreshMart Grocery Shopping Assistant** that can:

| Capability | Powered By | Description |
|---|---|---|
| **Structured data queries** | Genie Space (MCP) | Query customer accounts, products, transactions, stores via natural language to SQL |
| **Policy document lookup** | Vector Search (MCP) | RAG over store policies — returns, memberships, delivery, recalls, privacy |
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
│   └── grant_lakebase_permissions.py
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
| **Tool Protocol** | MCP (Model Context Protocol) — Genie, Vector Search, Code Interpreter |
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
  - Lakebase
  - Databricks Apps
- **Local tools**:
  - [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)
  - [nvm](https://github.com/nvm-sh/nvm) + Node.js 20 LTS
  - [Databricks CLI](https://docs.databricks.com/aws/en/dev-tools/cli/install)
- **Optional**: [Claude Code](https://docs.anthropic.com/en/docs/claude-code) for AI-assisted development

---

## Getting Started

### Option 1: Quick Start (Recommended)

```bash
# Clone the repository
git clone https://github.com/hiouchiy/databricks-ai-workshops.git
cd databricks-ai-workshops

# Run the interactive setup wizard
uv run quickstart
```

The quickstart script will:
1. Verify `uv`, `nvm`, and Databricks CLI installations
2. Configure Databricks OAuth authentication
3. Create and link two MLflow experiments (monitoring + evaluation)
4. Configure Lakebase for memory storage
5. Generate your `.env` file
6. Start the agent server and chat app

After setup, start the app anytime with:

```bash
uv run start-app
```

The chat UI will be available at **http://localhost:3000** and the API at **http://localhost:8000**.

### Option 2: Using Claude Code

If you have [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed, the repository includes built-in skills in `.claude/skills/` for AI-assisted development.

#### Prerequisites

Before using Claude Code, create the following resources manually in your Databricks workspace:

1. **Databricks CLI profile** — Run `databricks auth login` to configure
2. **MLflow Experiment** — Create via UI or CLI
3. **Genie Space** — Create and note the Space ID
4. **Vector Search Index** — Create and note the full name (`catalog.schema.index_name`)
5. **Prompt Registry** — Register your system prompt (`catalog.schema.prompt_name`)
6. **Lakebase Autoscaling Instance** — Create a project and branch

#### Local Development

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
- MLflow Experiment ID: <EXPERIMENT_ID>
- Genie Space ID: <GENIE_SPACE_ID>
- Vector Search Index: <CATALOG>.<SCHEMA>.<INDEX_NAME>
- Prompt Registry: <CATALOG>.<SCHEMA>.<PROMPT_NAME>
- Lakebase Autoscaling Project: <PROJECT_NAME>
- Lakebase Autoscaling Branch: <BRANCH_NAME>

Steps:
1. Update .env with all the above values (resolve PGHOST from the autoscaling
   branch endpoint)
2. Run `uv run start-app` and verify both frontend (port 3000) and backend
   (port 8000) are healthy
3. Smoke test the agent with a curl POST to /invocations
```

The chat UI will be available at **http://localhost:3000** and the API at **http://localhost:8000**.

#### Deploy to Databricks Apps

Once you've verified the app works locally, use this prompt to deploy:

```
Deploy the agent app to Databricks Apps. I have the following resources:

- Databricks CLI profile: <PROFILE_NAME>
- MLflow Experiment ID: <EXPERIMENT_ID>
- Genie Space ID: <GENIE_SPACE_ID>
- Vector Search Index: <CATALOG>.<SCHEMA>.<INDEX_NAME>
- Prompt Registry: <CATALOG>.<SCHEMA>.<PROMPT_NAME>
- Lakebase Autoscaling Project: <PROJECT_NAME>
- Lakebase Autoscaling Branch: <BRANCH_NAME>

Steps:
1. Update databricks.yml with all the above resource IDs (replace all
   <placeholder> values)
2. Run `databricks bundle deploy -p <PROFILE_NAME>` to deploy the bundle
3. Run `databricks apps start retail-grocery-ltm-memory -p <PROFILE_NAME>`
   to start the app
4. Verify the app is running and share the app URL
```

### Option 3: Manual Setup

1. **Install dependencies**

   ```bash
   # Python
   uv sync

   # Node.js (for chat UI)
   nvm use 20
   cd e2e-chatbot-app-next && npm install && cd ..
   ```

2. **Authenticate with Databricks**

   ```bash
   databricks auth login
   ```

   Set your profile in `.env`:
   ```
   DATABRICKS_CONFIG_PROFILE=DEFAULT
   ```

3. **Create MLflow experiments** (monitoring + evaluation)

   ```bash
   DATABRICKS_USERNAME=$(databricks current-user me | jq -r .userName)

   # Monitoring (app runtime tracing)
   databricks experiments create-experiment /Users/$DATABRICKS_USERNAME/freshmart-agent-monitoring

   # Evaluation (evaluation scripts)
   databricks experiments create-experiment /Users/$DATABRICKS_USERNAME/freshmart-agent-evaluation
   ```

4. **Configure environment variables**

   ```bash
   cp .env.example .env
   # Edit .env with MLFLOW_EXPERIMENT_ID (monitoring), MLFLOW_EVAL_EXPERIMENT_ID (evaluation),
   # Lakebase instance, Genie space ID, Vector Search index
   ```

5. **Start the application**

   ```bash
   uv run start-app
   ```

---

## Workshop Modules

### Module 1: Understanding the Agent Architecture

Explore how the agent is built:
- **`agent_server/agent.py`** — The core agent with system prompt, MCP tool initialization, and LangGraph orchestration
- **`agent_server/utils_memory.py`** — Seven memory tools for persistent user preferences and conversation history
- **`agent_server/utils.py`** — Authentication helpers, thread management, streaming utilities

### Module 2: Working with MCP Tools

The agent connects to three MCP (Model Context Protocol) servers:

| MCP Server | Purpose | Endpoint |
|---|---|---|
| `system-ai` | Code Interpreter (Python execution) | `/api/2.0/mcp/functions/system/ai` |
| `retail-grocery-genie` | Natural language to SQL queries | `/api/2.0/mcp/genie/{GENIE_SPACE_ID}` |
| `retail-policy-docs` | RAG over policy documents | `/api/2.0/mcp/vector-search/{INDEX}` |

### Module 3: Long-Term Memory with Lakebase

The memory system uses Lakebase (PostgreSQL) with semantic embeddings:

| Tool | Function | Use Case |
|---|---|---|
| `get_user_memory` | Semantic search on user memories | "What are my dietary preferences?" |
| `save_user_memory` | Persist user info | User says "I'm vegetarian" |
| `delete_user_memory` | Remove specific memories | "Forget my address" |
| `save_task_summary` | Record completed tasks (silent) | After answering a product question |
| `search_task_history` | Query past tasks | "What did you help me with last time?" |
| `save_conversation_summary` | Record conversation end-state (silent) | When user says goodbye |
| `search_past_conversations` | Find previous interactions | "What have we talked about?" |

### Module 4: Evaluating the Agent

Run the evaluation suite with 10 MLflow scorers:

```bash
uv run agent-evaluate
```

**Scorers**: Completeness, ConversationalSafety, ConversationCompleteness, Fluency, KnowledgeRetention, RelevanceToQuery, Safety, ToolCallCorrectness, UserFrustration

### Module 5: Deploying to Databricks Apps

```bash
# Create the app
databricks apps create retail-grocery-ltm-memory

# Sync code to workspace
DATABRICKS_USERNAME=$(databricks current-user me | jq -r .userName)
databricks sync . "/Users/$DATABRICKS_USERNAME/retail-grocery-ltm-memory"

# Deploy
databricks apps deploy retail-grocery-ltm-memory \
  --source-code-path /Workspace/Users/$DATABRICKS_USERNAME/retail-grocery-ltm-memory
```

See [Deploying to Databricks Apps](#deploying-to-databricks-apps-1) for full instructions including Lakebase permissions.

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

## Modifying Your Agent

### Change the LLM

Edit `LLM_ENDPOINT_NAME` in `agent_server/agent.py`:

```python
LLM_ENDPOINT_NAME = "databricks-claude-sonnet-4-5"  # or any Foundation Model API endpoint
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

1. **Create the app**:
   ```bash
   databricks apps create retail-grocery-ltm-memory
   ```

2. **Add resources** via the Databricks UI (App > Edit > App Resources):
   - MLflow Experiment (CAN_MANAGE)
   - Genie Space (CAN_RUN)
   - Lakebase Instance (CAN_CONNECT_AND_CREATE)
   - Vector Search Index (SELECT)

3. **Grant Lakebase permissions** to the app's service principal:
   ```bash
   uv run python scripts/grant_lakebase_permissions.py
   ```

4. **Sync and deploy**:
   ```bash
   DATABRICKS_USERNAME=$(databricks current-user me | jq -r .userName)
   databricks sync . "/Users/$DATABRICKS_USERNAME/retail-grocery-ltm-memory"
   databricks apps deploy retail-grocery-ltm-memory \
     --source-code-path /Workspace/Users/$DATABRICKS_USERNAME/retail-grocery-ltm-memory
   ```

5. **Query the deployed agent** (requires OAuth token):
   ```bash
   databricks auth token  # copy the token
   curl -X POST <app-url>.databricksapps.com/invocations \
     -H "Authorization: Bearer <oauth-token>" \
     -H "Content-Type: application/json" \
     -d '{"input": [{"role": "user", "content": "hi"}], "stream": true}'
   ```

---

## Troubleshooting

| Issue | Solution |
|---|---|
| `Lakebase configuration is required` | Set `LAKEBASE_AUTOSCALING_PROJECT` + `LAKEBASE_AUTOSCALING_BRANCH` (or `LAKEBASE_INSTANCE_NAME` for provisioned) in `.env` |
| `302 redirect when querying deployed agent` | Use OAuth token, not PAT. Run `databricks auth token` |
| `Permission denied on Lakebase` | Run `uv run python scripts/grant_lakebase_permissions.py` |
| `Streaming 200 OK but error in stream` | Expected — 200 confirms stream setup; check the error content |
| `GENIE_SPACE_ID not set` | Set in `.env` or pass via `uv run quickstart` |
| `nvm: command not found` | Install nvm: `curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh \| bash` |

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

## Resources

- [Databricks Agent Framework](https://docs.databricks.com/aws/en/generative-ai/agent-framework/)
- [MLflow ResponsesAgent](https://mlflow.org/docs/latest/genai/flavors/responses-agent-intro/)
- [Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/)
- [Lakebase Documentation](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/lakebase)
- [MCP on Databricks](https://docs.databricks.com/aws/en/generative-ai/agent-framework/agent-tool)
- [LangGraph Documentation](https://docs.langchain.com/oss/python/langgraph/quickstart)
