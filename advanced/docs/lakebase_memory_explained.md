# Lakebase によるメモリシステム解説

このドキュメントでは、フレッシュマートエージェントが Lakebase（PostgreSQL）をどのようにメモリとして活用しているかを、ステップバイステップで解説します。

---

## 全体像

```
┌─────────────────────────────────────────────────────────────┐
│                    Lakebase (PostgreSQL)                     │
│                                                             │
│  ┌─────────────────────┐  ┌──────────────────────────────┐  │
│  │  Short-term Memory  │  │     Long-term Memory         │  │
│  │  (CheckpointSaver)  │  │     (DatabricksStore)        │  │
│  │                     │  │                              │  │
│  │  ・会話の途中状態    │  │  ・ユーザーの好み            │  │
│  │  ・メッセージ履歴    │  │  ・タスク履歴                │  │
│  │  ・ツール呼び出し    │  │  ・会話サマリー              │  │
│  │                     │  │  ・セマンティック検索対応     │  │
│  │  スレッド内のみ有効  │  │  スレッドをまたいで有効      │  │
│  └─────────────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

| 比較項目 | Short-term Memory | Long-term Memory |
|---------|-------------------|------------------|
| ライブラリ | `AsyncCheckpointSaver` | `AsyncDatabricksStore` |
| スコープ | 同一スレッド（チャットセッション）内 | ユーザー単位（スレッドをまたぐ） |
| 保存タイミング | LangGraph が各ステップで自動保存 | エージェントがツール経由で明示的に保存 |
| 検索方法 | `thread_id` で完全一致 | セマンティック検索（Embedding 類似度） |
| 用途 | 「さっき聞いた商品の話の続き」 | 「前回のチャットで言ったベジタリアンの好み」 |
| Embedding | 不要 | `databricks-gte-large-en`（1024次元） |

---

## Part 1: Short-term Memory（会話ステート）

### 使用ライブラリ

```python
from databricks_langchain import AsyncCheckpointSaver

async with AsyncCheckpointSaver(
    project=LAKEBASE_AUTOSCALING_PROJECT,   # "freshmart-agent-hiroshi"
    branch=LAKEBASE_AUTOSCALING_BRANCH,     # "production"
) as checkpointer:
    agent = create_agent(..., checkpointer=checkpointer)
