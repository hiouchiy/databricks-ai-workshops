# フレッシュマート AI エージェント — アーキテクチャガイド

このドキュメントでは、アプリケーションの構成要素、それぞれの役割、コンポーネント間の接続方法を解説します。

---

## 全体像

```
┌──────────────────────────────────────────────────────────────┐
│                    Databricks Apps 環境                       │
│                                                              │
│  ┌──────────────────────┐    ┌──────────────────────────┐   │
│  │   Express サーバー     │    │   FastAPI サーバー         │   │
│  │   (Node.js)          │    │   (Python/Uvicorn)       │   │
│  │                      │    │                          │   │
│  │  ・React UI を配信    │    │  ・AI エージェント本体     │   │
│  │  ・OAuth 認証         │◄──►│  ・LLM 呼び出し           │   │
│  │  ・チャット履歴 DB     │    │  ・ツール実行             │   │
│  │  ・API リクエスト中継  │    │  ・メモリ管理             │   │
│  │                      │    │                          │   │
│  │  localhost:3000       │    │  localhost:8000          │   │
│  └──────┬───────────────┘    └──────────┬───────────────┘   │
│         │                               │                    │
│         │ 外部公開ポート                │ 内部のみ             │
│         ▼                               ▼                    │
│  ユーザーのブラウザ               Databricks サービス群       │
│  (HTTPS)                        (HTTPS API)                 │
└──────────────────────────────────────────────────────────────┘
```

---

## コンポーネント一覧

### 1. React フロントエンド（ブラウザで実行）

| 項目 | 内容 |
|------|------|
| **技術** | React + TypeScript + Vite |
| **役割** | チャット画面の UI。メッセージ表示、入力フォーム、ツール実行状況の可視化 |
| **実行場所** | ユーザーのブラウザ内 |
| **ソースコード** | `e2e-chatbot-app-next/client/` |

#### React とは何か？（フロントエンド素人向け）

React は **JavaScript のライブラリ** です。HTML ではありません。従来の Web アプリはサーバーが完成した HTML を返しますが、React ではサーバーは**ほぼ空の HTML と JavaScript ファイル**を返し、**ブラウザ内で JavaScript が画面を組み立てます**。

```
ビルド時（npm run build）:
  React のソースコード（.tsx）
    ↓ Vite（ビルドツール）がコンパイル・バンドル
  静的ファイル一式:
    ├── index.html          ← 骨格だけの HTML（中身はほぼ空）
    ├── index-B-YFnQIj.js   ← React の全ロジック（JavaScript）
    └── index-Cfgi24Rp.css  ← スタイルシート

ブラウザがアクセスした時:
  1. Express が index.html を返す
  2. ブラウザが index.html を読み込む:
     <html>
       <body>
         <div id="root"></div>              ← 空のコンテナ
         <script src="index-B-YFnQIj.js">  ← JavaScript を読み込む
       </body>
     </html>
  3. JavaScript（React）がブラウザ内で実行され、
     <div id="root"> の中にチャット画面を動的に生成
  4. 以降、ユーザーの操作（メッセージ送信等）は
     JavaScript が API リクエストを送り、画面を更新
     （ページ遷移なし＝サクサク動く）
```

| | 従来の Web アプリ | React（このアプリ） |
|---|---|---|
| サーバーが返すもの | 完成した HTML | ほぼ空の HTML + JavaScript |
| 画面の描画 | サーバー側 | ブラウザ側（JavaScript） |
| ページ遷移 | 毎回サーバーにリクエスト | JavaScript が画面を書き換え（遷移なし） |

### 2. Express サーバー（フロントエンドのバックエンド）

| 項目 | 内容 |
|------|------|
| **技術** | Express.js（Node.js の Web フレームワーク） |
| **ポート** | `3000`（外部公開） |
| **役割** | React UI の配信、OAuth 認証、チャット履歴の DB 管理、API リクエストの中継 |
| **ソースコード** | `e2e-chatbot-app-next/server/` |

Express は **Python の FastAPI に相当する Node.js の Web サーバー** です。1つのサーバーで**2つの役割**を兼ねています：

**役割 1: 静的ファイルサーバー（React の配信）**
`npm run build` で生成された HTML/JS/CSS をブラウザに返します。

