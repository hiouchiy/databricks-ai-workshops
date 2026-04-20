**[日本語](#ja)** | **[English](#en)**

---

<a id="ja"></a>

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


### チーム利用時の権限共有（代表者が実施）

**推奨: Databricks アカウントレベルグループを使用**（新規メンバー追加時は再実行不要）

```bash
# 事前: Admin がアカウントレベルグループ（例: workshop-members）を作成し、
#       参加メンバーをそのグループに追加
uv run grant-team-access --group workshop-members
```

**個別指定方式**（新規メンバー追加時は再実行が必要）

```bash
uv run grant-team-access alice@company.com bob@company.com
```

以下の権限が一括で付与されます（両方式共通）：

| リソース | 付与される権限 | 層 |
|---|---|---|
| **Unity Catalog（カタログ）** | USE_CATALOG | - |
| **Unity Catalog（スキーマ）** | USE_SCHEMA, SELECT, MODIFY | - |
| **MLflow Experiment** | CAN_MANAGE（モニタリング + 評価） | - |
| **Genie Space** | CAN_RUN | - |
| **Lakebase プロジェクト** | CAN_USE | 層1 |
| **Lakebase PostgreSQL** | ロール作成 + スキーマ USAGE/CREATE + テーブル SELECT/INSERT/UPDATE/DELETE | 層2 |
| **SQL Warehouse** | CAN_USE | - |

### Lakebase の2層権限モデルと運用上の注意

Lakebase の権限は **2層構造** になっています：

- **層1（プロジェクト接続権限）**: Databricks ACL。`CAN_USE` があればプロジェクトに接続可
- **層2（PostgreSQL 内部権限）**: PG レベルのロール + スキーマ/テーブル GRANT

`grant-team-access` は両方を一度に付与しますが、**テーブル権限はテーブルが作成されていないと付与されません**。代表者がクイックスタートを完了すれば `init_lakebase_tables` フェーズで自動的にテーブルが作成されているため、**代表者のクイックスタート後に `grant-team-access` を実行** すれば完結します。

### メンバーごとの Lakebase ブランチ（自動）

メンバーがクイックスタートで代表者の既存プロジェクトを指定すると、**自動的に `{project}-{username}` という個人ブランチが作成されます**：

```bash
# メンバーの実行例（ブランチ名は指定しない）
uv run quickstart --catalog <CATALOG> --schema <SCHEMA> \
  --vs-endpoint <VS-ENDPOINT> --lakebase-autoscaling-project <PROJECT>
# → fresh-mart-0416-alice のような個人ブランチが自動作成
```

各メンバーは自分専用ブランチを持つため：
- 他メンバーとデータが混ざらない
- Lakebase の高速ブランチング機能を体験できる
- テーブル権限の問題が発生しない（メンバーが自分のブランチで作るテーブルは自動的に自分が所有）

> **アプリの SP 権限について:** 各メンバーが自分のアプリをデプロイした後に、ステップ 11-6 で `uv run grant-sp-permissions` を各自で実行してください。代表者が事前に設定することはできません（SP はアプリ作成時に生成されるため）。

コマンド実行後、以下の情報をメンバーに共有してください：
- カタログ名・スキーマ名
- VS エンドポイント名
- Genie Space ID
- **Lakebase プロジェクト名**（ブランチ名は不要、メンバーごとに自動生成）
- MLflow Experiment ID（モニタリング + 評価）

### 参加者の事前準備

以下のツールをインストールし、動作確認を済ませてください。


| ツール            | インストール方法                                                             | 確認コマンド                            |
| -------------- | -------------------------------------------------------------------- | --------------------------------- |
| Databricks CLI | `brew tap databricks/tap && brew install databricks`                 | `databricks --version`（**v0.297.2 以上**） |
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

## ステップ 0：セットアップノートブックのインポート（推奨）

このワークショップでは、一部のコマンドを Databricks 上で実行する必要があります。`workshop_setup.py` に全てのコマンドが集約されていますので、ワークスペースにインポートしておくと便利です。

1. Databricks ワークスペースの左メニュー > **Workspace** > 自分のユーザーフォルダ
2. **Import** > `workshop_setup.py` ファイルをアップロード
3. ノートブック先頭の「設定」セルでプレースホルダーを自分の値に設定

> 以降のステップで「SQL エディタまたはノートブック」と記載された箇所は、このノートブックの該当セルを実行するだけで OK です。

---

## ステップ 1：カタログとスキーマの作成

> 管理者が事前に作成済みの場合はスキップしてください。

**方法 A：SQL エディタまたはノートブック**（`workshop_setup.py` のステップ 1 セルを実行）

```sql
CREATE CATALOG IF NOT EXISTS <CATALOG>;
CREATE SCHEMA IF NOT EXISTS <CATALOG>.<SCHEMA>;
```

**方法 B：ローカル CLI**

```bash
databricks api post /api/2.0/sql/statements --profile DEFAULT --json '{
  "warehouse_id": "<WAREHOUSE-ID>",
  "statement": "CREATE CATALOG IF NOT EXISTS `<CATALOG>`",
  "wait_timeout": "30s"
}'
databricks api post /api/2.0/sql/statements --profile DEFAULT --json '{
  "warehouse_id": "<WAREHOUSE-ID>",
  "statement": "CREATE SCHEMA IF NOT EXISTS `<CATALOG>`.`<SCHEMA>`",
  "wait_timeout": "30s"
}'
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

> **重要：** 次のステップで Vector Search インデックスを作成するため、テーブルに Change Data Feed を有効化します。
>
> **方法 A：ノートブック**（`workshop_setup.py` のステップ 3 セルを実行）
>
> **方法 B：SQL エディタ**
> ```sql
> ALTER TABLE <CATALOG>.<SCHEMA>.policy_docs_chunked
>   SET TBLPROPERTIES (delta.enableChangeDataFeed = true);
> ```
>
> **方法 C：ローカル CLI**
> ```bash
> databricks api post /api/2.0/sql/statements --profile DEFAULT --json '{
>   "warehouse_id": "<WAREHOUSE-ID>",
>   "statement": "ALTER TABLE `<CATALOG>`.`<SCHEMA>`.policy_docs_chunked SET TBLPROPERTIES (delta.enableChangeDataFeed = true)",
>   "wait_timeout": "30s"
> }'
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

> **注意：** デフォルトでは `PROMPT_REGISTRY_NAME` の設定は不要です。日本語のシステムプロンプトは `agent.py` にハードコードされています。

### Prompt Registry を使う場合（オプション）