```

### 役割

LangGraph のエージェントが**各処理ステップの後に自動的に**状態を保存する仕組みです。これにより、同じチャットセッション内で「前のメッセージを覚えている」状態が実現します。

### ステップバイステップ解説

#### ステップ 1：ユーザーが最初のメッセージを送信

```
ユーザー: 「一番安い商品は何ですか？」
```

この時点で `thread_id`（スレッドID）が割り当てられます。同じチャットセッション = 同じ `thread_id` です。

#### ステップ 2：チェックポイント #1 が自動保存される

LangGraph がエージェントの処理を開始する前に、**現在の状態のスナップショット**が Lakebase に保存されます。

```
checkpoint #1 = {
  thread_id: "abc-123",
  messages: [
    { role: "user", content: "一番安い商品は何ですか？" }
  ],
  channel_versions: { messages: 1 },
  metadata: { timestamp: "2026-03-30T...", step: 0 }
}
```

#### ステップ 3：エージェントがツールを呼び出す

エージェントが「Genie ツールで検索しよう」と判断し、ツールを実行します。

#### ステップ 4：チェックポイント #2 が自動保存される

ツール呼び出しの結果が出た後、**また状態が保存**されます：

```
checkpoint #2 = {
  thread_id: "abc-123",
  messages: [
    { role: "user", content: "一番安い商品は何ですか？" },
    { role: "assistant", tool_calls: [{ name: "genie_query", args: "..." }] },
    { role: "tool", content: "PROD-0234 有機炭酸水レモン ¥80" }
  ],
  channel_versions: { messages: 3 },
  metadata: { step: 2 }
}
```

#### ステップ 5：エージェントが最終回答を生成

```
アシスタント: 「一番安い商品は有機炭酸水レモン（¥80）です！」
```

#### ステップ 6：チェックポイント #3 が自動保存される

```
checkpoint #3 = {
  thread_id: "abc-123",
  messages: [
    { role: "user", content: "一番安い商品は何ですか？" },
    { role: "assistant", tool_calls: [...] },
    { role: "tool", content: "PROD-0234 ..." },
    { role: "assistant", content: "一番安い商品は有機炭酸水レモン（¥80）です！" }
  ]
}
```

#### ステップ 7：ユーザーが2回目のメッセージを送信（同じスレッド）

```
ユーザー: 「それ以外におすすめはある？」
```

ここが**チェックポインターの真価**です。同じ `thread_id` なので、LangGraph は Lakebase からチェックポイント #3 を読み込み、**前の会話を覚えた状態**で処理を開始します。エージェントは「一番安い商品の話をしていた」という文脈を持っています。

### PostgreSQL に自動作成されるテーブル

| テーブル | 内容 |
|---------|------|
| **checkpoints** | 各スナップショットの本体。`thread_id` でグループ化。メッセージ履歴等が JSONB で格納 |
| **checkpoint_blobs** | 大きなデータ（長いメッセージ、ツール結果等）をバイナリ（BYTEA）で格納。checkpoints から参照 |
| **checkpoint_writes** | ツール実行等の中間書き込み。正式なチェックポイントに統合される前の一時データ |

### Short-term Memory で保存される情報まとめ

| 情報 | 具体例 |
|------|--------|
| メッセージ履歴 | ユーザーとアシスタントの全メッセージ |
| ツール呼び出し履歴 | どのツールを呼んだか、引数、結果 |
| エージェントの中間状態 | LangGraph のノード実行状態 |
| バージョン情報 | 各チャネルのバージョン番号 |
| メタデータ | タイムスタンプ、ステップ数 |

### 制約

- **スレッドが変わると忘れる**：新しいチャットを開くと `thread_id` が変わるため、前のチャットの内容は参照できない
- これが Long-term Memory が必要な理由

### thread_id は誰がコントロールするか

thread_id の決定は以下の優先順位で行われます（`agent_server/utils.py`）：

```python
def _get_or_create_thread_id(request):
    # 1. フロントエンドが custom_inputs.thread_id を送信 → それを使う
    # 2. フロントエンドが context.conversation_id を送信 → それを使う
    # 3. どちらもない → サーバーが uuid7() で新規生成
```

| レイヤー | 役割 |
|---------|------|
| **チャット UI（フロントエンド）** | 「新しいチャット」ボタンで新しい thread_id を生成。同じチャット画面では同じ thread_id を送り続ける |
| **バックエンド（agent_server）** | フロントエンドから受け取った thread_id をそのまま使う。なければ自動生成 |
| **LangGraph + Lakebase** | 渡された thread_id でチェックポイントを読み書きするだけ |

つまり、**フロントエンドが同じ thread_id を送り続ければ会話が継続し、新しい ID にすればリセット**されます。

curl で直接 API を叩く場合の例：
```bash
# 同じ thread_id → 会話が継続する
curl -X POST http://localhost:8000/invocations \
  -d '{"input": [{"role":"user","content":"一番安い商品は？"}], "custom_inputs": {"thread_id": "my-session-001"}}'

curl -X POST http://localhost:8000/invocations \
  -d '{"input": [{"role":"user","content":"それ以外は？"}], "custom_inputs": {"thread_id": "my-session-001"}}'
# → 「一番安い商品の話」の文脈を覚えた状態で回答

# thread_id を省略 → 毎回新規 UUID が生成 → 毎回「初対面」
curl -X POST http://localhost:8000/invocations \
  -d '{"input": [{"role":"user","content":"それ以外は？"}]}'
