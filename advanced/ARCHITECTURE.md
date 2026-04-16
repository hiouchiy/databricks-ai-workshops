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

#### FastAPI と Uvicorn はいつもセット？

ほぼ毎回セットです。コードで見ると違いが分かります：

```python
# ── FastAPI が担当する部分（「何をするか」の定義）──

from fastapi import FastAPI
app = FastAPI()

@app.post("/invocations")          # ← 「/invocations に POST が来たら」
async def handle(request):         # ← 「この関数を実行する」
    answer = await ask_llm(request)
    return {"output": answer}

# この時点では、まだサーバーは起動していない。
# 「レシピは書いたが、レストランはまだ開店していない」状態。
```

```bash
# ── Uvicorn が担当する部分（「サーバーを起動する」）──

uvicorn main:app --port 8000

# Uvicorn が以下を行う：
#   1. ポート 8000 でネットワーク接続を待ち受け開始
#   2. HTTP リクエストが来たら FastAPI に渡す
#   3. FastAPI の戻り値をクライアントに返す
#
# 「レストランを開店して、お客さんを受け入れる」役割。
```

```python
# ── このアプリの実際のコード（start_server.py）──

from mlflow.genai.agent_server import AgentServer

agent_server = AgentServer("ResponsesAgent")  # ← MLflow が FastAPI アプリを自動生成
app = agent_server.app                         # ← FastAPI アプリ（レシピ集）

def main():
    agent_server.run(app_import_string="agent_server.start_server:app")
    # ↑ 内部で Uvicorn を起動（レストラン開店）
```

Uvicorn の代わりに別の ASGI サーバー（Hypercorn、Daphne 等）も使えますが、Uvicorn が最も一般的で高速なため、ほぼデファクトスタンダードです。

Node.js の世界との対比：

| Python | Node.js | 役割 |
|---|---|---|
| **Uvicorn** | Node.js ランタイム自体 | ネットワーク接続の管理・起動 |
| **FastAPI** | Express | URL ごとの処理を定義 |

Node.js は通信基盤とランタイムが一体なので「Express だけで動く」感覚ですが、Python では通信基盤（Uvicorn）とアプリロジック（FastAPI）が分離しています。差し替え可能な設計ですが、実質いつもセットで使います。

### 4. LangGraph エージェント（agent.py 内）

| 項目 | 内容 |
|------|------|
| **技術** | LangGraph（LangChain のステートフルエージェントフレームワーク） |
| **役割** | ツール選択・実行のオーケストレーション |

LangGraph は「LLM にどのツールを使うか判断させ、ツールを実行し、結果を LLM に返し、最終回答を生成する」ループを管理します。これは FastAPI サーバーの中で動く Python ライブラリであり、独立したサーバーではありません。

---

## 同期と非同期（async/await）の仕組み

このアプリのコードには `async def` や `await` が大量に出てきます。これは「非同期処理」と呼ばれる仕組みで、マルチスレッドとは異なります。

### よくある誤解

> 「async は複数のスレッドで並行処理しているんでしょ？」

**違います。async/await はシングルスレッド（1本の処理ライン）** です。

### レストランで例える

#### マルチスレッド方式（このアプリでは使っていない）

```
お客さん A が注文 → ウェイター A が厨房で待つ（棒立ち）
お客さん B が注文 → ウェイター B が厨房で待つ（棒立ち）
お客さん C が注文 → ウェイター C が厨房で待つ（棒立ち）
```

ウェイター（スレッド）を増やして対応。1000人来たら1000人のウェイターが必要。
メモリ消費が大きく、スレッド間の調整も複雑。

#### async/await 方式（このアプリの方式）

```
お客さん A が注文 → ウェイターが厨房に伝票を出す → すぐ戻る
お客さん B が注文 → ウェイターが厨房に伝票を出す → すぐ戻る
お客さん C が注文 → ウェイターが厨房に伝票を出す → すぐ戻る
   （厨房から「A の料理できた！」）→ ウェイターが A に配膳
   （厨房から「C の料理できた！」）→ ウェイターが C に配膳
```

**ウェイターは1人だけ**。料理ができるまで待たず、他のお客さんの対応に回る。
1000人来てもウェイター1人で捌ける（待ち時間を無駄にしないから）。

### なぜこの方式が有効なのか

このアプリの1リクエストの処理内訳：

