**[日本語](#ワークショップdatabricks-で食品スーパー向け-ai-エージェントを構築する)** | **[English](#workshop-build-a-retail-grocery-ai-agent-on-databricks)**

---

# ワークショップ：Databricks で食品スーパー向け AI エージェントを構築する

Genie・Vector Search・長期メモリを組み合わせた会話型 AI エージェントを構築・デプロイします。

## 前提条件

| ツール | インストール方法 |
|--------|-----------------|
| Databricks CLI | `brew tap databricks/tap && brew install databricks` |
| uv | [インストールガイド](https://docs.astral.sh/uv/getting-started/installation/) |
| Node.js 20+ | [nodejs.org](https://nodejs.org) |
| jq | `brew install jq` |

ワークスペースに必要な機能：サーバーレスコンピュート、Foundation Model API（Claude）、Unity Catalog、Vector Search、Lakebase。

**開始前に CLI の認証を済ませてください：**
```bash
databricks auth login --host https://<your-workspace>.cloud.databricks.com --profile DEFAULT
databricks current-user me  # 動作確認
```

## プレースホルダー

ワークショップ全体で以下を置き換えてください：

| プレースホルダー | 例 |
|-----------------|-----|
| `<CATALOG>` | `my_catalog` |
| `<SCHEMA>` | `retail_agent` |
| `<WAREHOUSE-ID>` | `databricks warehouses list` で取得 |
| `<PROJECT-NAME>` | `retail-grocery-agent`（Lakebase オートスケーリングプロジェクト） |
| `<BRANCH-NAME>` | `production`（Lakebase オートスケーリングブランチ） |
| `<GENIE-SPACE-ID>` | `01ef...abcd`（Genie の URL から取得） |
| `<EXPERIMENT-ID>` | `1159599289265540` |

---

## ステップ 1：リポジトリのクローン

```bash
git clone https://github.com/hiouchiy/databricks-ai-workshops.git
cd databricks-ai-workshops
```

---

## ステップ 2：カタログとスキーマの作成

Databricks SQL エディタで実行：

```sql
CREATE CATALOG IF NOT EXISTS <CATALOG>;
CREATE SCHEMA IF NOT EXISTS <CATALOG>.<SCHEMA>;
```

---

## ステップ 3：構造化データの生成

```bash
cd data
```

`execute_sql.py` の 19-20 行目で `CATALOG` と `SCHEMA` を設定し、実行：

```bash
python execute_sql.py --profile DEFAULT --warehouse-id <WAREHOUSE-ID>
```

6 つのテーブルが作成されます：customers、products、stores、transactions、transaction_items、payment_history。

---

## ステップ 4：ポリシー文書チャンクの生成

`execute_chunking.py` の 18-19 行目で `CATALOG` と `SCHEMA` を設定し、実行：

```bash
python execute_chunking.py --profile DEFAULT --warehouse-id <WAREHOUSE-ID>
```

7 つのポリシー文書をチャンクに分割し、`policy_docs_chunked` テーブルに書き込みます。

---

## ステップ 5：Vector Search エンドポイントの作成

Databricks UI：**Compute > Vector Search > Create Endpoint**

- 名前：`freshmart-policies`
- ステータスが **READY** になるまで待機（約 5〜10 分）

---

## ステップ 6：Vector Search インデックスの作成

**Catalog Explorer** で `<CATALOG>.<SCHEMA>.policy_docs_chunked` に移動：

1. **Create > Vector Search Index** をクリック
2. 設定：name=`policy_docs_index`、primary key=`chunk_id`、endpoint=ステップ 5 で作成したもの、source column=`content`、model=`databricks-gte-large-en`、sync=Triggered
3. **Create** をクリック

フルパスを控えておく：`<CATALOG>.<SCHEMA>.policy_docs_index`

---

## ステップ 7：Genie Space の作成

Databricks UI：**Genie > New Genie Space**

1. 名前：`Retail Grocery Data`
2. スキーマ内の 6 テーブルをすべて追加
3. SQL ウェアハウスを選択し、**Create** をクリック
4. URL から **スペース ID** をコピー

---

## ステップ 8：Lakebase オートスケーリングインスタンスの作成

```bash
# プロジェクトの作成
databricks api post /api/2.0/postgres/projects --json '{
  "name": "<PROJECT-NAME>"
}'

# ブランチの作成
databricks api post /api/2.0/postgres/projects/<PROJECT-NAME>/branches --json '{
  "name": "<BRANCH-NAME>"
}'

# エンドポイントが ACTIVE であることを確認
databricks api get /api/2.0/postgres/projects/<PROJECT-NAME>/branches/<BRANCH-NAME>/endpoints \
  | jq '.endpoints[0].status.current_state'
# "ACTIVE" になるまで待機
```

後で使う PGHOST を取得：
```bash
databricks api get /api/2.0/postgres/projects/<PROJECT-NAME>/branches/<BRANCH-NAME>/endpoints \
  | jq -r '.endpoints[0].status.hosts.host'
```

---

## ステップ 9：MLflow 実験の作成

```bash
cd ../advanced
DATABRICKS_USERNAME=$(databricks current-user me | jq -r .userName)
databricks experiments create --name "/Users/$DATABRICKS_USERNAME/retail-grocery-ltm-memory"
```

返された `experiment_id` を控えておきます。

---

## ステップ 10：システムプロンプトの登録

```bash
uv run register-prompt --name <CATALOG>.<SCHEMA>.freshmart_system_prompt
```

---

## ステップ 11：パーミッションの付与

### Lakebase

オートスケーリング Lakebase の場合、パーミッションは Databricks ID で管理されます。手動での `psql` ロール作成は不要です。接続時に Databricks ユーザーが OAuth で自動認証されます。

### Genie Space

**Genie > 対象のスペース > Share** > 自分のユーザーを **Can Run** で追加。

### Vector Search Index

**Catalog Explorer > 対象のインデックス > Permissions** > 自分のユーザーを **SELECT** で追加。

### MLflow Experiment

**Experiments > 対象の実験 > Permissions** > 自分のユーザーを **Can Manage** で追加。

### Unity Catalog

```sql
GRANT USE CATALOG ON CATALOG <CATALOG> TO `your.email@company.com`;
GRANT USE SCHEMA ON SCHEMA <CATALOG>.<SCHEMA> TO `your.email@company.com`;
GRANT SELECT ON SCHEMA <CATALOG>.<SCHEMA> TO `your.email@company.com`;
```

---

## ステップ 12：環境変数の設定

```bash
cd advanced
cp .env.example .env
```

`.env` を編集：

```bash
DATABRICKS_CONFIG_PROFILE=DEFAULT
MLFLOW_EXPERIMENT_ID=<EXPERIMENT-ID>
LAKEBASE_AUTOSCALING_PROJECT=<PROJECT-NAME>
LAKEBASE_AUTOSCALING_BRANCH=<BRANCH-NAME>
GENIE_SPACE_ID=<GENIE-SPACE-ID>
VECTOR_SEARCH_INDEX=<CATALOG>.<SCHEMA>.policy_docs_index
PROMPT_REGISTRY_NAME=<CATALOG>.<SCHEMA>.freshmart_system_prompt
PGHOST=<your-lakebase-hostname>
PGUSER=your.email@company.com
PGDATABASE=databricks_postgres
```

Lakebase のホスト名を確認するには（ステップ 8 参照）：
```bash
databricks api get /api/2.0/postgres/projects/<PROJECT-NAME>/branches/<BRANCH-NAME>/endpoints \
  | jq -r '.endpoints[0].status.hosts.host'
```

---

## ステップ 13：ローカルで実行

```bash
uv run start-app
```

バックエンドが `http://localhost:8000`、チャット UI が `http://localhost:3000` で起動します。

`http://localhost:3000` を開いて、以下のプロンプトを試してください：

- 「売上トップ 5 の商品は？」（Genie）
- 「生鮮食品の返品ポリシーは？」（Vector Search）
- 「オーガニック商品が好きだと覚えておいて」→ 新しいチャットで「私の好みは？」（メモリ）

Databricks UI の **Experiments > 対象の実験** でトレースを確認できます。

---

## ステップ 14：デプロイ設定ファイルの構成

### `databricks.yml` — リソース定義の更新

`resources` セクションに実際のリソース ID を設定：

```yaml
        - name: "experiment"
          experiment:
            experiment_id: "<EXPERIMENT-ID>"
            permission: "CAN_MANAGE"
        - name: "retail_grocery_genie"
          genie_space:
            name: "Retail Grocery Data"
            space_id: "<GENIE-SPACE-ID>"
            permission: "CAN_RUN"
        - name: "lakebase_memory"
          database:
            autoscaling_project: "<PROJECT-NAME>"
            autoscaling_branch: "<BRANCH-NAME>"
            database_name: "databricks_postgres"
            permission: "CAN_CONNECT_AND_CREATE"
        - name: "policy_docs_index"
          uc_securable:
            securable_full_name: "<CATALOG>.<SCHEMA>.policy_docs_index"
            securable_type: "TABLE"
            permission: "SELECT"
```

Prompt Registry の値を設定：
```yaml
          - name: PROMPT_REGISTRY_NAME
            value: "<CATALOG>.<SCHEMA>.freshmart_system_prompt"
```

---

## ステップ 15：Databricks Apps へのデプロイ

```bash
# バリデーション
databricks bundle validate -t dev

# デプロイ
databricks bundle deploy -t dev

# アプリにソースコードをデプロイ
DATABRICKS_USERNAME=$(databricks current-user me | jq -r .userName)
databricks apps deploy retail-grocery-ltm-memory \
  --source-code-path /Workspace/Users/$DATABRICKS_USERNAME/.bundle/retail_grocery_ltm_memory/dev/files
```

---

## ステップ 16：アプリのサービスプリンシパルにパーミッションを付与

```bash
# アプリのサービスプリンシパルを取得
SP_CLIENT_ID=$(databricks apps get retail-grocery-ltm-memory --output json | jq -r '.service_principal_client_id')

# Lakebase パーミッションの付与
uv run python scripts/grant_lakebase_permissions.py "$SP_CLIENT_ID" \
  --memory-type langgraph-short-term --project <PROJECT-NAME> --branch <BRANCH-NAME>
uv run python scripts/grant_lakebase_permissions.py "$SP_CLIENT_ID" \
  --memory-type langgraph-long-term --project <PROJECT-NAME> --branch <BRANCH-NAME>
```

サービスプリンシパルに Genie Space へのアクセスも付与します：**Genie > 対象のスペース > Share** > サービスプリンシパルを **Can Run** で追加。

---

## ステップ 17：アプリの起動と動作確認

```bash
databricks apps start retail-grocery-ltm-memory

# URL を取得
APP_URL=$(databricks apps get retail-grocery-ltm-memory --output json | jq -r '.url')
echo "App URL: $APP_URL"

# API をテスト
TOKEN=$(databricks auth token | jq -r .access_token)
curl -X POST "${APP_URL}/invocations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input": [{"role": "user", "content": "どんな店舗がありますか？"}]}'
```

ブラウザでアプリの URL を開き、ステップ 13 と同じプロンプトを試してください。

---

## トラブルシューティング

| 問題 | 対処法 |
|------|--------|
| `relation "store" does not exist` | メモリテーブルが未作成。アプリを再起動すると初回リクエスト時に自動作成されます |
| アプリが `STOPPED` のまま | `databricks apps start retail-grocery-ltm-memory` を実行 |
| API 呼び出しで `302` エラー | PAT ではなく OAuth トークン（`databricks auth token`）を使用 |
| Lakebase パーミッションエラー | デプロイ済みの場合：ステップ 16 を再実行。ローカルの場合：CLI 認証が有効か確認（`databricks auth token`） |
| `bundle validate` が失敗 | `value_from` の名前がリソースの `name` フィールドと完全一致しているか確認 |
| Vector Search が空を返す | Catalog Explorer でインデックスにデータがあるか確認 |
| ローカルアプリで Lakebase エラー | `.env` の PGHOST/PGUSER を確認。トークン期限切れの場合は `databricks auth login` 後にアプリを再起動 |
| Genie パーミッションエラー | 自分のユーザー（ステップ 11）またはアプリの SP（ステップ 16）に Can Run を付与 |
| アプリログの確認 | **Apps > retail-grocery-ltm-memory > Logs** または `databricks apps get-logs retail-grocery-ltm-memory` |

---

**[日本語](#ワークショップdatabricks-で食品スーパー向け-ai-エージェントを構築する)** | **[English](#workshop-build-a-retail-grocery-ai-agent-on-databricks)**

---

# Workshop: Build a Retail Grocery AI Agent on Databricks

Build and deploy a conversational AI agent with Genie, Vector Search, and long-term memory.

## Prerequisites

| Tool | Install |
|------|---------|
| Databricks CLI | `brew tap databricks/tap && brew install databricks` |
| uv | [install guide](https://docs.astral.sh/uv/getting-started/installation/) |
| Node.js 20+ | [nodejs.org](https://nodejs.org) |
| jq | `brew install jq` |

Your workspace needs: Serverless compute, Foundation Model API (Claude), Unity Catalog, Vector Search, and Lakebase.

**Authenticate the CLI before starting:**
```bash
databricks auth login --host https://<your-workspace>.cloud.databricks.com --profile DEFAULT
databricks current-user me  # verify it works
```

## Placeholders

Replace these throughout the workshop:

| Placeholder | Example |
|-------------|---------|
| `<CATALOG>` | `my_catalog` |
| `<SCHEMA>` | `retail_agent` |
| `<WAREHOUSE-ID>` | from `databricks warehouses list` |
| `<PROJECT-NAME>` | `retail-grocery-agent` (Lakebase autoscaling project) |
| `<BRANCH-NAME>` | `production` (Lakebase autoscaling branch) |
| `<GENIE-SPACE-ID>` | `01ef...abcd` (from Genie URL) |
| `<EXPERIMENT-ID>` | `1159599289265540` |

---

## Step 1: Clone the Repo

```bash
git clone https://github.com/hiouchiy/databricks-ai-workshops.git
cd databricks-ai-workshops
```

---

## Step 2: Create Catalog and Schema

Run in the Databricks SQL Editor:

```sql
CREATE CATALOG IF NOT EXISTS <CATALOG>;
CREATE SCHEMA IF NOT EXISTS <CATALOG>.<SCHEMA>;
```

---

## Step 3: Generate Structured Data

```bash
cd data
```

Edit `execute_sql.py` — set `CATALOG` and `SCHEMA` on lines 19-20, then run:

```bash
python execute_sql.py --profile DEFAULT --warehouse-id <WAREHOUSE-ID>
```

This creates 6 tables: customers, products, stores, transactions, transaction_items, payment_history.

---

## Step 4: Generate Policy Document Chunks

Edit `execute_chunking.py` — set `CATALOG` and `SCHEMA` on lines 18-19, then run:

```bash
python execute_chunking.py --profile DEFAULT --warehouse-id <WAREHOUSE-ID>
```

This chunks 7 policy docs and writes to the `policy_docs_chunked` table.

---

## Step 5: Create a Vector Search Endpoint

In the Databricks UI: **Compute > Vector Search > Create Endpoint**

- Name: `freshmart-policies`
- Wait for status: **READY** (~5-10 min)

---

## Step 6: Create a Vector Search Index

In **Catalog Explorer**, navigate to `<CATALOG>.<SCHEMA>.policy_docs_chunked`:

1. Click **Create > Vector Search Index**
2. Set: name=`policy_docs_index`, primary key=`chunk_id`, endpoint=from Step 5, source column=`content`, model=`databricks-gte-large-en`, sync=Triggered
3. Click **Create**

Note the full path: `<CATALOG>.<SCHEMA>.policy_docs_index`

---

## Step 7: Create a Genie Space

In the Databricks UI: **Genie > New Genie Space**

1. Name: `Retail Grocery Data`
2. Add all 6 tables from your schema
3. Select a SQL warehouse and click **Create**
4. Copy the **Space ID** from the URL

---

## Step 8: Create a Lakebase Autoscaling Instance

```bash
# Create the project
databricks api post /api/2.0/postgres/projects --json '{
  "name": "<PROJECT-NAME>"
}'

# Create the branch
databricks api post /api/2.0/postgres/projects/<PROJECT-NAME>/branches --json '{
  "name": "<BRANCH-NAME>"
}'

# Verify the endpoint is ACTIVE
databricks api get /api/2.0/postgres/projects/<PROJECT-NAME>/branches/<BRANCH-NAME>/endpoints \
  | jq '.endpoints[0].status.current_state'
# Wait until "ACTIVE"
```

Get the PGHOST for later:
```bash
databricks api get /api/2.0/postgres/projects/<PROJECT-NAME>/branches/<BRANCH-NAME>/endpoints \
  | jq -r '.endpoints[0].status.hosts.host'
```

---

## Step 9: Create an MLflow Experiment

```bash
cd ../advanced
DATABRICKS_USERNAME=$(databricks current-user me | jq -r .userName)
databricks experiments create --name "/Users/$DATABRICKS_USERNAME/retail-grocery-ltm-memory"
```

Copy the returned `experiment_id`.

---

## Step 10: Register the System Prompt

```bash
uv run register-prompt --name <CATALOG>.<SCHEMA>.freshmart_system_prompt
```

---

## Step 11: Grant Permissions

### Lakebase

For autoscaling Lakebase, permissions are managed via Databricks identity — no manual `psql` role creation needed. Your Databricks user is automatically authenticated via OAuth when connecting.

### Genie Space

**Genie > your space > Share** > Add your user with **Can Run**.

### Vector Search Index

**Catalog Explorer > your index > Permissions** > Add your user with **SELECT**.

### MLflow Experiment

**Experiments > your experiment > Permissions** > Add your user with **Can Manage**.

### Unity Catalog

```sql
GRANT USE CATALOG ON CATALOG <CATALOG> TO `your.email@company.com`;
GRANT USE SCHEMA ON SCHEMA <CATALOG>.<SCHEMA> TO `your.email@company.com`;
GRANT SELECT ON SCHEMA <CATALOG>.<SCHEMA> TO `your.email@company.com`;
```

---

## Step 12: Configure Environment Variables

```bash
cd advanced
cp .env.example .env
```

Edit `.env`:

```bash
DATABRICKS_CONFIG_PROFILE=DEFAULT
MLFLOW_EXPERIMENT_ID=<EXPERIMENT-ID>
LAKEBASE_AUTOSCALING_PROJECT=<PROJECT-NAME>
LAKEBASE_AUTOSCALING_BRANCH=<BRANCH-NAME>
GENIE_SPACE_ID=<GENIE-SPACE-ID>
VECTOR_SEARCH_INDEX=<CATALOG>.<SCHEMA>.policy_docs_index
PROMPT_REGISTRY_NAME=<CATALOG>.<SCHEMA>.freshmart_system_prompt
PGHOST=<your-lakebase-hostname>
PGUSER=your.email@company.com
PGDATABASE=databricks_postgres
```

To find your Lakebase hostname (from Step 8):
```bash
databricks api get /api/2.0/postgres/projects/<PROJECT-NAME>/branches/<BRANCH-NAME>/endpoints \
  | jq -r '.endpoints[0].status.hosts.host'
```

---

## Step 13: Run Locally

```bash
uv run start-app
```

This starts the backend on `http://localhost:8000` and the chat UI on `http://localhost:3000`.

Open `http://localhost:3000` and try these prompts:

- "What are the top 5 products by revenue?" (Genie)
- "What is the return policy for perishable items?" (Vector Search)
- "Remember that I prefer organic products" then in a new chat: "What are my preferences?" (Memory)

Verify traces in **Experiments > your experiment** in the Databricks UI.

---

## Step 14: Configure Deployment Files

### `databricks.yml` — Update resource definitions

Set your actual resource IDs in the `resources` section:

```yaml
        - name: "experiment"
          experiment:
            experiment_id: "<EXPERIMENT-ID>"
            permission: "CAN_MANAGE"
        - name: "retail_grocery_genie"
          genie_space:
            name: "Retail Grocery Data"
            space_id: "<GENIE-SPACE-ID>"
            permission: "CAN_RUN"
        - name: "lakebase_memory"
          database:
            autoscaling_project: "<PROJECT-NAME>"
            autoscaling_branch: "<BRANCH-NAME>"
            database_name: "databricks_postgres"
            permission: "CAN_CONNECT_AND_CREATE"
        - name: "policy_docs_index"
          uc_securable:
            securable_full_name: "<CATALOG>.<SCHEMA>.policy_docs_index"
            securable_type: "TABLE"
            permission: "SELECT"
```

Set the prompt registry value:
```yaml
          - name: PROMPT_REGISTRY_NAME
            value: "<CATALOG>.<SCHEMA>.freshmart_system_prompt"
```

---

## Step 15: Deploy to Databricks Apps

```bash
# Validate
databricks bundle validate -t dev

# Deploy
databricks bundle deploy -t dev

# Deploy source code to the app
DATABRICKS_USERNAME=$(databricks current-user me | jq -r .userName)
databricks apps deploy retail-grocery-ltm-memory \
  --source-code-path /Workspace/Users/$DATABRICKS_USERNAME/.bundle/retail_grocery_ltm_memory/dev/files
```

---

## Step 16: Grant App Service Principal Permissions

```bash
# Get the app's service principal
SP_CLIENT_ID=$(databricks apps get retail-grocery-ltm-memory --output json | jq -r '.service_principal_client_id')

# Grant Lakebase permissions
uv run python scripts/grant_lakebase_permissions.py "$SP_CLIENT_ID" \
  --memory-type langgraph-short-term --project <PROJECT-NAME> --branch <BRANCH-NAME>
uv run python scripts/grant_lakebase_permissions.py "$SP_CLIENT_ID" \
  --memory-type langgraph-long-term --project <PROJECT-NAME> --branch <BRANCH-NAME>
```

Also grant the SP access to the Genie Space: **Genie > your space > Share** > Add the service principal with **Can Run**.

---

## Step 17: Start and Verify the App

```bash
databricks apps start retail-grocery-ltm-memory

# Get the URL
APP_URL=$(databricks apps get retail-grocery-ltm-memory --output json | jq -r '.url')
echo "App URL: $APP_URL"

# Test the API
TOKEN=$(databricks auth token | jq -r .access_token)
curl -X POST "${APP_URL}/invocations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input": [{"role": "user", "content": "What stores do you have?"}]}'
```

Open the app URL in your browser and try the same prompts from Step 13.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `relation "store" does not exist` | Memory tables not created — restart the app, it auto-creates on first request |
| App stuck in `STOPPED` | `databricks apps start retail-grocery-ltm-memory` |
| `302` error on API call | Use OAuth token (`databricks auth token`), not a PAT |
| Lakebase permission denied | Re-run Step 16 (deployed). For local: verify CLI auth is valid (`databricks auth token`) |
| `bundle validate` fails | Check `value_from` names match resource `name` fields exactly |
| Vector Search returns empty | Verify the index has data in Catalog Explorer |
| Local app Lakebase error | Check PGHOST/PGUSER in `.env`. If token expired, restart app after `databricks auth login` |
| Genie permission error | Grant Can Run to your user (Step 11) or app SP (Step 16) |
| View app logs | **Apps > retail-grocery-ltm-memory > Logs** or `databricks apps get-logs retail-grocery-ltm-memory` |