# → 「何の話？」となる
```

### なぜフロントエンドから全履歴を送らないのか？

従来のチャットボットでは、フロントエンド側に蓄積した会話履歴を毎回まるごとサーバーに送信する方式（方式A）が一般的でした。このアプリのチェックポインター方式（方式B）とは何が違うのでしょうか。

#### 方式の比較

| | 方式A：フロント送信（従来型） | 方式B：チェックポインター（このアプリ） |
|---|---|---|
| **送信内容** | 全メッセージ履歴 + 最新質問 | 最新質問 + thread_id のみ |
| **履歴の保持場所** | フロントエンドのメモリ / State | Lakebase（サーバー側 DB） |
| **会話の復元** | ブラウザを閉じたら消える | thread_id があれば別端末からでも復元可能 |
| **保存される情報** | ユーザーとアシスタントのメッセージのみ | メッセージ + ツール呼び出し + 中間状態すべて |

#### チェックポインター方式のメリット

**1. ネットワーク効率**

会話が 100 往復になっても、リクエストサイズは最新の 1 メッセージ分だけです。方式 A だと 100 往復分のメッセージを毎回送信するため、トークンコスト・レイテンシが会話の長さに比例して増大します。

**2. ツール実行結果も保持される（最大の違い）**

方式 A では通常、ユーザーとアシスタントのメッセージだけをやり取りします。チェックポインターは**ツール呼び出しの引数・SQL クエリ結果・Vector Search の検索結果・中間ステップ**もすべて保存しています。

例えば「さっき検索した商品の詳細を教えて」と聞くと、Genie ツールが返した SQL 結果まで復元された状態でエージェントが回答できます。

**3. マルチステップのエラー回復**

エージェントがツール A を呼び → ツール B を呼び → 途中でクラッシュした場合、チェックポインターなら最後の成功ステップから再開できます。方式 A では最初からやり直しです。

**4. セッション永続性**

ブラウザを閉じても、別の端末からでも、thread_id さえあれば会話を再開できます。方式 A はフロントエンドの State が消えたら終わりです。

**5. Human-in-the-Loop への対応**

チェックポイント間に「人間の承認待ち」を挟めます（LangGraph の interrupt 機能）。例えば、エージェントが注文を確定する前にユーザーの確認を求め、確認後にそのステップから処理を再開する、といったワークフローが可能です。方式 A ではこうした中断・再開が困難です。

#### チェックポインター方式のデメリット

| デメリット | 詳細 |
|-----------|------|
| DB 依存 | Lakebase が落ちると会話ができない |
| 書き込みオーバーヘッド | 各ステップで DB に書き込む（ただし非同期なので通常は微小） |
| ストレージコスト | 全ステップのスナップショットを保存するためデータ量が増える |

#### 一言でまとめると

> 方式 A は「フロントエンドがメッセージ履歴を管理する」、方式 B は「サーバーが会話の完全な状態（メッセージ + ツール結果 + 中間状態）を管理する」。会話が複雑になるほど、ツールを多用するほど、方式 B の恩恵が大きくなります。

---

## Part 2: Long-term Memory（ユーザー記憶）

### 使用ライブラリ

```python
from databricks_langchain import AsyncDatabricksStore

async with AsyncDatabricksStore(
    project=LAKEBASE_AUTOSCALING_PROJECT,   # "freshmart-agent-hiroshi"
    branch=LAKEBASE_AUTOSCALING_BRANCH,     # "production"
    embedding_endpoint=EMBEDDING_ENDPOINT,   # "databricks-gte-large-en"
    embedding_dims=EMBEDDING_DIMS,           # 1024
) as store:
    await store.setup()  # テーブル自動作成
```

### 役割

ユーザーの好み・過去の対応履歴・会話サマリーを、**スレッドをまたいで**永続的に保存・検索できる Key-Value ストアです。保存時にテキストを Embedding（ベクトル化）し、検索時にセマンティック類似度で関連する記憶を見つけます。

### Short-term との決定的な違い

```
Short-term: スレッド A の中でしか使えない
   スレッド A: 「一番安い商品は？」→「それ以外は？」→ ✅ 文脈を覚えている