```
合計処理時間: 約10秒
  うち CPU を使う時間:    約 0.05秒（JSON パース、文字列操作等）
  うちネットワーク待ち:   約 9.95秒（LLM 応答、VS 検索、Lakebase）
```

**99.5% が「待っているだけ」** です。この「待ち」のためにスレッドを立てるのはメモリの無駄です。async/await なら「待ち」の間にイベントループに制御を返して、他のリクエストを処理できます。

### コードで見る違い

```python
# ── 同期版（ブロッキング）──
def policy_search(query):
    docs = retriever.invoke(query)    # ← ここで 2秒待つ。その間何もできない。
    return format(docs)

# ── 非同期版（ノンブロッキング）──
async def policy_search(query):
    docs = await retriever.ainvoke(query)  # ← 2秒待つが、その間は他の処理ができる。
    return format(docs)
```

`await` は **「結果が来るまで待つけど、その間イベントループは他の仕事をしていいよ」** という意味です。

### このアプリで実際に起きること

```
ユーザー A がチャットを送信（10:00:00）
  → FastAPI が受信
  → await llm.ainvoke()  ← LLM に送信、応答待ち開始
  → 【この間、FastAPI は暇】

ユーザー B がチャットを送信（10:00:01）  ← A の応答がまだ来ていない
  → FastAPI が受信（A を待っている間に処理できる！）
  → await llm.ainvoke()  ← B の LLM 送信

ユーザー A の LLM 応答が到着（10:00:05）
  → A の続きを処理 → 回答を返す

ユーザー B の LLM 応答が到着（10:00:06）
  → B の続きを処理 → 回答を返す
```

もし同期版だったら、A の応答が返るまで B は**待たされます**（10:00:05 まで受け付けすらされない）。

### なぜ policy_search を async にする必要があったか

このアプリで実際にバグが発生した事例です：

```python
# 修正前（同期）— バグの原因
@tool
def policy_search(query: str) -> str:
    docs = _retriever.invoke(query)      # 同期呼び出し — イベントループをブロック
    ...

# 修正後（非同期）— 正常動作
@tool
async def policy_search(query: str) -> str:
    docs = await _retriever.ainvoke(query)  # 非同期呼び出し — 他の処理ができる
    ...
```

LangGraph エージェントは非同期で動いています。その中で呼ばれるツールが同期関数だと、イベントループがブロックされ、**LLM へのメッセージ送信順序が壊れます**（`tool_use` の後に `tool_result` が来ない）。全てのツールを `async def` + `await` で統一することで、メッセージ順序が保たれます。

### まとめ

| | マルチスレッド | async/await（このアプリ） |
|---|---|---|
| スレッド数 | リクエストごとに1本 | **全体で1本** |
| 待ち方 | スレッドがブロック（棒立ち） | イベントループに制御を返す |
| メモリ | スレッドごとに数 MB | ほぼゼロ |
| 1000人同時 | 1000スレッド = 数 GB | 1スレッドのまま |
| 向いている処理 | CPU 重い計算 | **ネットワーク待ちが支配的な処理** ← AI アプリはこっち |

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

このアプリは「誰がチャットしているか」を知る必要があります（メモリをユーザーごとに分離するため）。
認証の仕組みはローカル開発と Apps 環境で異なります。

#### アプリの URL の実態

ユーザーがアクセスする `https://freshmart-agent-hiroshi.databricksapps.com` は、あなたのアプリに直接つながっているわけではありません。**Databricks Apps プラットフォーム**（AWS 上のインフラ）が間に入っています。

```
ユーザーが見ている景色:
  ブラウザ → https://freshmart-agent-hiroshi.databricksapps.com

実態:
  ブラウザ
    ↓ HTTPS
  Databricks Apps プラットフォーム（AWS 上のインフラ）
    ├── DNS: freshmart-agent-hiroshi.databricksapps.com のアドレスを解決
    ├── TLS: HTTPS の暗号化・復号を処理
    ├── OAuth: 未ログインなら Databricks の認証画面にリダイレクト
    ├── リバースプロキシ: 認証済みリクエストにユーザー情報ヘッダーを付与
    ↓ 転送
  アプリのコンテナ（あなたのコード）
    ├── Express (localhost:3000) — UI 配信 + API 中継
    └── FastAPI (localhost:8000) — AI エージェント
```

ユーザーのリクエストは必ず Databricks Apps プラットフォームを経由してからアプリに届きます。認証（OAuth）はプラットフォームが行い、リバースプロキシは認証結果をヘッダーに付けてアプリに転送するだけです。