**役割 2: API サーバー（認証・履歴・中継）**
認証、チャット履歴の DB 管理、FastAPI へのリクエスト中継を行います。

```
Express サーバー (localhost:3000) が処理するリクエスト:

  GET /                → index.html を返す（React の起点）
  GET /assets/*.js     → React の JavaScript を返す
  GET /assets/*.css    → スタイルシートを返す
  GET /favicon.ico     → アイコンを返す

  GET /api/session     → 認証情報を返す（Express 自身が処理）
  GET /api/history     → チャット履歴を返す（Express → Lakebase）
  POST /api/chat       → チャットリクエスト（Express → FastAPI に中継）

  POST /invocations    → FastAPI に直接中継（プロキシ）
```

> **なぜ Express が必要か？** React の配信だけなら Nginx 等の静的サーバーでも可能ですが、このアプリでは Databricks OAuth 認証・チャット履歴 DB・API 中継も必要なため、Express が窓口を一手に引き受けています。

### 3. FastAPI / MLflow AgentServer（エージェントバックエンド）

| 項目 | 内容 |
|------|------|
| **技術** | FastAPI + Uvicorn（Python の非同期 Web サーバー）、MLflow AgentServer でラップ |
| **ポート** | `8000`（内部。Express から `localhost:8000` で接続） |
| **役割** | AI エージェント本体。LLM 呼び出し、ツール実行、メモリ管理 |
| **ソースコード** | `agent_server/agent.py`, `agent_server/start_server.py` |
| **API** | OpenAI Responses API 互換（`POST /invocations`） |

#### FastAPI と Uvicorn の違い（素人向け）

どちらも「Web サーバー」と呼ばれることがありますが、役割が違います。レストランに例えると：

```
Uvicorn = レストランの建物（お客さんが入ってくるドア、テーブル、配膳の仕組み）
FastAPI = シェフとレシピ（注文に応じて料理を作るロジック）
```

| | Uvicorn | FastAPI |
|---|---|---|
| **何者？** | ASGI サーバー（通信基盤） | Web フレームワーク（アプリロジック） |
| **やること** | ネットワーク接続の管理、HTTP リクエストの受信・レスポンスの送信 | URL ごとの処理の定義（`/invocations` が来たら何をするか） |
| **例えると** | 郵便局（手紙を届ける仕組み） | 手紙を読んで返事を書く人 |
| **単体で動く？** | 動くが、何を返すか分からない | 動かない（Uvicorn が必要） |

```
リクエストの流れ:

  HTTP リクエスト ("POST /invocations")
    ↓
  Uvicorn が受け取る（ネットワーク処理）
    ↓
  FastAPI に渡す（「/invocations のハンドラを呼んで」）
    ↓
  FastAPI のハンドラが実行（agent.py の invoke_handler）
    ↓
  レスポンスを Uvicorn に返す
    ↓
  Uvicorn がブラウザ/クライアントに送信
```

このアプリでは、さらに **MLflow の AgentServer** が FastAPI アプリを自動生成しています：

```
MLflow AgentServer
  └── FastAPI アプリを生成
        ├── POST /invocations  ← @invoke() で登録したハンドラ
        ├── POST /invocations (streaming) ← @stream() で登録したハンドラ
        ├── GET /health
        └── GET /docs（自動生成 API ドキュメント）
              ↓
        Uvicorn で起動（ポート 8000）
```

つまり、開発者（あなた）が書くのは `@invoke()` と `@stream()` の中身だけ。サーバーの設定・起動・ルーティングは MLflow + FastAPI + Uvicorn が全て面倒を見てくれます。

### 4. LangGraph エージェント（agent.py 内）

| 項目 | 内容 |
|------|------|
| **技術** | LangGraph（LangChain のステートフルエージェントフレームワーク） |
| **役割** | ツール選択・実行のオーケストレーション |

LangGraph は「LLM にどのツールを使うか判断させ、ツールを実行し、結果を LLM に返し、最終回答を生成する」ループを管理します。これは FastAPI サーバーの中で動く Python ライブラリであり、独立したサーバーではありません。

---

## コンポーネント間の接続

### リクエストの流れ（ユーザーがチャットで質問した場合）