Long-term: スレッド A で保存 → スレッド B で思い出す
   スレッド A: 「ベジタリアンです。覚えて。」→ 💾 保存
   スレッド B: 「おすすめは？」→ 🔍 検索 →「ベジタリアンでしたね！」
```

### 名前空間（Namespace）の仕組み

Long-term Memory は **名前空間**（タプル）で整理されます。フォルダのような構造です：

```
Lakebase
├── ("user_memories", "tanaka-taro")
│   ├── "dietary" → {"preference": "ベジタリアン"}
│   ├── "organic" → {"preference": "オーガニック商品が好き"}
│   └── "store"   → {"usual_store": "渋谷店"}
│
├── ("task_summaries", "tanaka-taro")
│   ├── "abc-123_2026-03-30T..." → {"title": "商品検索", "summary": "一番安い商品を調べた"}
│   └── "def-456_2026-03-30T..." → {"title": "返品ポリシー", "summary": "生鮮食品の返品を説明"}
│
├── ("conversation_summaries", "tanaka-taro")
│   ├── "abc-123" → {"summary": "商品価格と返品について相談", "topics": ["商品検索","返品"]}
│   └── "def-456" → {"summary": "おすすめ商品を提案", "topics": ["おすすめ","オーガニック"]}
│
├── ("user_memories", "suzuki-hanako")
│   └── ...（別のユーザーの記憶）
```

### ステップバイステップ解説

#### シナリオ：ユーザーの好みを記憶し、後で活用する

---

**スレッド A（1回目のチャット）**

#### ステップ 1：ユーザーが好みを共有

```
ユーザー: 「私はベジタリアンで、オーガニック商品が好きです。覚えておいてください。」
```

#### ステップ 2：エージェントが `save_user_memory` ツールを呼び出す

エージェントはシステムプロンプトの指示に従い、ツールを呼び出します：

```python
# エージェントが自動的に呼び出す（コードはutils_memory.pyに定義）
save_user_memory(
    memory_key="dietary_preference",
    memory_data_json='{"preference": "ベジタリアン", "detail": "肉・魚を食べない"}',
    config=config  # user_id が含まれている
)
```

#### ステップ 3：Lakebase に保存される

内部的に以下が実行されます：

```python
namespace = ("user_memories", "tanaka-taro")  # user_id から生成
key = "dietary_preference"
value = {"preference": "ベジタリアン", "detail": "肉・魚を食べない"}