| コンポーネント | 役割 | 例えると |
|---|---|---|
| **Databricks OAuth** | ログイン画面の表示、パスワード確認、トークン発行 | 身分証明書を発行する窓口 |
| **リバースプロキシ** | 認証済みか確認し、ヘッダーを付けて転送 | ビルの受付でバッジを確認する人 |
| **Express** | ヘッダーからユーザー情報を読むだけ | バッジを見て名前を知る人 |

#### Apps 環境の認証フロー（詳細）

```
1. ユーザーがブラウザでアプリの URL にアクセス
     ↓
2. Databricks Apps プラットフォームが「未ログイン」を検知
     ↓
3. Databricks の OAuth ログイン画面にリダイレクト
     ↓
4. ユーザーがログイン → Databricks がトークンを発行
     ↓
5. リバースプロキシが「この人は認証済み」と判断し、
   HTTP ヘッダーに自動付与してリクエストを転送:

   X-Forwarded-User: 8803475336418960
   X-Forwarded-Email: hiroshi.ouchiyama@databricks.com
   X-Forwarded-Preferred-Username: hiroshi.ouchiyama@databricks.com

     ↓
6. Express がこれらのヘッダーを読み取り、ユーザーを識別
```

**リバースプロキシとは？**

ユーザーとアプリの間に立つ「受付係」です。ユーザーはリバースプロキシと会話しているつもりですが、実際はリバースプロキシが裏にいる本物のサーバーにリクエストを転送しています。

```
ユーザーのブラウザ
  │ 「freshmart-agent-hiroshi.databricksapps.com にアクセス」
  ↓
Databricks Apps のリバースプロキシ（受付係）
  │ 1. このユーザーはログイン済み？ → Yes
  │ 2. ユーザー情報をヘッダーに追加
  │ 3. リクエストを本物のサーバーに転送
  ↓
Express サーバー（localhost:3000）
  │ ヘッダーから「hiroshi.ouchiyama さんですね」と分かる
```

リバースプロキシのおかげで、Express 自身が OAuth のログイン画面を実装する必要がありません。Databricks Apps が認証を代行し、結果だけをヘッダーで教えてくれます。

**X-Forwarded-User とは？**
リバースプロキシが付ける HTTP ヘッダーで、「この人は認証済みですよ」という情報をアプリに伝えるための標準的な仕組みです。`X-` で始まるヘッダーはカスタムヘッダー（標準仕様にない追加情報）を意味します。

#### ローカル開発の場合

```
1. Express が起動時に Databricks CLI のトークンを取得
   （databricks auth login で事前に設定済み）
     ↓
2. Express が SCIM API を呼び出してユーザー情報を取得:

   GET https://<workspace>/api/2.0/preview/scim/v2/Me
   Authorization: Bearer <CLI トークン>

   レスポンス:
   {
     "id": "8803475336418960",
     "userName": "hiroshi.ouchiyama@databricks.com",
     "displayName": "Hiroshi Ouchiyama"
   }
     ↓
3. Express がこの情報をセッションとして保持
```

**SCIM API とは？**
SCIM（System for Cross-domain Identity Management）は、ユーザー情報を管理する標準的な API です。Databricks はこの API を提供しており、「今ログインしているのは誰？」を問い合わせることができます。ローカル開発では Databricks Apps のリバースプロキシがないため、Express が直接 SCIM API を呼んでユーザー情報を取得します。

#### 認証情報がエージェントに届くまで

```
Express（ユーザー情報を取得済み）
  ↓ POST /invocations に user_id を付与
FastAPI（エージェント）
  ↓ request.context.user_id を読み取り
メモリツール
  ↓ ("user_memories", "hiroshi.ouchiyama@databricks.com") の名前空間で検索
Lakebase
  ↓ このユーザーの記憶だけを返す
```

つまり、認証情報は最終的に **メモリの名前空間**（どのユーザーの記憶を読むか）として使われます。

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

## Lakebase 権限の全体像

Lakebase には **2層の権限** があり、それぞれ別の仕組みで付与されます。