システムプロンプトを Unity Catalog でバージョン管理したい場合は、以下を実行してください。プロンプトのバージョン管理・A/Bテスト・ロールバックが可能になります。

**1. プロンプトの登録**（1回だけ実行）：

```bash
uv run register-prompt --name <CATALOG>.<SCHEMA>.freshmart_system_prompt
```

**2. `.env` に追加**：

```bash
PROMPT_REGISTRY_NAME=<CATALOG>.<SCHEMA>.freshmart_system_prompt
```

**3. `app.yaml` に追加**（Apps デプロイ時）：

```yaml
  - name: PROMPT_REGISTRY_NAME
    value: "<CATALOG>.<SCHEMA>.freshmart_system_prompt"
```

> 設定すると、`agent.py` はハードコード版ではなく Prompt Registry からプロンプトを読み込みます。Registry に登録されたプロンプトの `@production` エイリアスが使われます。

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

**1. 権限の付与**（SQL エディタ、ノートブック、または CLI）：

```sql
GRANT MODIFY, SELECT ON SCHEMA <CATALOG>.<SCHEMA> TO `your.email@company.com`;
```

**2. トレーステーブルの初期作成**（`workshop_setup.py` の「トレース送信先の設定」セルを実行）

> **注意：** `set_experiment_trace_location` は Databricks ノートブック上でのみ実行可能です。ローカルからは実行できません。

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

> **`--no-ui` モード：** チャット UI なしでバックエンド（API）のみ起動したい場合：
> ```bash
> uv run start-app --no-ui
> ```
> API テストや評価スクリプト実行時に便利です。`curl` で直接 `http://localhost:8000/invocations` にリクエストを送れます。
>
> アーキテクチャの詳細は [ARCHITECTURE.md](ARCHITECTURE.md) を参照してください。

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
> - Databricks CLI **v0.297.2 以上**（`brew upgrade databricks` で更新）
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

### 最初に変数を設定

以降のコマンドで繰り返し使う値を変数に設定しておくと便利です：

```bash
# 参加者ごとにユニークなアプリ名（例: freshmart-agent-taro）
export APP_NAME="<あなたのアプリ名>"

# あなたの Databricks メールアドレス
export MY_EMAIL=$(databricks current-user me --profile DEFAULT -o json | jq -r .userName)
echo "APP_NAME: $APP_NAME"
echo "MY_EMAIL: $MY_EMAIL"
```

### 11-1. `databricks.yml` の編集

`databricks.yml` を開き、以下の箇所を自分の環境に合わせて編集します（`uv run quickstart` を使った場合は自動更新されます）。

**アプリ名**（参加者ごとにユニークにしてください）：

```yaml
      name: "<あなたのアプリ名>"  # 例: freshmart-agent-taro
```

> `name:` はファイル内に 2 箇所あります（`dev` と `prod` の両方）。両方とも同じ名前にしてください。

**リソース定義**（ステップ 7〜8 で控えた値を入力）：

```yaml
      resources:
        - name: "experiment"
          experiment:
            experiment_id: "<MONITORING-EXPERIMENT-ID>"   # ← ステップ 7 の値
            permission: "CAN_MANAGE"
        - name: "retail_grocery_genie"
          genie_space:
            name: "フレッシュマート 小売データ"
            space_id: "<GENIE-SPACE-ID>"                  # ← ステップ 5 の値
            permission: "CAN_RUN"
        - name: "policy_docs_index"
          uc_securable:
            securable_full_name: "<CATALOG>.<SCHEMA>.policy_docs_index"  # ← ステップ 4 の値
            securable_type: "TABLE"
            permission: "SELECT"
        - name: "postgres"
          postgres:
            branch: "projects/<PROJECT-NAME>/branches/<BRANCH-NAME>"      # ← ステップ 6 の値
            database: "projects/<PROJECT-NAME>/branches/<BRANCH-NAME>/databases/databricks_postgres"
            permission: "CAN_CONNECT_AND_CREATE"
```

> `postgres` リソースバインディングにより、デプロイ時にアプリの SP へ Lakebase の接続権限（CAN_CONNECT_AND_CREATE）が自動付与されます。

**Lakebase の環境変数**（`agent.py` が project/branch 名を直接参照するため `value` で指定）：

```yaml
          - name: LAKEBASE_AUTOSCALING_PROJECT
            value: "<PROJECT-NAME>"                       # ← ステップ 6 の値
          - name: LAKEBASE_AUTOSCALING_BRANCH
            value: "<BRANCH-NAME>"                        # ← ステップ 6 の値
```

### 11-2. `app.yaml` の編集

`app.yaml` も `databricks.yml` と同様に Lakebase の値を設定します：

```yaml
  - name: LAKEBASE_AUTOSCALING_PROJECT
    value: "<PROJECT-NAME>"
  - name: LAKEBASE_AUTOSCALING_BRANCH
    value: "<BRANCH-NAME>"
```

> その他の環境変数（MLFLOW_EXPERIMENT_ID、GENIE_SPACE_ID、VECTOR_SEARCH_INDEX）は `valueFrom` でリソースバインディング経由で自動注入されるため、編集不要です。

**Delta Table トレースを使用する場合**は、以下も `app.yaml` に追加してください（`uv run quickstart` を使った場合は自動追加されます）：

```yaml
  - name: MLFLOW_TRACING_DESTINATION
    value: "<CATALOG>.<SCHEMA>"
  - name: MLFLOW_TRACING_SQL_WAREHOUSE_ID
    value: "<WAREHOUSE-ID>"
```

### 11-3. バンドルデプロイ

```bash
databricks bundle deploy -t dev --profile DEFAULT
```

初回はアプリの作成が含まれるため数分かかります。

### 11-4. アプリの起動

```bash
databricks apps start $APP_NAME --profile DEFAULT
```

コンピュートが ACTIVE になるまで待機：

```bash
databricks apps get $APP_NAME --profile DEFAULT -o json | jq '.compute_status.state'
# "ACTIVE" と表示されるまで待つ
```

### 11-5. ソースコードのデプロイ

```bash
databricks apps deploy $APP_NAME \
  --source-code-path "/Workspace/Users/$MY_EMAIL/.bundle/retail_grocery_ltm_memory/dev/files" \
  --profile DEFAULT
```

> **注意：** デプロイ後、npm install → npm build → アプリ起動に **3〜5 分** かかります。ステータスが RUNNING になるまで待ってから動作確認してください：
> ```bash
> databricks apps get $APP_NAME --profile DEFAULT -o json | jq '.app_status.state'
> ```

### 11-6. サービスプリンシパルへのパーミッション付与

リソースバインディングにより、以下の権限はデプロイ時に **自動付与** されます：