await store.aput(namespace, key, value)
```

このとき、`value` のテキスト内容が `databricks-gte-large-en` で**1024次元のベクトルに変換**され、PostgreSQL にベクトルと一緒に保存されます。

#### ステップ 4：エージェントが同様に2つ目の記憶も保存

```python
save_user_memory(
    memory_key="organic_preference",
    memory_data_json='{"preference": "オーガニック商品が好き"}',
    config=config
)
```

#### ステップ 5：エージェントが返答

```
アシスタント: 「承知しました！ベジタリアンでオーガニック商品がお好きだということを記憶しました🌱」
```

#### ステップ 6：会話終了時にサマリーも自動保存

ユーザーが「ありがとう」と言うと、エージェントはシステムプロンプトの指示に従い、**ユーザーに通知せず**に会話サマリーを保存します：

```python
# サイレントに呼び出される
save_conversation_summary(
    summary_json='{"summary": "食事の好みを共有してもらった", "topics": ["好み","ベジタリアン","オーガニック"]}',
    config=config
)
```

---

**スレッド B（別の日の新しいチャット）**

#### ステップ 7：ユーザーが新しいチャットでおすすめを聞く

```
ユーザー: 「おすすめの商品を教えてください。」
```

これは**新しい `thread_id`** です。Short-term Memory には前のチャットの情報はありません。

#### ステップ 8：エージェントが `get_user_memory` を呼び出す

システムプロンプトに「会話の最初に関連する記憶がないか確認」と指示があるため：

```python
get_user_memory(
    query="おすすめ 好み 食事制限",
    config=config  # user_id: "tanaka-taro"
)
```

#### ステップ 9：セマンティック検索が実行される

内部的に以下が実行されます：

```python
namespace = ("user_memories", "tanaka-taro")
results = await store.asearch(namespace, query="おすすめ 好み 食事制限", limit=5)
```

1. クエリ「おすすめ 好み 食事制限」が `databricks-gte-large-en` で**ベクトルに変換**される
2. Lakebase 内の `("user_memories", "tanaka-taro")` 名前空間のすべてのエントリのベクトルと**コサイン類似度**を計算
3. 類似度の高い順に最大5件を返す

結果：
```
Found 2 relevant memories:
- [dietary_preference]: {"preference": "ベジタリアン", "detail": "肉・魚を食べない"}
- [organic_preference]: {"preference": "オーガニック商品が好き"}
```

#### ステップ 10：エージェントが記憶を活用して回答

```
アシスタント: 「ベジタリアンでオーガニック商品がお好きでしたね！
おすすめは：
・有機バナナ（¥198）
・有機アボカド（¥148）
・有機ブロッコリー（¥248）
...」
```

### 7つのメモリツール一覧

| ツール | 名前空間 | 操作 | 呼び出しタイミング |
|--------|---------|------|-------------------|
| `get_user_memory` | `("user_memories", user_id)` | セマンティック検索 | 会話の最初、ユーザーの好みに関する質問 |
| `save_user_memory` | `("user_memories", user_id)` | Key-Value 保存 | ユーザーが好みや情報を共有した時 |
| `delete_user_memory` | `("user_memories", user_id)` | キー指定で削除 | ユーザーが「忘れて」と言った時 |
| `save_task_summary` | `("task_summaries", user_id)` | Key-Value 保存 | タスク完了後（サイレント） |
| `search_task_history` | `("task_summaries", user_id)` | セマンティック検索 | 「前回何を調べた？」と聞かれた時 |
| `save_conversation_summary` | `("conversation_summaries", user_id)` | Key-Value 保存 | 会話終了時（サイレント） |
| `search_past_conversations` | `("conversation_summaries", user_id)` | セマンティック検索 | 「今まで何を話した？」と聞かれた時 |

### PostgreSQL に自動作成されるテーブル

`store.setup()` で以下のテーブルが自動作成されます：

| テーブル | 内容 |
|---------|------|
| **store** | Key-Value データ本体。`namespace`（名前空間）、`key`、`value`（JSONB）、`embedding`（vector(1024)）を格納 |

> **注意：** Short-term の checkpoints テーブルとは別のテーブルです。同じ Lakebase インスタンスの中に両方が共存します。

---

## 両者の連携：実際のリクエスト処理の流れ

```python
# agent.py の stream() メソッド（簡略化）

async with AsyncCheckpointSaver(...) as checkpointer:      # Short-term
    async with AsyncDatabricksStore(...) as store:           # Long-term
        await store.setup()

        config = {
            "configurable": {
                "thread_id": thread_id,     # Short-term のキー
                "store": store,             # Long-term をツールに渡す
                "user_id": user_id,         # Long-term の名前空間に使う
            }
        }

        agent = create_agent(
            ...,
            checkpointer=checkpointer,  # Short-term を LangGraph に渡す
        )

        # エージェント実行
        # → LangGraph が自動的に checkpointer でステップごとに状態保存
        # → エージェントが判断して store 経由でユーザー記憶を読み書き
        async for event in agent.astream(input_state, config):
            yield event