```
databricks bundle deploy（デプロイ時に自動）
  ↓
┌────────────────────────────────────────────┐
│ 層1: プロジェクトレベル接続権限              │
│                                            │
│ リソースバインディング（databricks.yml）で   │
│ SP に CAN_CONNECT_AND_CREATE を自動付与     │
│                                            │
│ = 「Lakebase プロジェクトに接続できる」      │
│   だけの権限。テーブルの読み書きはまだ不可   │
└────────────────────────────────────────────┘
  ↓ これだけでは不十分

grant_lakebase_permissions.py（デプロイ後に手動）
  ↓
┌────────────────────────────────────────────┐
│ 層2: PostgreSQL 内部権限                    │
│                                            │
│ LakebaseClient で以下を付与:                │
│  ・ロール作成（create_role）                 │
│  ・スキーマ権限（USAGE + CREATE）            │
│  ・テーブル権限（SELECT, INSERT,             │
│                 UPDATE, DELETE）             │
│                                            │
│ = 「チェックポイントやメモリのテーブルに     │
│    実際に読み書きできる」権限                │
└────────────────────────────────────────────┘
```

### なぜ2層に分かれているか

Lakebase は Databricks のプラットフォーム上に構築された **PostgreSQL データベース** です。

- **層1（プロジェクト接続権限）**: Databricks 側の ACL。「この SP/ユーザーはこのプロジェクトにアクセスしていい」
- **層2（PostgreSQL 内部権限）**: PostgreSQL 側の GRANT。「このロールはこのテーブルを SELECT していい」

この2層は**独立して管理**されており、自動同期はありません。層1だけあっても層2がなければテーブルにアクセスできず、逆もまた然りです。

### 誰にどの権限が必要か

| 対象 | 層1（接続権限） | 層2（DB 内部権限） | いつ付与？ |
|------|---|---|---|
| **アプリの SP** | `databricks.yml` のリソースバインディングで**自動** | `grant_lakebase_permissions.py` で**手動** | デプロイ後 |
| **チームメンバー** | `grant_team_access.py` の `LakebaseClient.create_role` で付与 | 同スクリプトで `grant_schema` + `grant_table` | 代表者が実行 |
| **自分自身（ローカル開発）** | プロジェクト作成者は自動的にアクセス可能 | 自動的にアクセス可能 | 不要 |

---

## メモリの仕組み

このアプリには **2種類のメモリ** があります。人間に例えると：

| | Short-term Memory | Long-term Memory |
|---|---|---|
| 人間で例えると | 今の会話を覚えている（短期記憶） | 「この人はベジタリアン」を覚えている（長期記憶） |
| 消えるタイミング | 新しいチャットを開くと消える | ずっと残る（別の日、別のチャットでも） |
| 保存する人 | LangGraph が**自動**で保存 | エージェントが**明示的**にツールで保存 |

### Short-term Memory（会話ステート）

```
AsyncCheckpointSaver → Lakebase（PostgreSQL）
```

LangGraph が各ステップの後に、会話の**全状態**を自動保存します。

```
ステップ 1: ユーザーが質問
  → チェックポイント保存 ──┐
ステップ 2: LLM が「ツールを使え」と判断     │
  → チェックポイント保存 ──┤  すべて Lakebase に保存
ステップ 3: ツール実行結果を LLM に返す       │  thread_id で識別
  → チェックポイント保存 ──┤
ステップ 4: LLM が最終回答を生成             │
  → チェックポイント保存 ──┘
```

保存される内容：

| データ | 例 |
|--------|-----|
| メッセージ履歴 | ユーザーとアシスタントの全メッセージ |
| ツール呼び出し履歴 | どのツールを呼んだか、引数、結果 |
| エージェントの中間状態 | LangGraph のノード実行状態 |

**なぜ自動保存が必要か？**

フロントエンドは同じチャットスレッドで続きの質問を送る時、**最新のメッセージだけ**を送ります。過去のメッセージ履歴は送りません。エージェント側でチェックポイントから復元するため、フロントエンドの通信量が抑えられ、会話が長くなっても高速に動作します。

**制約：** `thread_id` が変わると（新しいチャットを開くと）、前のチャットの内容は参照できません。これが Long-term Memory が必要な理由です。

### Long-term Memory（ユーザー記憶）

```
AsyncDatabricksStore → Lakebase（PostgreSQL）+ Embedding（databricks-qwen3-embedding-0-6b）
```

エージェントが7つのメモリツールを使って、**ユーザーごとに**情報を保存・検索・削除します。