```
1. ブラウザ（React）
   │  ユーザーが「返品ポリシーを教えて」と入力
   │
   ▼ HTTPS（外部ネットワーク）
2. Express サーバー (localhost:3000)
   │  ・OAuth 認証を確認
   │  ・リクエストを FastAPI に中継
   │
   ▼ HTTP（localhost — 同一マシン内通信）
3. FastAPI サーバー (localhost:8000)
   │  ・POST /invocations を受信
   │  ・LangGraph エージェントを起動
   │
   ▼ 関数呼び出し（同一プロセス内）
4. LangGraph エージェント
   │  ・Claude LLM に質問を送信
   │  ・Claude: 「policy_search ツールを使ってください」
   │
   ▼ HTTPS（外部 API 呼び出し）
5. 外部サービス
   ├── Claude LLM（Foundation Model API）
   ├── Vector Search（ポリシー文書検索）
   ├── Genie MCP（構造化データクエリ）
   └── Lakebase（メモリ読み書き）
   │
   ▼ 逆順で結果が返る
6. ブラウザに回答が表示される
```

### ポートとネットワーク

| ポート | コンポーネント | 外部からアクセス | 用途 |
|--------|--------------|----------------|------|
| **3000** | Express | **はい**（Databricks Apps の公開 URL） | UI 配信 + API 中継 |
| **8000** | FastAPI | **いいえ**（localhost のみ） | エージェント API |

Databricks Apps 環境では、外部からのリクエストは**ポート 8000 に直接ルーティング**されます（Apps のリバースプロキシ設定）。Express は **ポート 3000 で起動し、`API_PROXY=http://localhost:8000/invocations` 環境変数**で FastAPI にリクエストを中継します。

> **重要:** ユーザーのブラウザから `localhost:8000` に直接アクセスすることはありません。すべてのリクエストは Express（3000）を経由します。ただし、`curl` でテストする場合は直接 `localhost:8000/invocations` に POST できます。

### 認証の流れ

```
ブラウザ → Databricks OAuth → Express（認証済みユーザー情報を取得）
                                  │
                                  ├── ローカル開発: SCIM API でユーザー情報取得
                                  │   （databricks auth login で取得したトークンを使用）
                                  │
                                  └── Apps 環境: X-Forwarded-User ヘッダー
                                      （Databricks Apps が自動付与）
```

FastAPI（エージェント）側では、Express が付与した `user_id` をリクエストの `context` から読み取り、メモリの名前空間として使用します。

---

## ローカル開発 vs Apps デプロイ

| 項目 | ローカル（`uv run start-app`） | Apps（`databricks apps deploy`） |
|------|---|---|
| Express 起動 | `npm run start` | `npm run start`（自動クローン + ビルド） |
| FastAPI 起動 | `uv run start-server` | `uv run start-server` |
| 認証 | Databricks CLI トークン + SCIM API | Databricks OAuth + X-Forwarded ヘッダー |
| チャット履歴 DB | Lakebase（`.env` の PGHOST） | Lakebase（同じ接続先） |
| 環境変数 | `.env` ファイルから読み込み | `app.yaml` の `env` セクションから注入 |
| 外部アクセス | `http://localhost:3000` | `https://<app-name>-<workspace-id>.aws.databricksapps.com` |

---

## `start_app.py` の動作

`uv run start-app` を実行すると `scripts/start_app.py` が以下を行います：

```
1. .env を読み込む
2. e2e-chatbot-app-next/ が存在するか確認
   ├── 存在する → そのまま使う
   └── 存在しない → GitHub から自動クローン
3. バックエンド起動: uv run start-server (ポート 8000)
4. フロントエンド:
   ├── npm install（依存関係インストール）
   ├── npm run build（React のビルド）
   └── npm run start（Express サーバー起動、ポート 3000）
5. 両方の起動を監視し、READY になったら通知
```

### `--no-ui` モード

```bash
uv run start-app --no-ui
```

フロントエンド（Express + React）を起動せず、**バックエンド（FastAPI）のみ**起動します。

| 項目 | 通常モード | `--no-ui` モード |
|------|---|---|
| Express (3000) | 起動する | **起動しない** |
| FastAPI (8000) | 起動する | 起動する |
| チャット画面 | 使える | **使えない** |
| `curl` テスト | 使える | 使える |
| 用途 | 通常利用 | API テスト、評価スクリプト実行時 |