| リソース | 自動付与される権限 |
|---|---|
| MLflow Experiment | CAN_MANAGE |
| Genie Space | CAN_RUN |
| Vector Search Index | SELECT |
| Lakebase プロジェクト | CAN_CONNECT_AND_CREATE（接続権限） |

以下は**手動で付与**する必要があります：
- **Unity Catalog スキーマ権限**（USE CATALOG, USE SCHEMA, SELECT, MODIFY）
- **Lakebase PostgreSQL 内部権限**（スキーマ・テーブルレベルの USAGE, SELECT, INSERT 等）

#### 方法 A：ワンコマンドで一括付与（推奨）

ローカルからすべての SP 権限を一括で付与できます：

```bash
uv run grant-sp-permissions
```

アプリ名は `databricks.yml` から自動取得されます。以下の権限が付与されます：
1. **Unity Catalog** — USE CATALOG, USE SCHEMA, SELECT, MODIFY（データスキーマ + トレーススキーマ）
2. **Lakebase PostgreSQL** — ロール作成 + 全メモリテーブルの USAGE, SELECT, INSERT, UPDATE, DELETE

> アプリ名を指定する場合は `--app-name <名前>` を追加してください。

#### 方法 B：手動で個別に付与

<details>
<summary>手動手順を表示</summary>

```bash
# SP Client ID を取得
SP_CLIENT_ID=$(databricks apps get $APP_NAME --output json --profile DEFAULT | jq -r '.service_principal_client_id')
echo "SP Client ID: $SP_CLIENT_ID"
```

**Unity Catalog パーミッション**（SQL エディタ、`workshop_setup.py` ノートブック、または CLI）：

エージェントがアクセスする**データスキーマ**（Genie、Vector Search）への権限：

```sql
-- データスキーマ（テーブル・VS インデックスがあるスキーマ）
GRANT USE CATALOG ON CATALOG `<CATALOG>` TO `<SP_CLIENT_ID>`;
GRANT USE SCHEMA ON SCHEMA `<CATALOG>`.`<SCHEMA>` TO `<SP_CLIENT_ID>`;
GRANT SELECT ON SCHEMA `<CATALOG>`.`<SCHEMA>` TO `<SP_CLIENT_ID>`;
```

Delta Table トレースを使用する場合は、**トレーススキーマ**への権限も必要です。データスキーマと同じ場合は上記に MODIFY を追加するだけで OK です。**別のスキーマを指定した場合は、そちらにも権限を付与**してください：

```sql
-- トレーススキーマ（データスキーマと同じ場合）
GRANT MODIFY ON SCHEMA `<CATALOG>`.`<SCHEMA>` TO `<SP_CLIENT_ID>`;

-- トレーススキーマが別の場合（例: hiroshi.my_traces）
-- GRANT USE CATALOG ON CATALOG `<TRACE_CATALOG>` TO `<SP_CLIENT_ID>`;
-- GRANT USE SCHEMA ON SCHEMA `<TRACE_CATALOG>`.`<TRACE_SCHEMA>` TO `<SP_CLIENT_ID>`;
-- GRANT SELECT, MODIFY ON SCHEMA `<TRACE_CATALOG>`.`<TRACE_SCHEMA>` TO `<SP_CLIENT_ID>`;
```

> `.env` の `MLFLOW_TRACING_DESTINATION` を確認して、データスキーマと異なる場合は両方に権限を付与してください。

**Lakebase PostgreSQL 内部パーミッション**：

> Lakebase のプロジェクト接続権限（`CAN_CONNECT_AND_CREATE`）はリソースバインディングで自動付与されますが、**PostgreSQL 内部のスキーマ・テーブル権限は別途付与が必要**です。これがないと、アプリ起動時に `permission denied for table` エラーが発生します。

```bash
uv run python scripts/grant_lakebase_permissions.py "$SP_CLIENT_ID" \
  --memory-type langgraph-short-term --project <PROJECT-NAME> --branch <BRANCH-NAME>
uv run python scripts/grant_lakebase_permissions.py "$SP_CLIENT_ID" \
  --memory-type langgraph-long-term --project <PROJECT-NAME> --branch <BRANCH-NAME>
```

</details>

#### パーミッション付与後のアプリ再起動

```bash
databricks apps stop $APP_NAME --profile DEFAULT
databricks apps start $APP_NAME --profile DEFAULT
```

### 11-7. 動作確認

> **注意：** アプリ起動後、フロントエンドが完全に利用可能になるまで **3〜5 分** かかります。

**ブラウザ**：アプリの URL にアクセスしてチャット画面が表示されることを確認

```bash
databricks apps get $APP_NAME --profile DEFAULT -o json | jq -r '.url'
```

**API テスト**：

```bash
APP_URL=$(databricks apps get $APP_NAME --output json --profile DEFAULT | jq -r '.url')
TOKEN=$(databricks auth token --profile DEFAULT -o json | jq -r .access_token)

curl -X POST "${APP_URL}/invocations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input": [{"role": "user", "content": "返品ポリシーを教えてください"}]}'
```

### 11-8. コードや設定を変更した後の再デプロイ

ローカルで `app.yaml`、`agent.py`、フロントエンドなどを編集した後、変更を Apps に反映するには以下を実行します：

```bash
# 1. バンドルを再同期（ローカル → ワークスペース）
databricks bundle deploy -t dev --profile DEFAULT

# 2. アプリにソースコードを再デプロイ
databricks apps deploy $APP_NAME \
  --source-code-path "/Workspace/Users/$MY_EMAIL/.bundle/retail_grocery_ltm_memory/dev/files" \
  --profile DEFAULT
```

> **注意：** 再デプロイ後、npm install/build が走るため **3〜5 分** かかります。ステータスが RUNNING になるまで待ってください。
>
> `app.yaml` の `env` セクションを変更した場合は、アプリの再起動も必要です：
> ```bash
> databricks apps stop $APP_NAME --profile DEFAULT
> databricks apps start $APP_NAME --profile DEFAULT
> ```

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
| `bundle deploy` でリソースエラー | Databricks CLI を v0.297.2 以上に更新（`brew upgrade databricks`） |
| `bundle deploy` で `openpgp: key expired` | Terraform 署名鍵の期限切れ。CLI を v0.297.2 以上に更新（`brew upgrade databricks`）で解消 |
| Apps の上限エラー | 不要なアプリを削除してから再デプロイ |
| Apps UI でリソースが空 | CLI が古い。v0.297.2 以上ならリソースバインディングが正しく反映される |

---

## リソースのクリーンアップ

ワークショップで作成したリソースを一括削除するには、以下を実行します：