```

1. **リクエスト受信** → `thread_id` と `user_id` を取得
2. **Lakebase に2つの接続を確立**：CheckpointSaver（Short-term）と DatabricksStore（Long-term）
3. **Short-term**：LangGraph が `thread_id` で前のチェックポイントを自動ロード → 会話の続きとして処理
4. **Long-term**：エージェントが必要に応じてツール経由で `user_id` の記憶を検索・保存
5. **処理の各ステップ**で Short-term が自動チェックポイント保存
6. **レスポンス返却** → 接続クローズ

---

## 同期と非同期：メモリの読み書きはどう実行されるか

### 全操作が async/await

このアプリのメモリ操作は、参照も保存も**すべて非同期（async/await）** で実装されています。

| 操作 | Long-term Memory | Short-term Memory |
|------|-----------------|-------------------|
| **参照** | `await store.asearch()` | LangGraph 内部で `await checkpointer.aget()` |
| **保存** | `await store.aput()` | LangGraph 内部で `await checkpointer.aput()` |
| **削除** | `await store.adelete()` | — |

### 「参照は同期じゃないとまずいのでは？」

ご懸念はもっともです。「参照結果が返ってこないうちに次の処理が進んでしまう」のが非同期の怖いところです。しかし、**`await` が付いているので、結果が返るまでその関数内では確実に待ちます**。

```python
# Long-term: get_user_memory の中身（utils_memory.py）
async def get_user_memory(query: str, config: RunnableConfig) -> str:
    results = await store.asearch(namespace, query=query, limit=5)
    #         ^^^^^ ここで DB の結果が返るまで待つ。次の行には進まない。
    return f"Found {len(results)} relevant memories:\n..."
```

### 同期と非同期の違い

```
同期（sync）:
  リクエストA: DB問合せ中... ■■■■■■■ 完了 → 次の処理
  リクエストB:              待機中... ■■■■■ 完了 → 次の処理
  → サーバー全体がリクエストAの完了を待ってしまう

非同期（async/await）:
  リクエストA: DB問合せ開始 → await → ■■■ 結果受取 → 次の処理
  リクエストB:        ↑ 空いた時間で処理開始 → await → ■■ 結果受取
  → リクエストAの中では結果を待つが、サーバーは他のリクエストを並行処理できる
```

ポイント：
- **個々のリクエスト内** → `await` で確実に結果を待つ（参照の一貫性を保証）
- **リクエスト間** → 並行処理できる（サーバーのスループットを確保）

### Short-term Memory の場合

LangGraph の `astream` が内部的に以下を実行します：

```python
# 1. 前のチェックポイントを読む（await で完了を待つ）
state = await checkpointer.aget(thread_id)

# 2. エージェントのステップを実行（state が復元された状態で）
result = await agent_step(state)

# 3. 新しいチェックポイントを書く（await で書き込み完了を待つ）
await checkpointer.aput(thread_id, new_state)

# 4. 次のステップへ（3の完了が保証されている）
```

参照（1）は `await` で確実に完了してからエージェントが動き始めます。保存（3）も `await` で書き込み完了を確認してから次のステップに進みます。

### Long-term Memory の場合

エージェントがツールを呼ぶタイミングで実行されます：

```python
# 参照：エージェントが get_user_memory ツールを呼ぶ
results = await store.asearch(namespace, query=query, limit=5)
# → DB 検索が完了するまで待つ → 結果をエージェントに返す → エージェントが回答に活用

# 保存：エージェントが save_user_memory ツールを呼ぶ
await store.aput(namespace, memory_key, memory_data)
# → DB 書き込みが完了するまで待つ → 「保存しました」とエージェントに返す
```

### なぜ全部 async にしているか

このアプリは **FastAPI + MLflow AgentServer** で動いており、FastAPI は非同期サーバーです。1 つのリクエストが DB の応答を待っている間に、他のユーザーのリクエストを処理できます。同期にすると、1 ユーザーの DB 待ち時間中にサーバー全体がブロックされ、同時アクセスに弱くなります。

> **まとめ：** `await` により「参照は結果を待たないとまずい」と「保存は非同期がいい」を**両立**しています。個々の操作は確実に完了を待ちつつ、サーバー全体としては複数リクエストを効率的に並行処理できます。

---

## アプリケーションアーキテクチャ：FastAPI + MLflow AgentServer

ここまでメモリの仕組みを解説しましたが、これらが動く**土台**であるサーバーアーキテクチャについても説明します。

### 全体構成

```
ブラウザ (localhost:3000)
    │
    │  HTTP
    ▼