```
Lakebase 内のデータ構造（名前空間で整理）:

("user_memories", "tanaka-taro")
  ├── "dietary"  → {"preference": "ベジタリアン"}
  ├── "organic"  → {"preference": "オーガニック商品が好き"}
  └── "store"    → {"usual_store": "渋谷店"}

("task_summaries", "tanaka-taro")
  ├── "abc-123_2026-04-08T..." → {"title": "商品検索", "summary": "一番安い商品を調べた"}
  └── "def-456_2026-04-08T..." → {"title": "返品ポリシー", "summary": "生鮮食品の返品を説明"}

("conversation_summaries", "tanaka-taro")
  ├── "abc-123" → {"summary": "商品価格と返品について相談"}
  └── "def-456" → {"summary": "おすすめ商品を提案"}
```

#### 7つのメモリツール

| ツール | 種類 | いつ使われるか |
|--------|------|---------------|
| `get_user_memory` | 検索 | 「私の好みは？」と聞かれた時 |
| `save_user_memory` | 保存 | 「ベジタリアンです」と言われた時 |
| `delete_user_memory` | 削除 | 「住所の情報を忘れて」と言われた時 |
| `save_task_summary` | 保存（自動） | タスク完了後にエージェントが勝手に保存 |
| `search_task_history` | 検索 | 「前回何を調べてもらった？」と聞かれた時 |
| `save_conversation_summary` | 保存（自動） | 「さようなら」と言われた時にエージェントが保存 |
| `search_past_conversations` | 検索 | 「今まで何を話した？」と聞かれた時 |

#### セマンティック検索の仕組み

メモリの保存時に、テキストが **Embedding（ベクトル）** に変換されて一緒に保存されます。検索時は質問文もベクトルに変換し、**意味的に近い**メモリを見つけます。

```
保存時:
  "ベジタリアンです" → [0.12, -0.45, 0.78, ...] （1024次元のベクトル）
                        ↓ テキストとベクトルを一緒に Lakebase に保存

検索時:
  「私の食事の好みは？」→ [0.10, -0.42, 0.80, ...]
                           ↓ ベクトルの類似度で検索
                           ↓ 「ベジタリアンです」がヒット（意味が近いから）
```

これにより、「ベジタリアン」という単語を直接使わなくても、「食事の好み」「食べられないもの」などの質問で関連する記憶がヒットします。

#### Short-term と Long-term の使い分けシナリオ

```
── チャット A（月曜日）──
ユーザー: 「ベジタリアンです。覚えておいて。」
エージェント: (save_user_memory で Long-term に保存)
エージェント: 「はい、覚えておきますね！」
ユーザー: 「おすすめの商品は？」
エージェント: (get_user_memory で「ベジタリアン」を検索)
エージェント: 「ベジタリアンのお客様には有機野菜セットがおすすめです！」
  ※ この2つの質問は Short-term Memory で繋がっている（同じ thread_id）

── チャット B（水曜日、新しいチャット）──
ユーザー: 「おすすめの商品は？」
  ※ Short-term Memory は空（新しい thread_id）
  ※ でも Long-term Memory に「ベジタリアン」が残っている！
エージェント: (get_user_memory で「ベジタリアン」を検索)
エージェント: 「以前ベジタリアンとお聞きしていますので、有機野菜セットがおすすめです！」
```

> **詳細なメモリの技術解説:** [docs/lakebase_memory_explained.md](docs/lakebase_memory_explained.md) にデータベーステーブル構成、Embedding の仕組み、チェックポインターの内部動作などの詳細を記載しています。

---

## トレース・モニタリング・評価

### なぜ実験を2つに分けるのか

このアプリでは、MLflow Experiment を**モニタリング用**と**評価用**の2つに分離しています。

```
┌─────────────────────────────┐    ┌─────────────────────────────┐
│  freshmart-agent-monitoring │    │  freshmart-agent-evaluation  │
│  （モニタリング用）            │    │  （評価用）                    │
│                             │    │                             │
│  ・運用中のアプリのトレース    │    │  ・オフライン評価の結果        │
│  ・実ユーザーのリクエスト      │    │  ・スコアラーの採点結果        │
│  ・レイテンシ、エラー率       │    │  ・テストケースの成績          │
│                             │    │                             │
│  → Delta Table に送信可能     │    │  → MLflow Experiment のみ    │
└─────────────────────────────┘    └─────────────────────────────┘
```

**分離する理由：** モニタリング用の Experiment だけ Unity Catalog の Delta Table に送信します。Delta Table への送信には `set_experiment_trace_location`（ノートブックで1回実行）が必要ですが、これは**トレースが0件の空の Experiment にしか紐付けられません**。もし評価結果と運用トレースを同じ Experiment に混在させると、Delta Table 紐付けが困難になります。

