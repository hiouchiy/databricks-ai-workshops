**[日本語](#ワークショップ用合成データ生成)** | **[English](#synthetic-data-generation-for-workshop)**

---

# ワークショップ用合成データ生成

このフォルダには、QSICワークショップに必要な全データを生成するためのスクリプトとソースドキュメントが含まれています。Unity Catalog上に2種類のデータを作成します：

1. **構造化リテールデータ** — 合成の顧客、商品、店舗、取引、決済データ
2. **チャンク分割されたポリシードキュメント** — マークダウン形式のポリシー文書をベクトル検索用に重複ありのテキストチャンクに分割

## フォルダ構成

```
data/
├── README.md
├── create_structured_data.py     # PySparkスクリプト — 構造化テーブルを生成（クラスタまたはローカルで実行）
├── create_chunked_docs.py        # PySparkスクリプト — ポリシー文書をチャンク分割（UC Volumesへのアクセスが必要）
├── execute_sql.py                # ローカルスクリプト — SQL REST APIで構造化テーブルを生成
├── execute_chunking.py           # ローカルスクリプト — SQL REST APIでポリシー文書をチャンク分割
├── run_sql_generation.py         # ローカルスクリプト — Databricks CLIで構造化テーブルを生成
└── policy_docs/                  # ソースのマークダウンポリシードキュメント（7ファイル）
    ├── customer_service_guidelines.md
    ├── delivery_pickup_procedures.md
    ├── membership_loyalty_program.md
    ├── privacy_policy.md
    ├── product_safety_recalls.md
    ├── return_refund_policy.md
    └── store_operating_procedures.md
```

## スクリプト概要

**2つのタスク**があり、それぞれ複数の実行方法があります：

### タスク1：構造化リテールデータの生成

6つのテーブルを作成します：`customers`（200行）、`products`（約500行）、`stores`（10行）、`transactions`（2000行）、`transaction_items`（約8000行以上）、`payment_history`（400行）。

| スクリプト | 実行環境 | 方法 |
|-----------|---------|------|
| `create_structured_data.py` | Databricksクラスタまたはローカル（PySpark環境） | PySpark DataFrames |
| `execute_sql.py` | ローカルマシン | REST API経由のSQL（`urllib`） |
| `run_sql_generation.py` | ローカルマシン | `databricks api` CLI経由のSQL |

### タスク2：ベクトル検索用ポリシードキュメントのチャンク分割

`policy_docs/` 内の7つのマークダウンファイルを読み込み、重複ありのチャンク（1000文字、200文字オーバーラップ）に分割し、`policy_docs_chunked` テーブルに書き込みます。

| スクリプト | 実行環境 | 方法 |
|-----------|---------|------|
| `create_chunked_docs.py` | Databricksクラスタまたはローカル（PySpark環境） | PySpark + UC Volumes |
| `execute_chunking.py` | ローカルマシン | REST API経由のSQL（`urllib`） |

## TODO：新しいワークスペースで変更が必要な項目

### 必須の変更（全5スクリプト共通）

**すべての**スクリプトの先頭にある以下の2つの定数を更新してください：

| 定数 | 現在の値 | 変更先 |
|------|---------|--------|
| `CATALOG` | `"qsic_workshop_prep_catalog"` | 使用するUnity Catalog名 |
| `SCHEMA` | `"retail_agent"` | 対象のスキーマ名 |

更新が必要なファイル：
- [ ] `create_structured_data.py` — `CATALOG` と `SCHEMA` の行
- [ ] `create_chunked_docs.py` — `CATALOG` と `SCHEMA` の行
- [ ] `execute_sql.py` — `CATALOG` と `SCHEMA` の行
- [ ] `execute_chunking.py` — `CATALOG` と `SCHEMA` の行
- [ ] `run_sql_generation.py` — `CATALOG` と `SCHEMA` の行

### 新しいワークスペースの前提条件

- [ ] Unity Catalogで対象のカタログとスキーマを作成する
- [ ] PySparkスクリプトの場合：Databricksクラスタ上で実行する（例：`databricks jobs submit` 経由）か、PySpark + UC接続が可能なローカル環境で実行する
- [ ] `create_chunked_docs.py` の場合：UC Volumeを作成し、`policy_docs/*.md` ファイルをアップロードする：
  ```bash
  databricks fs cp ./policy_docs/ dbfs:/Volumes/<CATALOG>/<SCHEMA>/policy_docs/ --recursive --profile <profile>
  ```
- [ ] ローカルスクリプトの場合：`databricks` CLIがインストール・設定済みであること
- [ ] ローカルスクリプトの場合：SQLウェアハウスが稼働中で、そのウェアハウスIDを確認しておくこと

### 実行時引数（ローカルスクリプトのみ）

ローカルスクリプトはCLI引数を受け付けます（ワークスペースURLのハードコードは不要）：

```bash
# 構造化データの生成
python execute_sql.py --profile <PROFILE> --warehouse-id <WAREHOUSE_ID>
python run_sql_generation.py --profile <PROFILE> --warehouse-id <WAREHOUSE_ID>

# ドキュメントのチャンク分割
python execute_chunking.py --profile <PROFILE> --warehouse-id <WAREHOUSE_ID>
```

### データ生成後：Genieスペースのセットアップ

構造化リテールテーブルの作成後、ビジネスユーザーが自然言語でデータを照会できるようGenieスペースを設定します。

- [ ] **Genieスペースを作成する** — REST API（`POST /api/2.0/genie/spaces`）またはDatabricks UIを使用
  - タイトル：例 `"QSIC Retail Agent"`
  - 説明：Genieのコンテキスト用にリテールデータセットを説明
  - テーブル識別子：6つの構造化テーブルをすべて追加（`customers`、`products`、`stores`、`transactions`、`transaction_items`、`payment_history`）
  - ウェアハウスID：ProまたはServerless SQLウェアハウス
- [ ] **セットアップスクリプトを作成する**（`create_genie_space.py`）— 上記をREST APIで自動化
- [ ] Genieがリテールテーブルに対する自然言語クエリに回答できることを確認する

### チャンク分割後：ベクトル検索のセットアップ

`policy_docs_chunked` テーブルにデータが投入されたら、セマンティック検索用のベクトル検索エンドポイントとインデックスを作成します。

- [ ] **ベクトル検索エンドポイントを作成する** — Python SDKを使用：
  ```python
  from databricks.vector_search.client import VectorSearchClient
  client = VectorSearchClient()
  client.create_endpoint(name="<ENDPOINT_NAME>", endpoint_type="STANDARD")
  ```
- [ ] **エンドポイントの準備完了を待つ** — `READY` 状態になるまで数分かかる場合があります
- [ ] **チャンク分割済みポリシーテーブルにDelta Syncインデックスを作成する**：
  ```python
  client.create_delta_sync_index(
      endpoint_name="<ENDPOINT_NAME>",
      source_table_name="<CATALOG>.<SCHEMA>.policy_docs_chunked",
      index_name="<CATALOG>.<SCHEMA>.policy_docs_vs_index",
      pipeline_type="TRIGGERED",
      primary_key="chunk_id",
      embedding_source_column="content",
      embedding_model_endpoint_name="databricks-gte-large-en",
  )
  ```
- [ ] **セットアップスクリプトを作成する**（`create_vector_search.py`）— エンドポイント＋インデックス作成を自動化
- [ ] **インデックスを同期し**、類似検索で関連するポリシーチャンクが返されることを確認する

### その他の注意事項

- [ ] Databricks CLIプロファイルが正しいワークスペースホストを指していることを確認する
- [ ] サービスプリンシパルまたはユーザーが対象スキーマに対する `CREATE TABLE` および `WRITE` 権限を持っていることを確認する
- [ ] チャンク分割パラメータ（サイズ/オーバーラップ）を変更する場合は、`create_chunked_docs.py` と `execute_chunking.py` の両方を更新して同期を保つ
- [ ] すべてのスクリプトは再現性のために `random.seed(42)` を使用しており、実行ごとに同一のデータが生成されます
- [ ] ワークスペースにエンベディング生成用のFoundation Model APIエンドポイント（例：`databricks-gte-large-en`）が利用可能であることを確認する

---

**[日本語](#ワークショップ用合成データ生成)** | **[English](#synthetic-data-generation-for-workshop)**

---

# Synthetic Data Generation for Workshop

This folder contains scripts and source documents to generate all the data required for the QSIC workshop. It produces two types of data in Unity Catalog:

1. **Structured retail data** — synthetic customers, products, stores, transactions, and payments
2. **Chunked policy documents** — markdown policy docs split into overlapping text chunks for vector search

## Folder Structure

```
data/
├── README.md
├── create_structured_data.py     # PySpark script — generates structured tables (run on cluster or locally)
├── create_chunked_docs.py        # PySpark script — chunks policy docs (requires UC Volumes access)
├── execute_sql.py                # Local script — generates structured tables via SQL REST API
├── execute_chunking.py           # Local script — chunks policy docs via SQL REST API
├── run_sql_generation.py         # Local script — generates structured tables via Databricks CLI
└── policy_docs/                  # Source markdown policy documents (7 files)
    ├── customer_service_guidelines.md
    ├── delivery_pickup_procedures.md
    ├── membership_loyalty_program.md
    ├── privacy_policy.md
    ├── product_safety_recalls.md
    ├── return_refund_policy.md
    └── store_operating_procedures.md
```

## Scripts Overview

There are **two tasks**, each with multiple execution variants:

### Task 1: Generate Structured Retail Data

Creates 6 tables: `customers` (200 rows), `products` (~500), `stores` (10), `transactions` (2000), `transaction_items` (~8000+), `payment_history` (400).

| Script | Runs On | Method |
|--------|---------|--------|
| `create_structured_data.py` | Databricks cluster or local with PySpark | PySpark DataFrames |
| `execute_sql.py` | Local machine | SQL via REST API (`urllib`) |
| `run_sql_generation.py` | Local machine | SQL via `databricks api` CLI |

### Task 2: Chunk Policy Documents for Vector Search

Reads the 7 markdown files from `policy_docs/`, splits them into overlapping chunks (1000 chars, 200 overlap), and writes to a `policy_docs_chunked` table.

| Script | Runs On | Method |
|--------|---------|--------|
| `create_chunked_docs.py` | Databricks cluster or local with PySpark | PySpark + UC Volumes |
| `execute_chunking.py` | Local machine | SQL via REST API (`urllib`) |

## TODO: What to Change for a New Workspace

### Required Changes (all 5 scripts)

Update these two constants at the top of **every** script:

| Constant | Current Value | Update To |
|----------|---------------|-----------|
| `CATALOG` | `"qsic_workshop_prep_catalog"` | Your Unity Catalog name |
| `SCHEMA` | `"retail_agent"` | Your target schema name |

Files to update:
- [ ] `create_structured_data.py` — lines with `CATALOG` and `SCHEMA`
- [ ] `create_chunked_docs.py` — lines with `CATALOG` and `SCHEMA`
- [ ] `execute_sql.py` — lines with `CATALOG` and `SCHEMA`
- [ ] `execute_chunking.py` — lines with `CATALOG` and `SCHEMA`
- [ ] `run_sql_generation.py` — lines with `CATALOG` and `SCHEMA`

### Prerequisites for the New Workspace

- [ ] Create the target catalog and schema in Unity Catalog
- [ ] For PySpark scripts: run on a Databricks cluster (e.g. via `databricks jobs submit`) or locally with PySpark + UC connectivity
- [ ] For `create_chunked_docs.py`: create a UC Volume and upload `policy_docs/*.md` files:
  ```bash
  databricks fs cp ./policy_docs/ dbfs:/Volumes/<CATALOG>/<SCHEMA>/policy_docs/ --recursive --profile <profile>
  ```
- [ ] For local scripts: ensure the `databricks` CLI is installed and configured with a profile
- [ ] For local scripts: have a SQL warehouse running and note its warehouse ID

### Runtime Arguments (local scripts only)

The local scripts accept CLI arguments — no hardcoded workspace URLs:

```bash
# Structured data generation
python execute_sql.py --profile <PROFILE> --warehouse-id <WAREHOUSE_ID>
python run_sql_generation.py --profile <PROFILE> --warehouse-id <WAREHOUSE_ID>

# Document chunking
python execute_chunking.py --profile <PROFILE> --warehouse-id <WAREHOUSE_ID>
```

### Post-Data-Generation: Genie Space Setup

Once the structured retail tables are created, set up a Genie space so business users can query the data using natural language.

- [ ] **Create a Genie space** via the REST API (`POST /api/2.0/genie/spaces`) or the Databricks UI
  - Title: e.g. `"QSIC Retail Agent"`
  - Description: describe the retail dataset for Genie's context
  - Table identifiers: add all 6 structured tables (`customers`, `products`, `stores`, `transactions`, `transaction_items`, `payment_history`)
  - Warehouse ID: a Pro or Serverless SQL warehouse
- [ ] **Write a setup script** (`create_genie_space.py`) that automates the above via the REST API
- [ ] Verify Genie can answer natural language queries against the retail tables

### Post-Chunking: Vector Search Setup

Once the `policy_docs_chunked` table is populated, create a Vector Search endpoint and index for semantic retrieval.

- [ ] **Create a Vector Search endpoint** using the Python SDK:
  ```python
  from databricks.vector_search.client import VectorSearchClient
  client = VectorSearchClient()
  client.create_endpoint(name="<ENDPOINT_NAME>", endpoint_type="STANDARD")
  ```
- [ ] **Wait for the endpoint** to reach `READY` state (can take several minutes)
- [ ] **Create a Delta Sync index** on the chunked policy table:
  ```python
  client.create_delta_sync_index(
      endpoint_name="<ENDPOINT_NAME>",
      source_table_name="<CATALOG>.<SCHEMA>.policy_docs_chunked",
      index_name="<CATALOG>.<SCHEMA>.policy_docs_vs_index",
      pipeline_type="TRIGGERED",
      primary_key="chunk_id",
      embedding_source_column="content",
      embedding_model_endpoint_name="databricks-gte-large-en",
  )
  ```
- [ ] **Write a setup script** (`create_vector_search.py`) that automates endpoint + index creation
- [ ] **Sync the index** and verify similarity search returns relevant policy chunks

### Other Considerations

- [ ] Verify the Databricks CLI profile points to the correct workspace host
- [ ] Ensure the service principal or user has `CREATE TABLE` and `WRITE` permissions on the target schema
- [ ] If changing the chunking parameters (size/overlap), update both `create_chunked_docs.py` and `execute_chunking.py` to keep them in sync
- [ ] All scripts use `random.seed(42)` for reproducibility — data will be identical across runs
- [ ] Ensure the workspace has a Foundation Model API endpoint (e.g. `databricks-gte-large-en`) available for embedding generation