┌──────────────────────────────────┐
│  フロントエンド (Express.js)      │  e2e-chatbot-app-next/
│  React + Vite + Vercel AI SDK    │  ← チャット UI
│  Port 3000                       │
└──────────┬───────────────────────┘
           │  HTTP (API_PROXY)
           ▼
┌──────────────────────────────────────────────────────────────┐
│  MLflow AgentServer (FastAPI)                                │  agent_server/
│  Port 8000                                                   │
│                                                              │
│  ┌────────────────────────────┐                              │
│  │  POST /invocations         │  ← OpenAI Responses API 互換 │
│  │  (invoke_handler)          │                              │
│  │  (stream_handler)          │                              │
│  └────────────┬───────────────┘                              │
│               │                                              │
│               ▼                                              │
│  ┌────────────────────────────┐                              │
│  │  LangGraph Agent           │                              │
│  │  ├─ ChatDatabricks (LLM)  │  → Foundation Model API      │
│  │  ├─ MCP Tools             │  → Genie / Vector Search     │
│  │  ├─ Memory Tools          │  → Lakebase (Long-term)      │
│  │  └─ CheckpointSaver       │  → Lakebase (Short-term)     │
│  └────────────────────────────┘                              │
│                                                              │
│  自動機能：                                                   │
│  ├─ MLflow Tracing（全リクエストを自動記録）                    │
│  ├─ リクエスト検証（OpenAI API スキーマ準拠）                   │
│  └─ ストリーミング対応（SSE）                                  │
└──────────────────────────────────────────────────────────────┘
```

### 各レイヤーの役割

#### 1. MLflow AgentServer — サーバーの骨格

```python
# start_server.py
from mlflow.genai.agent_server import AgentServer

agent_server = AgentServer("ResponsesAgent", enable_chat_proxy=True)
app = agent_server.app  # ← これが FastAPI アプリ
```

`AgentServer` は MLflow が提供する **FastAPI ベースのサーバーフレームワーク** です。以下を自動的に提供します：

| 機能 | 詳細 |
|------|------|
| `/invocations` エンドポイント | OpenAI Responses API 互換の REST エンドポイントを自動生成 |
| リクエスト検証 | `ResponsesAgentRequest` スキーマに基づく自動バリデーション |
| ストリーミング | SSE（Server-Sent Events）による逐次レスポンス |
| MLflow Tracing | 全リクエストの LLM 呼び出し・ツール実行・レイテンシを自動記録 |
| Uvicorn 統合 | 非同期 ASGI サーバーで起動 |

開発者は `@invoke()` と `@stream()` デコレータでハンドラーを登録するだけです。

#### 2. @invoke() と @stream() — エージェントの入り口

```python
# agent.py