### トレースの送信先

```
アプリ実行時（ユーザーがチャット）
  │
  ├── mlflow.langchain.autolog() が自動トレース
  │
  ▼
MLFLOW_EXPERIMENT_ID（モニタリング用）
  │
  ├── デフォルト: MLflow Experiment に記録
  │     └── Experiments UI でトレース確認
  │
  └── MLFLOW_TRACING_DESTINATION 設定時: Delta Table にも送信
        │
        ▼
      Zerobus（サーバーレス取り込みエンジン）
        │
        ▼
      Unity Catalog Delta Table（3テーブル）
        ├── mlflow_experiment_trace_otel_spans   ← 各処理ステップ
        ├── mlflow_experiment_trace_otel_logs    ← ログ
        └── mlflow_experiment_trace_otel_metrics ← メトリクス
```

#### Zerobus とは

トレースを Delta Table に送信する裏側では、**Zerobus** という Databricks のサーバーレス取り込みエンジンが動いています。

```
従来の方式（自前運用が必要）:
  アプリ → OTEL Collector（自分で構築・運用） → ストレージ

Databricks の方式（Zerobus）:
  アプリ → Databricks 管理の OTEL エンドポイント → Zerobus → Delta Table
           ↑                                        ↑
           gRPC API で送信                    サーバーレスで自動スケール
                                              運用不要
```

- **OpenTelemetry（OTEL）標準** に準拠：業界標準のテレメトリ形式でスパン・ログ・メトリクスを送信
- **gRPC API** でアプリからストリーミング送信
- **サーバーレス**：Collector のスケーリング、バックプレッシャー処理、耐障害性を Databricks が管理
- **Unity Catalog のガバナンス**：テーブルレベルの権限管理（誰がトレースを見られるか）

開発者が意識するのは `.env` に `MLFLOW_TRACING_DESTINATION=<catalog>.<schema>` を設定するだけ。Zerobus の存在を知らなくても使えます。

#### Delta Table にトレースを送るメリット

| | MLflow Experiment のみ | Delta Table（Zerobus 経由） |
|---|---|---|
| トレース上限 | Experiment ごとに制限あり | **無制限** |
| 保持期間 | Experiment の保持ポリシーに依存 | **無制限（Delta Table）** |
| SQL クエリ | 不可 | **可能**（SQL Warehouse で直接分析） |
| ダッシュボード | Experiments UI のみ | **SQL + AI/BI Dashboard で自由に可視化** |
| 権限管理 | Experiment ACL | **Unity Catalog のテーブル権限** |

### 評価

評価スクリプトはモニタリングとは別の **評価用 Experiment** に結果を記録します。

```
評価スクリプト実行時
  │
  ├── MLFLOW_EVAL_EXPERIMENT_ID に自動切り替え
  ├── MLFLOW_TRACING_DESTINATION を自動無効化（Delta Table エラー回避）
  ├── mlflow.tracing.reset() で送信先をリセット
  │
  ▼
MLFLOW_EVAL_EXPERIMENT_ID（評価用）
  └── Experiments UI の Evaluation タブで結果確認
```

| コマンド | 方式 | テストケース | サーバー |
|---|---|---|---|
| `uv run agent-evaluate` | ConversationSimulator（マルチターン） | 3件 | 不要 |
| `uv run agent-evaluate-advanced` | ConversationSimulator + カスタムスコアラー | 20件 | 不要 |
| `uv run agent-evaluate-chat` | expected_facts（固定質問） | 9件 | 不要 |

> 評価スクリプトはエージェントを直接関数呼び出しするため、サーバーの起動は不要です。実行前にアプリを停止してください（ポート競合回避）。

#### なぜ評価時に Delta Table 送信を無効化するのか

評価スクリプトが `from agent_server import agent` でエージェントをインポートすると、`agent.py` 内の `set_destination()` が実行されて Delta Table 送信モードになります。しかし、評価結果は Delta Table ではなく MLflow Experiment に記録したいため、評価スクリプトは以下の3段階で送信先をリセットしています：

```python
# 1. 環境変数を削除（agent.py のインポート前に実行）
os.environ.pop("MLFLOW_TRACING_DESTINATION", None)

# 2. agent.py をインポート（set_destination が呼ばれる可能性がある）
from agent_server import agent

# 3. MLflow の内部状態をリセット
mlflow.tracing.reset()
```

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