> **注意:** `--no-ui` はあくまで**起動時**のオプションです。`databricks bundle deploy` によるソースコードのアップロードには影響しません。`e2e-chatbot-app-next/` のソースコード自体は常にワークスペースに同期されます（`node_modules/` のみ `.databricksignore` で除外）。

---

## ツール接続方式

```
LangGraph エージェント
├── Genie（MCP 経由）
│     └── HTTPS → Databricks MCP API → Genie Space → SQL Warehouse → データ
│
├── Code Interpreter（MCP 経由）
│     └── HTTPS → Databricks MCP API → Python 実行環境
│
├── Vector Search（ネイティブ）
│     └── DatabricksVectorSearch → HTTPS → Vector Search API → インデックス
│     ※ MCP ではなくネイティブ実装を使用（RETRIEVER スパン生成のため）
│
├── メモリ（7ツール、Lakebase 直接接続）
│     └── psycopg（PostgreSQL クライアント） → TCP → Lakebase
│
└── LLM（Claude）
      └── HTTPS → Foundation Model API → Claude Sonnet 4.5
```

### なぜ Vector Search だけネイティブなのか？

MCP 経由で Vector Search を呼ぶと、MLflow のスパンタイプが `TOOL` になります。`DatabricksVectorSearch` をネイティブで使うと `RETRIEVER` スパンが自動生成され、MLflow の `RetrievalSufficiency` スコアラーで**検索品質の評価**が可能になります。

---

## メモリの仕組み

### Short-term Memory（会話ステート）

```
AsyncCheckpointSaver → Lakebase（PostgreSQL）
```

LangGraph の各ステップ後に会話の状態を自動保存。`thread_id` で識別。同じチャットスレッド内で過去のメッセージ・ツール実行結果を復元します。

### Long-term Memory（ユーザー記憶）

```
AsyncDatabricksStore → Lakebase（PostgreSQL）+ Embedding（databricks-qwen3-embedding-0-6b）
```

7つのメモリツールで、ユーザーの好み・タスク履歴・会話サマリーを保存。セマンティック検索で関連記憶を呼び出します。`user_id` の名前空間で分離。

---

## トレースとモニタリング

```
エージェントの処理
  │
  ├── mlflow.langchain.autolog() が自動トレース
  │
  ▼
MLflow Experiment（デフォルト）
  └── Experiments UI でトレース確認

  または

Unity Catalog Delta Table（オプション）
  ├── MLFLOW_TRACING_DESTINATION を設定
  ├── set_experiment_trace_location() で紐付け（ノートブックで1回実行）
  └── SQL でクエリ可能、長期保持
```

### 評価

| コマンド | 方式 | サーバー |
|---|---|---|
| `uv run agent-evaluate` | ConversationSimulator（マルチターン） | 不要 |
| `uv run agent-evaluate-advanced` | ConversationSimulator + カスタムスコアラー | 不要 |
| `uv run agent-evaluate-chat` | expected_facts（固定質問） | 不要 |

> 評価スクリプトはエージェントを直接関数呼び出しするため、サーバーの起動は不要です。実行前にアプリを停止してください（ポート競合回避）。

---

## ファイル構成と役割

```
advanced/
├── agent_server/
│   ├── agent.py           ← AI エージェント本体（LangGraph + ツール + プロンプト）
│   ├── utils_memory.py    ← 7つのメモリツール
│   ├── utils.py           ← 認証・スレッド管理
│   ├── start_server.py    ← MLflow AgentServer 起動スクリプト
│   └── evaluate_*.py      ← 評価スクリプト群
│
├── e2e-chatbot-app-next/  ← フロントエンド（React + Express）
│   ├── client/            ← React UI ソースコード
│   ├── server/            ← Express サーバーソースコード
│   └── packages/          ← 共有ライブラリ（認証、DB、AI SDK）
│
├── scripts/
│   ├── quickstart.py      ← 対話式セットアップウィザード
│   ├── start_app.py       ← フロントエンド + バックエンドの起動管理
│   ├── cleanup.py         ← リソース一括削除
│   └── register_prompt.py ← Prompt Registry への登録
│
├── app.yaml               ← Databricks Apps の設定（コマンド、環境変数）
├── databricks.yml         ← Databricks Asset Bundle の設定（リソース定義）
├── workshop_setup.py      ← Databricks ノートブック（SQL/Python セットアップ）
└── .env.example           ← 環境変数テンプレート
```