```bash
uv run cleanup
```

以下のリソースを一つずつ確認しながら削除します：

1. Databricks App
2. MLflow Experiments（モニタリング + 評価）
3. Vector Search インデックス
4. Genie Space
5. Lakebase プロジェクト
6. Unity Catalog スキーマ（CASCADE — テーブル・トレーステーブルも削除）
7. ワークスペースのバンドルファイル
8. ローカルファイル（`.env`、`.venv`、ログ）

> **注意：** 各リソースの削除前に確認が表示されます。不要なものだけ選択して削除できます。

---

<a id="en"></a>

# Workshop: Building a Retail Grocery AI Agent on Databricks

Build and deploy a conversational AI agent that combines Genie, Vector Search, and long-term memory.

---

## Prerequisites (Complete Before Workshop)

### Workspace Administrator (Admin) Preparation

Only **one person** per team needs to complete the following steps; all participants can then share these resources.


| #   | Task                                    | Reason                                                                                                      |
| --- | --------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| 1   | Create participant catalog & grant permissions | Participants may not have catalog creation privileges. Grant `USE CATALOG` / `CREATE SCHEMA` to all participants |
| 2   | Verify SQL Warehouse                    | Confirm the shared warehouse is RUNNING and share the Warehouse ID with participants                        |
| 3   | Pre-create Vector Search endpoint       | Creating a new endpoint takes several minutes; prepare one shared endpoint and share the endpoint name      |
| 4   | Verify Foundation Model API             | Confirm the `databricks-claude-sonnet-4-5` endpoint is available                                            |
| 5   | Verify Lakebase is enabled              | Confirm Lakebase is enabled in the workspace                                                                |
| 6   | Check Databricks Apps slot availability | If near the limit, delete unused apps beforehand (only needed if deploying Apps)                            |
| 7   | Verify PyPI / npm access                | Confirm that package installation is possible from local environments                                       |


### Sharing Permissions for Team Use (Team Lead)

When working as a team, the team lead should run the following locally after completing the quickstart:

```bash
uv run grant-team-access member1@company.com member2@company.com
```

The following permissions are granted in bulk:

| Resource | Permissions Granted |
|---|---|
| **Unity Catalog** | USE CATALOG, USE SCHEMA, SELECT, MODIFY |
| **MLflow Experiment** | CAN_MANAGE (monitoring + evaluation) |
| **Genie Space** | CAN_RUN |
| **Lakebase** | Project CAN_USE + DB schema permissions |
| **SQL Warehouse** | CAN_USE |

To add members later, simply re-run the same command (idempotent).

> **About App SP permissions:** Each member must run Step 11-6 themselves after deploying their own app. The team lead cannot configure this in advance (the SP is generated when the app is created).

Share the following information displayed after running the command with team members:
- Catalog name and schema name
- Genie Space ID
- Lakebase project name and branch name
- MLflow Experiment IDs (monitoring + evaluation)

Members can run the quickstart and select "Enter existing ID" for MLflow Experiment, then start immediately from Step 9.

### Participant Preparation

Install the following tools and verify they work correctly.


