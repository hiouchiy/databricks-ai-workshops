# ワークショップ：Databricks で食品スーパー向け AI エージェントを構築する

Genie・Vector Search・長期メモリを組み合わせた会話型 AI エージェントを構築・デプロイします。

---

## 事前準備（ワークショップ開始前に完了してください）

### ワークスペース管理者（Admin）の事前準備

チームで **1名** が以下を実施すれば、全参加者が共有して利用できます。


| #   | 作業                         | 理由                                                              |
| --- | -------------------------- | --------------------------------------------------------------- |
| 1   | 参加者用カタログの作成・権限付与           | 参加者にカタログ作成権限がない場合がある。参加者全員に `USE CATALOG` / `CREATE SCHEMA` を付与 |
| 2   | SQL ウェアハウスの確認              | 共有ウェアハウスが RUNNING であることを確認し、Warehouse ID を参加者に共有                |
| 3   | Vector Search エンドポイントの事前作成 | 新規作成に数分かかるため、共有エンドポイントを1つ用意し、エンドポイント名を参加者に共有                    |
| 4   | Foundation Model API の確認   | `databricks-claude-sonnet-4-5` エンドポイントが利用可能であることを確認             |
| 5   | Lakebase 機能の有効化確認          | ワークスペースで Lakebase が有効であることを確認                                   |
| 6   | Databricks Apps の空きスロット確認  | 上限に近い場合、不要なアプリを事前に削除（Apps デプロイを行う場合のみ）                          |
| 7   | PyPI / npm アクセスの確認         | ローカル環境からパッケージインストールが可能であることを確認                                  |


### 参加者の事前準備

以下のツールをインストールし、動作確認を済ませてください。