@invoke()
async def invoke_handler(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    """非ストリーミング：レスポンス全体を一括返却"""
    # 内部的に stream_handler を呼び出し、全イベントを収集して返す
    ...

@stream()
async def stream_handler(request: ResponsesAgentRequest) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    """ストリーミング：レスポンスを逐次返却"""
    # 1. thread_id を取得/生成
    # 2. Lakebase に接続（CheckpointSaver + DatabricksStore）
    # 3. LangGraph エージェントを初期化
    # 4. エージェントを実行し、イベントを逐次 yield
    ...
```

`@invoke()` と `@stream()` は MLflow が提供するデコレータで、これを付けた関数が自動的に `/invocations` エンドポイントに紐付けられます。開発者は FastAPI のルーティングを直接書く必要がありません。

#### 3. OpenAI Responses API 互換

リクエストとレスポンスは **OpenAI の Responses API 形式** に準拠しています：

```bash
# リクエスト
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{
    "input": [{"role": "user", "content": "こんにちは"}],
    "stream": true,
    "context": {"user_id": "tanaka@example.com"},
    "custom_inputs": {"thread_id": "session-001"}
  }'

# レスポンス（非ストリーミング）
{
  "output": [
    {
      "type": "message",
      "role": "assistant",
      "content": [{"type": "output_text", "text": "こんにちは！..."}]
    }
  ],
  "custom_outputs": {"thread_id": "session-001", "user_id": "tanaka@example.com"}
}
```

これにより、OpenAI API 用に作られた既存のクライアント（Vercel AI SDK 等）がそのまま使えます。

#### 4. LangGraph Agent の初期化

```python
async def init_agent(store, workspace_client, checkpointer):
    # MCP ツールの初期化（Genie, Vector Search, Code Interpreter）
    mcp_client = init_mcp_client(workspace_client)
    tools = [get_current_time] + memory_tools() + await mcp_client.get_tools()

    return create_agent(
        model=ChatDatabricks(endpoint="databricks-claude-sonnet-4-5"),  # LLM
        tools=tools,                    # 全ツール（MCP + メモリ + 時刻）
        system_prompt=load_system_prompt(),  # 日本語システムプロンプト
        store=store,                    # Long-term Memory
        checkpointer=checkpointer,      # Short-term Memory
        state_schema=StatefulAgentState, # メッセージ + カスタム入出力
    )
```

#### 5. フロントエンドとバックエンドの起動

`uv run start-app` を実行すると `scripts/start_app.py` が動き、以下を順番に起動します：

```
1. バックエンド起動
   uv run start-server
   → start_server.py → AgentServer → Uvicorn (port 8000)

2. フロントエンド準備
   e2e-chatbot-app-next/ が無ければ GitHub からクローン
   npm install → npm run build

3. フロントエンド起動
   npm run start (port 3000)
   API_PROXY=http://localhost:8000/invocations を環境変数で設定

4. 両方の起動を監視
   「Uvicorn running on」と「Server is running on」のログを検出して READY 判定
```

#### 6. Databricks Apps にデプロイした場合

ローカルと同じコードがそのまま動きます。違いは認証方式のみ：

| | ローカル | Databricks Apps |
|---|---|---|
| 認証 | Databricks CLI プロファイル（OAuth） | サービスプリンシパル（自動） |
| ユーザー識別 | `custom_inputs.user_id` で手動指定 | OBO（On-Behalf-Of）で自動取得 |
| URL | `http://localhost:8000` | `https://<app-name>-<workspace-id>.databricksapps.com` |
| フロントエンド | 同じ React アプリ | 同じ React アプリ（同一プロセス内） |

---

## 参考リンク

- [LangGraph Memory 概要 - LangChain Docs](https://docs.langchain.com/oss/python/langgraph/memory)
- [Semantic Search for LangGraph Memory - LangChain Blog](https://blog.langchain.com/semantic-search-for-langgraph-memory/)
- [LangGraph Checkpointing Architecture - DeepWiki](https://deepwiki.com/langchain-ai/langgraph/4.1-checkpointing-architecture)
- [Internals of LangGraph Postgres Checkpointer](https://blog.lordpatil.com/posts/langgraph-postgres-checkpointer/)
- [Databricks Langchain API Docs](https://api-docs.databricks.com/python/databricks-ai-bridge/latest/databricks_langchain.html)
- [Adding Long-Term Memory to LangGraph Agents](https://hindsight.vectorize.io/blog/2026/03/24/langgraph-longterm-memory)
- [Launching Long-Term Memory Support in LangGraph](https://blog.langchain.com/launching-long-term-memory-support-in-langgraph/)