| Tool           | Installation                                                                | Verification Command                        |
| -------------- | --------------------------------------------------------------------------- | ------------------------------------------- |
| Databricks CLI | `brew tap databricks/tap && brew install databricks`                        | `databricks --version` (**v0.297.2 or later**) |
| uv             | [Installation Guide](https://docs.astral.sh/uv/getting-started/installation/) | `uv --version`                              |
| Node.js 20+    | [nodejs.org](https://nodejs.org) or `nvm install 20`                        | `node --version`                            |
| jq             | `brew install jq`                                                           | `jq --version`                              |


**Databricks CLI authentication setup:**

```bash
databricks auth login --host https://<your-workspace>.cloud.databricks.com --profile DEFAULT
databricks current-user me  # Success if your username is displayed
```

**Clone the repository and install dependencies:**

```bash
git clone https://github.com/hiouchiy/databricks-ai-workshops.git
cd databricks-ai-workshops/advanced

# Install Python dependencies
uv venv .venv
uv sync

# Install Node.js dependencies
cd e2e-chatbot-app-next && npm install && cd ..
```

---

## Placeholders

The following values are used throughout the workshop. Replace them with values provided by the instructor or values you created yourself.


| Placeholder                    | Description                    | Example                                  |
| ------------------------------ | ------------------------------ | ---------------------------------------- |
| `<CATALOG>`                    | Unity Catalog catalog name     | `my_catalog`                             |
| `<SCHEMA>`                     | Schema name                    | `retail_agent`                           |
| `<WAREHOUSE-ID>`               | SQL Warehouse ID               | Obtain via `databricks warehouses list`  |
| `<VS-ENDPOINT>`                | Vector Search endpoint name    | `dbdemos_vs_endpoint` (if using existing) |
| `<PROJECT-NAME>`               | Lakebase project name          | `freshmart-agent-yourname`               |
| `<BRANCH-NAME>`                | Lakebase branch name           | `production`                             |
| `<GENIE-SPACE-ID>`             | Genie Space ID                 | `01ef...abcd` (from URL)                 |
| `<MONITORING-EXPERIMENT-ID>`   | MLflow monitoring experiment ID | `1159599289265540`                       |
| `<EVALUATION-EXPERIMENT-ID>`   | MLflow evaluation experiment ID | `1159599289265541`                       |


---

## Step 0: Import Setup Notebook (Recommended)

This workshop requires running some commands on Databricks. All commands are consolidated in `workshop_setup.py`, so it is convenient to import it into your workspace.

1. Databricks workspace left menu > **Workspace** > your user folder
2. **Import** > upload the `workshop_setup.py` file
3. Set the placeholders to your values in the "Settings" cell at the top of the notebook

> In subsequent steps, wherever it says "SQL editor or notebook", you can simply run the corresponding cell in this notebook.

---

## Step 1: Create Catalog and Schema

> Skip this step if the administrator has already created them.

**Option A: SQL editor or notebook** (run the Step 1 cell in `workshop_setup.py`)

```sql
CREATE CATALOG IF NOT EXISTS <CATALOG>;
CREATE SCHEMA IF NOT EXISTS <CATALOG>.<SCHEMA>;
```

**Option B: Local CLI**

```bash
databricks api post /api/2.0/sql/statements --profile DEFAULT --json '{
  "warehouse_id": "<WAREHOUSE-ID>",
  "statement": "CREATE CATALOG IF NOT EXISTS `<CATALOG>`",
  "wait_timeout": "30s"
}'
databricks api post /api/2.0/sql/statements --profile DEFAULT --json '{
  "warehouse_id": "<WAREHOUSE-ID>",
  "statement": "CREATE SCHEMA IF NOT EXISTS `<CATALOG>`.`<SCHEMA>`",
  "wait_timeout": "30s"
}'
```

---

## Step 2: Generate Structured Data

```bash
cd ../data
```

Specify the catalog and schema names via environment variables and run (no file edits required):

```bash
CATALOG=<CATALOG> SCHEMA=<SCHEMA> python3 execute_sql.py --profile DEFAULT --warehouse-id <WAREHOUSE-ID>
```

Six tables are created: customers (200 records), products (~500 records), stores (10 records), transactions (2,000 records), transaction_items (~10,000 records), and payment_history (400 records).

All data is generated in Japanese (Japanese names, Japanese addresses, Japanese supermarket products).

> **Estimated time:** approximately 5-10 minutes

---

## Step 3: Generate Policy Document Chunks

Similarly, specify the catalog and schema names via environment variables and run:

```bash
CATALOG=<CATALOG> SCHEMA=<SCHEMA> python3 execute_chunking.py --profile DEFAULT --warehouse-id <WAREHOUSE-ID>
```

Seven Japanese policy documents (returns, shipping, membership programs, etc.) are chunked and written to the `policy_docs_chunked` table.

> **Important:** Enable Change Data Feed on the table to create a Vector Search index in the next step.
>
> **Option A: Notebook** (run the Step 3 cell in `workshop_setup.py`)
>
> **Option B: SQL editor**
> ```sql
> ALTER TABLE <CATALOG>.<SCHEMA>.policy_docs_chunked
>   SET TBLPROPERTIES (delta.enableChangeDataFeed = true);
> ```
>
> **Option C: Local CLI**
> ```bash
> databricks api post /api/2.0/sql/statements --profile DEFAULT --json '{
>   "warehouse_id": "<WAREHOUSE-ID>",
>   "statement": "ALTER TABLE `<CATALOG>`.`<SCHEMA>`.policy_docs_chunked SET TBLPROPERTIES (delta.enableChangeDataFeed = true)",
>   "wait_timeout": "30s"
> }'
> ```

```bash
cd ../advanced
```

---

## Step 4: Create Vector Search Index

> **Prerequisite:** Use the Vector Search endpoint pre-created by the instructor.
> Endpoint name: `<VS-ENDPOINT>` (use the name provided by the instructor)
>
> If creating your own, go to **Compute > Vector Search > Create Endpoint** in the Databricks UI and wait until it becomes READY.

Navigate to `<CATALOG>.<SCHEMA>.policy_docs_chunked` in **Catalog Explorer**:

1. Click **Create > Vector Search Index**
2. Configure as follows:
  - Name: `policy_docs_index`
  - Primary key: `chunk_id`
  - Endpoint: `<VS-ENDPOINT>`
  - Source column: `content`
  - Embedding model: `databricks-qwen3-embedding-0-6b`
  - Sync mode: Triggered
3. Click **Create**

Note the full path: `<CATALOG>.<SCHEMA>.policy_docs_index`

> **Estimated time:** Initial index sync takes 1-5 minutes. Wait until the status becomes READY.
> You can proceed to the next step while waiting.

---

## Step 5: Create Genie Space

Databricks UI: **Genie > New Genie Space**

1. Name: `FreshMart Retail Data`
2. Add all 6 tables from the schema created in Step 1:
  - `customers`, `products`, `stores`, `transactions`, `transaction_items`, `payment_history`
3. Select the SQL Warehouse and click **Create**
4. Copy the **Space ID** from the URL (the last part of the URL)

---

## Step 6: Create Lakebase Autoscaling Instance

```bash
# Create the project
databricks api post "/api/2.0/postgres/projects?project_id=<PROJECT-NAME>" --json '{}'
```

A branch is automatically created. Verify the branch name:

```bash
databricks api get /api/2.0/postgres/projects/<PROJECT-NAME>/branches \
  | jq '.branches[].name'
```

> **Note:** The branch name is auto-generated based on the project name (e.g., `<PROJECT-NAME>-branch`). Save it for later use in `.env`.

Retrieve the PGHOST (`<BRANCH-NAME>` should be replaced with the name confirmed above):

```bash
databricks api get /api/2.0/postgres/projects/<PROJECT-NAME>/branches/<BRANCH-NAME>/endpoints \
  | jq -r '.endpoints[0].status.hosts.host'
```

> **Note:** The endpoint may take 1-2 minutes to become ACTIVE.

---

## Step 7: Create MLflow Experiments

Create **two experiments**: one for monitoring (trace logging during app execution) and one for evaluation (when running evaluation scripts).

```bash
DATABRICKS_USERNAME=$(databricks current-user me -o json | jq -r .userName)

# For monitoring (trace logging during app execution)
databricks experiments create-experiment "/Users/$DATABRICKS_USERNAME/freshmart-agent-monitoring"

# For evaluation (when running evaluation scripts)
databricks experiments create-experiment "/Users/$DATABRICKS_USERNAME/freshmart-agent-evaluation"
```

Note the `experiment_id` returned for each.

---

## Step 8: Set Environment Variables

```bash
cp .env.example .env
```

Edit `.env` as follows. Enter the values you noted in previous steps:

```bash
DATABRICKS_CONFIG_PROFILE=DEFAULT
DATABRICKS_HOST=https://<your-workspace>.cloud.databricks.com
MLFLOW_EXPERIMENT_ID=<MONITORING-EXPERIMENT-ID>
MLFLOW_EVAL_EXPERIMENT_ID=<EVALUATION-EXPERIMENT-ID>
LAKEBASE_AUTOSCALING_PROJECT=<PROJECT-NAME>
LAKEBASE_AUTOSCALING_BRANCH=<BRANCH-NAME>
GENIE_SPACE_ID=<GENIE-SPACE-ID>
VECTOR_SEARCH_INDEX=<CATALOG>.<SCHEMA>.policy_docs_index
PGHOST=<Lakebase hostname (obtained in Step 6)>
PGUSER=<your Databricks email address>
PGDATABASE=databricks_postgres
```

> **Note:** `MLFLOW_EXPERIMENT_ID` is used for trace logging (monitoring) during app execution, and `MLFLOW_EVAL_EXPERIMENT_ID` is used when running evaluation scripts.

> **Note:** By default, `PROMPT_REGISTRY_NAME` does not need to be configured. The Japanese system prompt is hardcoded in `agent.py`.

### Using Prompt Registry (Optional)

If you want to version-manage system prompts with Unity Catalog, follow the steps below. This enables prompt version management, A/B testing, and rollbacks.

**1. Register the prompt** (run once):

```bash
uv run register-prompt --name <CATALOG>.<SCHEMA>.freshmart_system_prompt
```

**2. Add to `.env`**:

```bash
PROMPT_REGISTRY_NAME=<CATALOG>.<SCHEMA>.freshmart_system_prompt
```

**3. Add to `app.yaml`** (when deploying to Apps):

```yaml
  - name: PROMPT_REGISTRY_NAME
    value: "<CATALOG>.<SCHEMA>.freshmart_system_prompt"
```

> When configured, `agent.py` loads the prompt from Prompt Registry instead of the hardcoded version. The `@production` alias of the registered prompt is used.

### Choosing the Trace Destination (Optional)

By default, traces are recorded to the MLflow Experiment. If you want to send traces to a Unity Catalog Delta Table, add the following to `.env`:

```bash
# Set only when sending traces to a Unity Catalog Delta Table
MLFLOW_TRACING_DESTINATION=<CATALOG>.<SCHEMA>
```


| Setting                          | Destination                 | Characteristics                                              |
| -------------------------------- | --------------------------- | ------------------------------------------------------------ |
| Not set (default)                | MLflow Experiment           | View traces in the Experiments UI. Easy to get started       |
| Set `<CATALOG>.<SCHEMA>`         | Unity Catalog Delta Table   | Queryable via SQL. Long-term retention. Managed by Unity Catalog permissions |


When sending to a Delta Table, the following preparation is required:

**1. Grant permissions** (SQL editor, notebook, or CLI):

```sql
GRANT MODIFY, SELECT ON SCHEMA <CATALOG>.<SCHEMA> TO `your.email@company.com`;
```

**2. Initial creation of trace tables** (run the "Trace destination settings" cell in `workshop_setup.py`)

> **Note:** `set_experiment_trace_location` can only be run in a Databricks notebook. It cannot be run locally.

> **Note:** The associated Experiment must have zero traces. If traces already exist, create a new empty Experiment:
>
> ```bash
> databricks experiments create-experiment "/Users/$DATABRICKS_USERNAME/freshmart-agent-monitoring-uc"
> ```
>
> Set the new Experiment ID in the code below and in `MLFLOW_EXPERIMENT_ID` in `.env`.

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

This automatically creates three Delta Tables in the schema:

- `mlflow_experiment_trace_otel_spans` -- Each processing step (LLM calls, tool executions, etc.)
- `mlflow_experiment_trace_otel_logs` -- Logs during trace execution
- `mlflow_experiment_trace_otel_metrics` -- Metrics such as latency and token counts

**3. Set the trace destination in `.env`** (edit locally):

```bash
MLFLOW_TRACING_DESTINATION=<CATALOG>.<SCHEMA>
```

After creating the tables, start the app and chat to have traces written to the Delta Table. You can query them via SQL:

```sql
SELECT * FROM <CATALOG>.<SCHEMA>.mlflow_experiment_trace_otel_spans
WHERE start_time > current_timestamp() - INTERVAL 1 HOUR;
```

> **Note:** `set_experiment_trace_location` can only be run in a Databricks notebook. It cannot be run from a local environment.
>
> Reference: [Send MLflow traces to Unity Catalog](https://docs.databricks.com/aws/en/mlflow3/genai/tracing/trace-unity-catalog)

---

## Step 9: Run Locally

```bash
uv run start-app
```

The backend starts at `http://localhost:8000` and the chat UI at `http://localhost:3000`.

> **`--no-ui` mode:** To start only the backend (API) without the chat UI:
> ```bash
> uv run start-app --no-ui
> ```
> Useful for API testing or running evaluation scripts. You can send requests directly to `http://localhost:8000/invocations` via `curl`.
>
> For architecture details, see [ARCHITECTURE.md](ARCHITECTURE.md).

> **If it doesn't start correctly:**
>
> - Verify that `uv sync` has completed
> - Verify that the `.env` file is configured correctly
> - Verify that `databricks auth token` can retrieve a token

### Verification

Open `http://localhost:3000` in your browser and try the following prompts:

**Genie (structured data queries):**

- "Show me the top 5 products by sales"
- "What is the cheapest product?"

**Vector Search (policy search):**

- "Tell me about the return policy. Can I return fresh produce?"
- "How much is the delivery fee?"

**Memory:**

- "I'm a vegetarian and I prefer organic products. Please remember that."
- (In a new chat) "Do you remember my preferences? Can you recommend some products?"

### Checking Traces

You can view agent traces in the Databricks UI under **Experiments > freshmart-agent-monitoring**. LLM calls, tool executions, latency, and other details are recorded for each request. Evaluation results can be viewed under **Experiments > freshmart-agent-evaluation**.

---

## Step 10 (Optional): Agent Evaluation

> **Note:** If the app is running from Step 9, press **Ctrl+C** in the terminal to stop the server before running the evaluation. The evaluation script calls the agent directly without using the server, so leaving the server running may cause port conflicts or process interference.
>
> **Note (when using Delta Table traces):** If `MLFLOW_TRACING_DESTINATION` is set in `.env`, the evaluation script automatically disables this setting during execution. This prevents errors when the Delta Table trace tables have not been created yet. Evaluation results are always recorded in the MLflow Experiment specified by `MLFLOW_EVAL_EXPERIMENT_ID`.

### Chat Evaluation (expected_facts-based)

```bash
uv run agent-evaluate-chat
```

Uses 9 fixed questions (3 simple + 3 complex + 3 out-of-scope) with expected facts to score on Correctness / RelevanceToQuery / RetrievalSufficiency / Safety / Fluency. No server startup is required; the agent is called directly for evaluation.

### Multi-turn Evaluation (Conversation Simulator)

```bash
uv run agent-evaluate
```

Uses 3 Japanese test cases where a simulated user (LLM) automatically conducts multi-turn conversations with the agent. Scoring is performed by 10 MLflow scorers (Completeness, ConversationalSafety, Fluency, KnowledgeRetention, RelevanceToQuery, Safety, ToolCallCorrectness, ToolCallEfficiency, UserFrustration, etc.).

### Advanced Multi-turn Evaluation (20 Test Cases + Custom Scorers)

```bash
uv run agent-evaluate-advanced
```

Evaluates with 20 Japanese test cases (structured data, policy search, compound questions, memory) plus 3 custom scorers:

- **tool_routing_accuracy** -- Whether the correct tool (Genie/Vector Search/Memory) is selected based on the question type
- **policy_specificity** -- Whether policy answers contain specific numbers ("48 hours", "3,000 yen", etc.)
- **retail_tone_appropriateness** -- Whether the customer service tone is appropriate (empathy, action suggestions, warmth)

Results can be viewed in the MLflow Experiments UI under the **freshmart-agent-evaluation** experiment.

---

## Step 11 (Optional): Deploying to Databricks Apps

> **Prerequisites:**
> - Databricks CLI **v0.297.2 or later** (update with `brew upgrade databricks`)
> - Available Apps slot in the workspace
> - PyPI and npm registry access from the Apps environment

> **Important:** Verify that `e2e-chatbot-app-next/package-lock.json` references the **public registry (registry.npmjs.org)**. If it contains a corporate proxy URL, `npm install` will fail in the Apps environment. To verify:
> ```bash
> grep -c "registry.npmjs.org" e2e-chatbot-app-next/package-lock.json    # ~900 means OK
> grep -c "your-proxy" e2e-chatbot-app-next/package-lock.json            # 0 means OK
> ```
> If a proxy URL is present, regenerate the lockfile:
> ```bash
> cd e2e-chatbot-app-next && rm -f package-lock.json && npm install && cd ..
> ```

### Set Variables First

It is convenient to set frequently used values as variables for the commands that follow:

```bash
# Unique app name per participant (e.g., freshmart-agent-taro)
export APP_NAME="<YOUR-APP-NAME>"

# Your Databricks email address
export MY_EMAIL=$(databricks current-user me --profile DEFAULT -o json | jq -r .userName)
echo "APP_NAME: $APP_NAME"
echo "MY_EMAIL: $MY_EMAIL"
```

### 11-1. Edit databricks.yml

Open `databricks.yml` and edit the following sections to match your environment (these are auto-updated if you used `uv run quickstart`).

**App name** (must be unique per participant):

```yaml
      name: "<YOUR-APP-NAME>"  # e.g., freshmart-agent-taro
```

> `name:` appears in 2 places in the file (`dev` and `prod`). Set both to the same name.

**Resource definitions** (enter the values noted in Steps 7-8):

```yaml
      resources:
        - name: "experiment"
          experiment:
            experiment_id: "<MONITORING-EXPERIMENT-ID>"   # <- Step 7 value
            permission: "CAN_MANAGE"
        - name: "retail_grocery_genie"
          genie_space:
            name: "FreshMart Retail Data"
            space_id: "<GENIE-SPACE-ID>"                  # <- Step 5 value
            permission: "CAN_RUN"
        - name: "policy_docs_index"
          uc_securable:
            securable_full_name: "<CATALOG>.<SCHEMA>.policy_docs_index"  # <- Step 4 value
            securable_type: "TABLE"
            permission: "SELECT"
        - name: "postgres"
          postgres:
            branch: "projects/<PROJECT-NAME>/branches/<BRANCH-NAME>"      # <- Step 6 value
            database: "projects/<PROJECT-NAME>/branches/<BRANCH-NAME>/databases/databricks_postgres"
            permission: "CAN_CONNECT_AND_CREATE"
```

> The `postgres` resource binding automatically grants Lakebase connection permissions (CAN_CONNECT_AND_CREATE) to the app's SP at deploy time.

**Lakebase environment variables** (specified as `value` because `agent.py` directly references project/branch names):

```yaml
          - name: LAKEBASE_AUTOSCALING_PROJECT
            value: "<PROJECT-NAME>"                       # <- Step 6 value
          - name: LAKEBASE_AUTOSCALING_BRANCH
            value: "<BRANCH-NAME>"                        # <- Step 6 value
```

### 11-2. Edit app.yaml

Set the Lakebase values in `app.yaml` similarly to `databricks.yml`:

```yaml
  - name: LAKEBASE_AUTOSCALING_PROJECT
    value: "<PROJECT-NAME>"
  - name: LAKEBASE_AUTOSCALING_BRANCH
    value: "<BRANCH-NAME>"
```

> Other environment variables (MLFLOW_EXPERIMENT_ID, GENIE_SPACE_ID, VECTOR_SEARCH_INDEX) are automatically injected via resource bindings using `valueFrom`, so no editing is needed.

**If using Delta Table traces**, also add the following to `app.yaml` (auto-added if you used `uv run quickstart`):

```yaml
  - name: MLFLOW_TRACING_DESTINATION
    value: "<CATALOG>.<SCHEMA>"
  - name: MLFLOW_TRACING_SQL_WAREHOUSE_ID
    value: "<WAREHOUSE-ID>"
```

### 11-3. Bundle Deploy

```bash
databricks bundle deploy -t dev --profile DEFAULT
```

The first deployment takes several minutes as it includes app creation.

### 11-4. Start the App

```bash
databricks apps start $APP_NAME --profile DEFAULT
```

Wait until compute becomes ACTIVE:

```bash
databricks apps get $APP_NAME --profile DEFAULT -o json | jq '.compute_status.state'
# Wait until "ACTIVE" is displayed
```

### 11-5. Deploy Source Code

```bash
databricks apps deploy $APP_NAME \
  --source-code-path "/Workspace/Users/$MY_EMAIL/.bundle/retail_grocery_ltm_memory/dev/files" \
  --profile DEFAULT
```

> **Note:** After deployment, npm install, npm build, and app startup take **3-5 minutes**. Wait until the status becomes RUNNING before verifying:
> ```bash
> databricks apps get $APP_NAME --profile DEFAULT -o json | jq '.app_status.state'
> ```

### 11-6. Grant Service Principal Permissions

Resource bindings **automatically grant** the following permissions at deploy time:

| Resource | Automatically Granted Permissions |
|---|---|
| MLflow Experiment | CAN_MANAGE |
| Genie Space | CAN_RUN |
| Vector Search Index | SELECT |
| Lakebase project | CAN_CONNECT_AND_CREATE (connection permission) |

The following must be **granted manually**:
- **Unity Catalog schema permissions** (USE CATALOG, USE SCHEMA, SELECT, MODIFY)
- **Lakebase PostgreSQL internal permissions** (schema/table level USAGE, SELECT, INSERT, etc.)

#### Option A: One-command bulk grant (recommended)

Grant all SP permissions in one command from your local machine:

```bash
uv run grant-sp-permissions
```

The app name is automatically read from `databricks.yml`. The following permissions are granted:
1. **Unity Catalog** -- USE CATALOG, USE SCHEMA, SELECT, MODIFY (data schema + trace schema)
2. **Lakebase PostgreSQL** -- Role creation + USAGE, SELECT, INSERT, UPDATE, DELETE on all memory tables

> To specify the app name, add `--app-name <NAME>`.

#### Option B: Grant manually one by one

<details>
<summary>Show manual steps</summary>

```bash
# Retrieve SP Client ID
SP_CLIENT_ID=$(databricks apps get $APP_NAME --output json --profile DEFAULT | jq -r '.service_principal_client_id')
echo "SP Client ID: $SP_CLIENT_ID"
```

**Unity Catalog permissions** (SQL editor, `workshop_setup.py` notebook, or CLI):

Permissions for the **data schema** (Genie, Vector Search) that the agent accesses:

```sql
-- Data schema (schema containing tables and VS index)
GRANT USE CATALOG ON CATALOG `<CATALOG>` TO `<SP_CLIENT_ID>`;
GRANT USE SCHEMA ON SCHEMA `<CATALOG>`.`<SCHEMA>` TO `<SP_CLIENT_ID>`;
GRANT SELECT ON SCHEMA `<CATALOG>`.`<SCHEMA>` TO `<SP_CLIENT_ID>`;
```

If using Delta Table traces, permissions for the **trace schema** are also required. If it is the same as the data schema, just add MODIFY to the above. **If a different schema is specified, grant permissions on that schema as well**:

```sql
-- Trace schema (same as data schema)
GRANT MODIFY ON SCHEMA `<CATALOG>`.`<SCHEMA>` TO `<SP_CLIENT_ID>`;

-- If trace schema is different (e.g., hiroshi.my_traces)
-- GRANT USE CATALOG ON CATALOG `<TRACE_CATALOG>` TO `<SP_CLIENT_ID>`;
-- GRANT USE SCHEMA ON SCHEMA `<TRACE_CATALOG>`.`<TRACE_SCHEMA>` TO `<SP_CLIENT_ID>`;
-- GRANT SELECT, MODIFY ON SCHEMA `<TRACE_CATALOG>`.`<TRACE_SCHEMA>` TO `<SP_CLIENT_ID>`;
```

> Check `MLFLOW_TRACING_DESTINATION` in `.env` and grant permissions on both schemas if it differs from the data schema.

**Lakebase PostgreSQL internal permissions**:

> The Lakebase project connection permission (`CAN_CONNECT_AND_CREATE`) is automatically granted via resource bindings, but **PostgreSQL internal schema/table permissions must be granted separately**. Without this, a `permission denied for table` error occurs at app startup.

```bash
uv run python scripts/grant_lakebase_permissions.py "$SP_CLIENT_ID" \
  --memory-type langgraph-short-term --project <PROJECT-NAME> --branch <BRANCH-NAME>
uv run python scripts/grant_lakebase_permissions.py "$SP_CLIENT_ID" \
  --memory-type langgraph-long-term --project <PROJECT-NAME> --branch <BRANCH-NAME>
```

</details>

#### Restart the App After Granting Permissions

```bash
databricks apps stop $APP_NAME --profile DEFAULT
databricks apps start $APP_NAME --profile DEFAULT
```

### 11-7. Verify

> **Note:** After starting the app, it takes **3-5 minutes** for the frontend to become fully available.

**Browser**: Access the app URL and verify the chat interface is displayed

```bash
databricks apps get $APP_NAME --profile DEFAULT -o json | jq -r '.url'
```

**API test**:

```bash
APP_URL=$(databricks apps get $APP_NAME --output json --profile DEFAULT | jq -r '.url')
TOKEN=$(databricks auth token --profile DEFAULT -o json | jq -r .access_token)

curl -X POST "${APP_URL}/invocations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input": [{"role": "user", "content": "Tell me about the return policy"}]}'
```

### 11-8. Redeploying After Changes

After editing `app.yaml`, `agent.py`, the frontend, etc. locally, run the following to push changes to Apps:

```bash
# 1. Re-sync bundle (local -> workspace)
databricks bundle deploy -t dev --profile DEFAULT

# 2. Re-deploy source code to the app
databricks apps deploy $APP_NAME \
  --source-code-path "/Workspace/Users/$MY_EMAIL/.bundle/retail_grocery_ltm_memory/dev/files" \
  --profile DEFAULT
```

> **Note:** After redeployment, npm install/build runs, so it takes **3-5 minutes**. Wait until the status becomes RUNNING.
>
> If you changed the `env` section in `app.yaml`, an app restart is also required:
> ```bash
> databricks apps stop $APP_NAME --profile DEFAULT
> databricks apps start $APP_NAME --profile DEFAULT
> ```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `python3: command not found` | Verify Python 3.11 or later is installed. `python` may also work |
| PyPI connection error during `uv sync` | Check internet connection. On corporate networks, verify internal PyPI mirror or proxy settings |
| `npm install` crashes in Apps environment | `package-lock.json` contains corporate proxy URLs. Regenerate with `rm -f package-lock.json && npm install` for public registry lockfile |
| `delta.enableChangeDataFeed` error | CDF enablement from Step 3 was not executed. Run `ALTER TABLE` in the SQL editor |
| VS index not becoming READY | Check status in Catalog Explorer. Verify the endpoint is ONLINE |
| Lakebase `project_id is required` | Specify `?project_id=<NAME>` in the API query parameter (in the URL, not the JSON body) |
| `experiments create --name` error | Use `experiments create-experiment "<NAME>"` |
| `couldn't get a connection after 30 sec` | Lakebase SP permissions not granted. Execute the Lakebase permissions in Step 11-6 and restart the app |
| `relation "store" does not exist` | Memory tables not created. Restart the app; they are auto-created on the first request |
| `302` error on API calls | Use OAuth token (`databricks auth token`) instead of PAT |
| 502 Bad Gateway after deployment | Frontend npm build is still in progress. Wait 3-5 minutes and try again |
| Resource error during `bundle deploy` | Update Databricks CLI to v0.297.2 or later (`brew upgrade databricks`) |
| `bundle deploy` fails with `openpgp: key expired` | Terraform signing key expired. Update CLI to v0.297.2 or later (`brew upgrade databricks`) to fix |
| Apps limit error | Delete unused apps before redeploying |
| Resources empty in Apps UI | CLI is outdated. Resource bindings are correctly reflected with v0.297.2 or later |

---

## Resource Cleanup

To delete all resources created during the workshop at once, run:

```bash
uv run cleanup
```

The following resources are deleted one by one with confirmation prompts:

1. Databricks App
2. MLflow Experiments (monitoring + evaluation)
3. Vector Search index
4. Genie Space
5. Lakebase project
6. Unity Catalog schema (CASCADE -- also deletes tables and trace tables)
7. Workspace bundle files
8. Local files (`.env`, `.venv`, logs)

> **Note:** A confirmation prompt is displayed before deleting each resource. You can selectively delete only what you no longer need.