| ツール            | インストール方法                                                             | 確認コマンド                            |
| -------------- | -------------------------------------------------------------------- | --------------------------------- |
| Databricks CLI | `brew tap databricks/tap && brew install databricks`                 | `databricks --version`（**v0.295 以上**） |
| uv             | [インストールガイド](https://docs.astral.sh/uv/getting-started/installation/) | `uv --version`                    |
| Node.js 20+    | [nodejs.org](https://nodejs.org) または `nvm install 20`                | `node --version`                  |
| jq             | `brew install jq`                                                    | `jq --version`                    |


**Databricks CLI の認証設定：**

```bash
databricks auth login --host https://<your-workspace>.cloud.databricks.com --profile DEFAULT
databricks current-user me  # ユーザー名が表示されればOK
```

**リポジトリのクローンと依存関係のインストール：**

```bash
git clone https://github.com/hiouchiy/databricks-ai-workshops.git
cd databricks-ai-workshops/advanced

# Python 依存関係のインストール
uv venv .venv
uv sync

# Node.js 依存関係のインストール
cd e2e-chatbot-app-next && npm install && cd ..
```

---

## プレースホルダー

以下の値をワークショップ全体で使います。講師から指定された値、またはご自身で作成した値に置き換えてください。


| プレースホルダー                     | 説明                     | 例                                |
| ---------------------------- | ---------------------- | -------------------------------- |
| `<CATALOG>`                  | Unity Catalog のカタログ名   | `my_catalog`                     |
| `<SCHEMA>`                   | スキーマ名                  | `retail_agent`                   |
| `<WAREHOUSE-ID>`             | SQL ウェアハウスの ID         | `databricks warehouses list` で取得 |
| `<VS-ENDPOINT>`              | Vector Search エンドポイント名 | `dbdemos_vs_endpoint`（既存を使う場合）   |
| `<PROJECT-NAME>`             | Lakebase プロジェクト名       | `freshmart-agent-yourname`       |
| `<BRANCH-NAME>`              | Lakebase ブランチ名         | `production`                     |
| `<GENIE-SPACE-ID>`           | Genie Space の ID       | `01ef...abcd`（URL から取得）          |
| `<MONITORING-EXPERIMENT-ID>` | MLflow モニタリング実験の ID    | `1159599289265540`               |
| `<EVALUATION-EXPERIMENT-ID>` | MLflow 評価実験の ID        | `1159599289265541`               |


---

## ステップ 1：カタログとスキーマの作成

> 講師が事前に作成済みの場合はスキップしてください。

Databricks SQL エディタで実行：

```sql
CREATE CATALOG IF NOT EXISTS <CATALOG>;
CREATE SCHEMA IF NOT EXISTS <CATALOG>.<SCHEMA>;
```

---

## ステップ 2：構造化データの生成

```bash
cd ../data
```

環境変数でカタログ名・スキーマ名を指定して実行します（ファイルの書き換えは不要）：

```bash
CATALOG=<CATALOG> SCHEMA=<SCHEMA> python3 execute_sql.py --profile DEFAULT --warehouse-id <WAREHOUSE-ID>
```

6 つのテーブルが作成されます：customers（200件）、products（約500件）、stores（10件）、transactions（2,000件）、transaction_items（約10,000件）、payment_history（400件）。

すべて日本語のデータ（日本人の名前、日本の住所、日本のスーパーの商品）が生成されます。

> **所要時間：** 約 5〜10 分

---

## ステップ 3：ポリシー文書チャンクの生成

同様に環境変数でカタログ名・スキーマ名を指定して実行：

```bash
CATALOG=<CATALOG> SCHEMA=<SCHEMA> python3 execute_chunking.py --profile DEFAULT --warehouse-id <WAREHOUSE-ID>
```

7 つの日本語ポリシー文書（返品・配送・会員プログラム等）がチャンク分割され、`policy_docs_chunked` テーブルに書き込まれます。

> **重要：** 次のステップで Vector Search インデックスを作成するため、テーブルに Change Data Feed を有効化します：
>
> SQL エディタで実行：
>
> ```sql
> ALTER TABLE <CATALOG>.<SCHEMA>.policy_docs_chunked
>   SET TBLPROPERTIES (delta.enableChangeDataFeed = true);
> ```

```bash
cd ../advanced
```

---

## ステップ 4：Vector Search インデックスの作成

> **前提：** Vector Search エンドポイントは講師が事前に作成済みのものを使います。
> エンドポイント名: `<VS-ENDPOINT>`（講師から指定された名前を使用）
>
> 自分で作成する場合は Databricks UI の **Compute > Vector Search > Create Endpoint** から作成し、READY になるまで待機してください。

**Catalog Explorer** で `<CATALOG>.<SCHEMA>.policy_docs_chunked` に移動：

1. **Create > Vector Search Index** をクリック
2. 以下を設定：
  - Name: `policy_docs_index`
  - Primary key: `chunk_id`
  - Endpoint: `<VS-ENDPOINT>`
  - Source column: `content`
  - Embedding model: `databricks-qwen3-embedding-0-6b`
  - Sync mode: Triggered
3. **Create** をクリック

フルパスを控えておく：`<CATALOG>.<SCHEMA>.policy_docs_index`

> **所要時間：** インデックスの初期同期に 1〜5 分かかります。ステータスが READY になるまで待機してください。
> 次のステップに進みながら待つことができます。

---

## ステップ 5：Genie Space の作成

Databricks UI：**Genie > New Genie Space**

1. 名前：`フレッシュマート 小売データ`
2. ステップ 1 で作成したスキーマ内の 6 テーブルをすべて追加：
  - `customers`, `products`, `stores`, `transactions`, `transaction_items`, `payment_history`
3. SQL ウェアハウスを選択し、**Create** をクリック
4. URL から **スペース ID** をコピー（URL の最後の部分）

---

## ステップ 6：Lakebase オートスケーリングインスタンスの作成

```bash
# プロジェクトの作成
databricks api post "/api/2.0/postgres/projects?project_id=<PROJECT-NAME>" --json '{}'
```

ブランチは自動作成されます。ブランチ名を確認します：

```bash
databricks api get /api/2.0/postgres/projects/<PROJECT-NAME>/branches \
  | jq '.branches[].name'
```

> **注意：** ブランチ名はプロジェクト名に応じて自動生成されます（例: `<PROJECT-NAME>-branch`）。後で `.env` に設定するので控えておいてください。

PGHOST を取得（`<BRANCH-NAME>` は上で確認した名前に置き換え）：

```bash
databricks api get /api/2.0/postgres/projects/<PROJECT-NAME>/branches/<BRANCH-NAME>/endpoints \
  | jq -r '.endpoints[0].status.hosts.host'
```

> **注意：** エンドポイントが ACTIVE になるまで 1〜2 分かかる場合があります。

---

## ステップ 7：MLflow 実験の作成

モニタリング用（アプリ実行時のトレース記録）と評価用（評価スクリプト実行時）の **2つの実験** を作成します。

```bash
DATABRICKS_USERNAME=$(databricks current-user me -o json | jq -r .userName)

# モニタリング用（アプリ実行時のトレース記録）
databricks experiments create-experiment "/Users/$DATABRICKS_USERNAME/freshmart-agent-monitoring"

# 評価用（評価スクリプト実行時）
databricks experiments create-experiment "/Users/$DATABRICKS_USERNAME/freshmart-agent-evaluation"
```

それぞれ返された `experiment_id` を控えておきます。

---

## ステップ 8：環境変数の設定

```bash
cp .env.example .env
```

`.env` を以下のように編集します。ここまでのステップで控えた値を入力してください：

```bash
DATABRICKS_CONFIG_PROFILE=DEFAULT
DATABRICKS_HOST=https://<your-workspace>.cloud.databricks.com
MLFLOW_EXPERIMENT_ID=<MONITORING-EXPERIMENT-ID>
MLFLOW_EVAL_EXPERIMENT_ID=<EVALUATION-EXPERIMENT-ID>
LAKEBASE_AUTOSCALING_PROJECT=<PROJECT-NAME>
LAKEBASE_AUTOSCALING_BRANCH=<BRANCH-NAME>
GENIE_SPACE_ID=<GENIE-SPACE-ID>
VECTOR_SEARCH_INDEX=<CATALOG>.<SCHEMA>.policy_docs_index
PGHOST=<Lakebase のホスト名（ステップ 6 で取得）>
PGUSER=<あなたの Databricks メールアドレス>
PGDATABASE=databricks_postgres
```

> **注意：** `MLFLOW_EXPERIMENT_ID` はアプリ実行時のトレース記録（モニタリング）に、`MLFLOW_EVAL_EXPERIMENT_ID` は評価スクリプト実行時に使われます。

> **注意：** `PROMPT_REGISTRY_NAME` は設定不要です。日本語のシステムプロンプトは `agent.py` にハードコードされています。

### トレース送信先の選択（オプション）

デフォルトではトレースは MLflow Experiment に記録されます。Unity Catalog の Delta Table に送信したい場合は、`.env` に以下を追加してください：

```bash
# Unity Catalog Delta Table にトレースを送信する場合のみ設定
MLFLOW_TRACING_DESTINATION=<CATALOG>.<SCHEMA>
```


| 設定                       | 送信先                       | 特徴                                   |
| ------------------------ | ------------------------- | ------------------------------------ |
| 未設定（デフォルト）               | MLflow Experiment         | Experiments UI でトレース確認。手軽に始められる      |
| `<CATALOG>.<SCHEMA>` を設定 | Unity Catalog Delta Table | SQL でクエリ可能。長期保持。Unity Catalog の権限で管理 |


Delta Table に送信する場合は、以下の事前準備が必要です：

**1. 権限の付与**（SQL エディタで実行）：

```sql
GRANT MODIFY, SELECT ON SCHEMA <CATALOG>.<SCHEMA> TO `your.email@company.com`;
```

**2. トレーステーブルの初期作成**（**Databricks ノートブック**で実行。ローカルからは実行不可）

> **注意：** 紐付ける Experiment にはトレースが1件も入っていない必要があります。既にトレースが入っている場合は、新しい空の Experiment を作成してください：
>
> ```bash
> databricks experiments create-experiment "/Users/$DATABRICKS_USERNAME/freshmart-agent-monitoring-uc"
> ```
>
> 作成した新しい Experiment ID を以下のコードと `.env` の `MLFLOW_EXPERIMENT_ID` に設定してください。

```python
import os
os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = "<WAREHOUSE-ID>"

import mlflow
from mlflow.entities import UCSchemaLocation

mlflow.tracing.set_experiment_trace_location(
    location=UCSchemaLocation(catalog_name="<CATALOG>", schema_name="<SCHEMA>"),
    experiment_id="<MONITORING-EXPERIMENT-ID>",
)
```

これにより、スキーマ内に3つの Delta Table が自動作成されます：

- `mlflow_experiment_trace_otel_spans` — 各処理ステップ（LLM 呼び出し、ツール実行等）
- `mlflow_experiment_trace_otel_logs` — トレース実行中のログ
- `mlflow_experiment_trace_otel_metrics` — レイテンシ・トークン数等のメトリクス

**3. `.env` に送信先を設定**（ローカルで編集）：

```bash
MLFLOW_TRACING_DESTINATION=<CATALOG>.<SCHEMA>
```

テーブル作成後にアプリを起動してチャットすると、トレースが Delta Table に書き込まれます。SQL でクエリできます：

```sql
SELECT * FROM <CATALOG>.<SCHEMA>.mlflow_experiment_trace_otel_spans
WHERE start_time > current_timestamp() - INTERVAL 1 HOUR;
```

> **注意：** `set_experiment_trace_location` は Databricks ノートブック上でのみ実行可能です。ローカル環境からは実行できません。
>
> 参考：[MLflow トレースを Unity Catalog に送信する](https://docs.databricks.com/aws/en/mlflow3/genai/tracing/trace-unity-catalog)

---

## ステップ 9：ローカルで実行

```bash
uv run start-app
```

バックエンドが `http://localhost:8000`、チャット UI が `http://localhost:3000` で起動します。

> **うまく起動しない場合：**
>
> - `uv sync` が完了していることを確認
> - `.env` ファイルが正しく設定されていることを確認
> - `databricks auth token` でトークンが取得できることを確認

### 動作確認

ブラウザで `http://localhost:3000` を開き、以下のプロンプトを試してください：

**Genie（構造化データクエリ）：**

- 「売上トップ 5 の商品を教えてください」
- 「一番安い商品は何ですか？」

**Vector Search（ポリシー検索）：**

- 「返品ポリシーを教えてください。生鮮食品の返品はできますか？」
- 「配送料はいくらですか？」

**メモリ：**

- 「私はベジタリアンで、オーガニック商品が好きです。覚えておいてください。」
- （新しいチャットで）「私の好みを覚えていますか？おすすめの商品を教えてください。」

### トレースの確認

Databricks UI の **Experiments > freshmart-agent-monitoring** でエージェントのトレースを確認できます。各リクエストの LLM 呼び出し、ツール実行、レイテンシなどが記録されています。評価結果は **Experiments > freshmart-agent-evaluation** で確認できます。

---

## ステップ 10（オプション）：エージェントの評価

> **注意：** ステップ 9 でアプリを起動中の場合は、ターミナルで **Ctrl+C** を押してサーバーを停止してから評価を実行してください。評価スクリプトはサーバーを使わずにエージェントを直接呼び出すため、サーバーが起動したままだとポートの競合やプロセスの干渉が発生する場合があります。
>
> **注意（Delta Table トレース利用時）：** `.env` で `MLFLOW_TRACING_DESTINATION` を設定している場合、評価スクリプトは自動的にこの設定を無効化して実行します。これは、Delta Table のトレーステーブルが未作成の場合にエラーになることを防ぐためです。評価結果は常に `MLFLOW_EVAL_EXPERIMENT_ID` の MLflow Experiment に記録されます。

### チャット評価（expected_facts ベース）

```bash
uv run agent-evaluate-chat
```

9件の固定質問（シンプル3件 + 複雑3件 + スコープ外3件）と模範解答（expected_facts）を使い、Correctness / RelevanceToQuery / RetrievalSufficiency / Safety / Fluency で採点します。サーバーの起動は不要で、エージェントを直接呼び出して評価します。

### マルチターン評価（会話シミュレータ）

```bash
uv run agent-evaluate
```

日本語のテストケース3件を使い、模擬ユーザー（LLM）がエージェントとマルチターンの会話を自動実行します。10 の MLflow スコアラー（Completeness、ConversationalSafety、Fluency、KnowledgeRetention、RelevanceToQuery、Safety、ToolCallCorrectness、ToolCallEfficiency、UserFrustration 等）で自動採点されます。

### マルチターン高度な評価（20テストケース + カスタムスコアラー）

```bash
uv run agent-evaluate-advanced
```

20件の日本語テストケース（構造化データ、ポリシー検索、複合質問、メモリ）に加え、3つのカスタムスコアラーで評価します：

- **tool_routing_accuracy** — 質問の種類に応じて正しいツール（Genie/Vector Search/Memory）が選ばれているか
- **policy_specificity** — ポリシー回答に具体的な数字（「48時間」「¥3,000」等）が含まれているか
- **retail_tone_appropriateness** — 接客トーンが適切か（共感・アクション提示・温かみ）

結果は MLflow Experiments UI の **freshmart-agent-evaluation** 実験で確認できます。

---

## ステップ 11（オプション）：Databricks Apps へのデプロイ

> **前提条件：**
> - Databricks CLI **v0.295 以上**（`brew upgrade databricks` で更新）
> - ワークスペースの Apps 枠に空きがあること
> - Apps 環境から PyPI と npm レジストリにアクセスできること

> **重要：** `e2e-chatbot-app-next/package-lock.json` が**公開レジストリ（registry.npmjs.org）** を参照していることを確認してください。企業プロキシの URL が含まれている場合、Apps 環境で `npm install` が失敗します。確認方法：
> ```bash
> grep -c "registry.npmjs.org" e2e-chatbot-app-next/package-lock.json    # 900前後なら OK
> grep -c "your-proxy" e2e-chatbot-app-next/package-lock.json            # 0 なら OK
> ```
> プロキシ URL が含まれている場合は、lockfile を再生成してください：
> ```bash
> cd e2e-chatbot-app-next && rm -f package-lock.json && npm install && cd ..
> ```

### 11-1. `databricks.yml` と `app.yaml` の確認

手動セットアップの場合、`databricks.yml` のリソース定義に実際の値を設定してください（`uv run quickstart` を使った場合は自動更新されます）：

- `experiment_id` — モニタリング用 MLflow Experiment ID
- `space_id` — Genie Space ID
- `securable_full_name` — Vector Search インデックスのフルパス
- `LAKEBASE_AUTOSCALING_PROJECT` / `LAKEBASE_AUTOSCALING_BRANCH` — Lakebase の値（`value` で直接指定）

> **注意：** Lakebase のリソースバインディングは CLI v0.295 時点では未対応のため、`value` で直接指定します。Experiment、Genie Space、Vector Search Index は `value_from` でリソースバインディング経由で注入されます。

### 11-2. バンドルデプロイ（アプリ作成 + ソースコード同期）

```bash
databricks bundle deploy -t dev --profile DEFAULT
```

初回はアプリの作成が含まれるため数分かかります。

### 11-3. アプリの起動

```bash
databricks apps start <アプリ名> --profile DEFAULT
```

コンピュートが ACTIVE になるまで待機：

```bash
databricks apps get <アプリ名> --profile DEFAULT -o json | jq '.compute_status.state'
# "ACTIVE" と表示されるまで待つ
```

### 11-4. ソースコードのデプロイ

```bash
databricks apps deploy <アプリ名> \
  --source-code-path "/Workspace/Users/<あなたのメールアドレス>/.bundle/retail_grocery_ltm_memory/dev/files" \
  --profile DEFAULT
```

> **注意：** デプロイ後、npm install → npm build → アプリ起動に **3〜5 分** かかります。ステータスが RUNNING になるまで待ってから動作確認してください：
> ```bash
> databricks apps get <アプリ名> --profile DEFAULT -o json | jq '.app_status.state'
> ```

### 11-5. サービスプリンシパルへのパーミッション付与

リソースバインディング（Experiment、Genie、VS Index）は自動的に SP に権限が付与されますが、**Unity Catalog スキーマと Lakebase は手動で付与**する必要があります。

```bash
# SP Client ID を取得
SP_CLIENT_ID=$(databricks apps get <アプリ名> --output json --profile DEFAULT | jq -r '.service_principal_client_id')
echo "SP Client ID: $SP_CLIENT_ID"
```

**Unity Catalog パーミッション**（SQL エディタで実行）：

```sql
GRANT USE CATALOG ON CATALOG `<CATALOG>` TO `<SP_CLIENT_ID>`;
GRANT USE SCHEMA ON SCHEMA `<CATALOG>`.`<SCHEMA>` TO `<SP_CLIENT_ID>`;
GRANT SELECT ON SCHEMA `<CATALOG>`.`<SCHEMA>` TO `<SP_CLIENT_ID>`;
```

**Lakebase パーミッション**：

```bash
uv run python scripts/grant_lakebase_permissions.py "$SP_CLIENT_ID" \
  --memory-type langgraph-short-term --project <PROJECT-NAME> --branch <BRANCH-NAME>
uv run python scripts/grant_lakebase_permissions.py "$SP_CLIENT_ID" \
  --memory-type langgraph-long-term --project <PROJECT-NAME> --branch <BRANCH-NAME>
```

パーミッション付与後、アプリを再起動してください：

```bash
databricks apps stop <アプリ名> --profile DEFAULT
databricks apps start <アプリ名> --profile DEFAULT
```

### 11-6. 動作確認

> **注意：** アプリ起動後、フロントエンドが完全に利用可能になるまで **3〜5 分** かかります。

**ブラウザ**：アプリの URL にアクセスしてチャット画面が表示されることを確認

```bash
databricks apps get <アプリ名> --profile DEFAULT -o json | jq -r '.url'
```

**API テスト**：

```bash
APP_URL=$(databricks apps get <アプリ名> --output json --profile DEFAULT | jq -r '.url')
TOKEN=$(databricks auth token --profile DEFAULT -o json | jq -r .access_token)

curl -X POST "${APP_URL}/invocations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input": [{"role": "user", "content": "返品ポリシーを教えてください"}]}'
```

---

## トラブルシューティング

| 問題 | 対処法 |
|------|--------|
| `python3: command not found` | Python 3.11 以上がインストールされていることを確認。`python` でも可 |
| `uv sync` で PyPI 接続エラー | インターネット接続を確認。企業ネットワークの場合は社内の PyPI ミラーやプロキシ設定を確認 |
| `npm install` が Apps 環境でクラッシュ | `package-lock.json` に企業プロキシ URL が含まれている。`rm -f package-lock.json && npm install` で公開レジストリの lockfile を再生成 |
| `delta.enableChangeDataFeed` エラー | ステップ 3 の CDF 有効化を実行し忘れている。SQL エディタで `ALTER TABLE` を実行 |
| VS インデックスが READY にならない | Catalog Explorer でステータスを確認。エンドポイントが ONLINE であることを確認 |
| Lakebase `project_id is required` | API のクエリパラメータに `?project_id=<名前>` を指定（JSON ボディではなく URL に） |
| `experiments create --name` エラー | `experiments create-experiment "<名前>"` を使用 |
| `couldn't get a connection after 30 sec` | Lakebase の SP パーミッション未付与。ステップ 11-5 の Lakebase パーミッションを実行し、アプリを再起動 |
| `relation "store" does not exist` | メモリテーブルが未作成。アプリを再起動すると初回リクエスト時に自動作成されます |
| API 呼び出しで `302` エラー | PAT ではなく OAuth トークン（`databricks auth token`）を使用 |
| デプロイ後 502 Bad Gateway | フロントエンドの npm build に時間がかかっている。3〜5 分待ってから再アクセス |
| `bundle deploy` でリソースエラー | Databricks CLI を v0.295 以上に更新（`brew upgrade databricks`） |
| Apps の上限エラー | 不要なアプリを削除してから再デプロイ |
| Apps UI でリソースが空 | CLI が古い。v0.295 以上ならリソースバインディングが正しく反映される |


