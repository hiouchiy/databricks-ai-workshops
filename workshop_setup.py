# Databricks notebook source
# MAGIC %md
# MAGIC # フレッシュマート AI エージェント ワークショップ — セットアップノートブック
# MAGIC
# MAGIC このノートブックには、ローカル（`uv run quickstart`）では実行できない
# MAGIC Databricks 上専用のコマンドが含まれています。
# MAGIC
# MAGIC **セル一覧：**
# MAGIC 1. **トレース送信先の設定** — Delta Table にトレースを送信する場合のみ（全員）
# MAGIC 2. **アプリの SP 権限付与** — Databricks Apps にデプロイする場合のみ（各自）
# MAGIC
# MAGIC `uv run quickstart` を実行済みの場合、プレースホルダーは自動入力されています。
# MAGIC
# MAGIC > **チームメンバーへの権限付与**は、ローカルから `uv run grant-team-access` で実行できます。
# MAGIC > 詳細は README を参照してください。
# MAGIC
# MAGIC ---

# COMMAND ----------

# MAGIC %md
# MAGIC ## 設定（最初に実行）

# COMMAND ----------

# ── プレースホルダー（quickstart 実行済みなら自動入力されています）──
CATALOG = "<CATALOG>"                      # 例: "hiroshi"
SCHEMA = "<SCHEMA>"                        # 例: "retail_agent"
WAREHOUSE_ID = "<WAREHOUSE-ID>"            # 例: "4b9b953939869799"
MONITORING_EXPERIMENT_ID = "<MONITORING-EXPERIMENT-ID>"  # 例: "2019445883421300"
SP_CLIENT_ID = "<SP_CLIENT_ID>"            # 例: "9bf3f616-..." （Apps デプロイ後に取得）

# トレーススキーマ（データスキーマと異なる場合のみ設定。同じなら空のまま）
TRACE_CATALOG = ""                         # 例: "hiroshi"（データスキーマと異なる場合）
TRACE_SCHEMA = ""                          # 例: "my_traces"（データスキーマと異なる場合）

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## 1. トレース送信先の設定（全員・オプション）
# MAGIC
# MAGIC Unity Catalog の Delta Table にトレースを送信する場合のみ実行してください。
# MAGIC
# MAGIC **注意：**
# MAGIC - 紐付ける Experiment にはトレースが **1件も入っていない** 必要があります
# MAGIC - `set_experiment_trace_location` は **このノートブック上でのみ** 実行可能です（ローカル不可）
# MAGIC - チームメンバーが代表者と同じ Experiment を共有する場合、代表者が1回実行すれば OK

# COMMAND ----------

import os
os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = WAREHOUSE_ID

import mlflow
from mlflow.entities import UCSchemaLocation

mlflow.tracing.set_experiment_trace_location(
    location=UCSchemaLocation(catalog_name=CATALOG, schema_name=SCHEMA),
    experiment_id=MONITORING_EXPERIMENT_ID,
)
print(f"✓ トレース送信先を設定: {CATALOG}.{SCHEMA}")
print(f"  Experiment ID: {MONITORING_EXPERIMENT_ID}")
print(f"  以下のテーブルが作成されます:")
print(f"    - {CATALOG}.{SCHEMA}.mlflow_experiment_trace_otel_spans")
print(f"    - {CATALOG}.{SCHEMA}.mlflow_experiment_trace_otel_logs")
print(f"    - {CATALOG}.{SCHEMA}.mlflow_experiment_trace_otel_metrics")

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## 2. アプリの SP 権限付与（各自・Apps デプロイ時のみ）
# MAGIC
# MAGIC Databricks Apps にデプロイした後、自分のアプリの SP に権限を付与してください。
# MAGIC
# MAGIC `SP_CLIENT_ID` は以下のコマンドで取得できます：
# MAGIC ```
# MAGIC databricks apps get <アプリ名> --output json --profile DEFAULT | jq -r '.service_principal_client_id'
# MAGIC ```

# COMMAND ----------

# データスキーマへの権限（Genie、Vector Search 経由のクエリに必要）
spark.sql(f"GRANT USE CATALOG ON CATALOG `{CATALOG}` TO `{SP_CLIENT_ID}`")
spark.sql(f"GRANT USE SCHEMA ON SCHEMA `{CATALOG}`.`{SCHEMA}` TO `{SP_CLIENT_ID}`")
spark.sql(f"GRANT SELECT ON SCHEMA `{CATALOG}`.`{SCHEMA}` TO `{SP_CLIENT_ID}`")
print(f"✓ データスキーマ権限:")
print(f"  - USE CATALOG on {CATALOG}")
print(f"  - USE SCHEMA on {CATALOG}.{SCHEMA}")
print(f"  - SELECT on {CATALOG}.{SCHEMA}")

# トレーススキーマへの権限（Delta Table トレースに必要）
_tc = TRACE_CATALOG or CATALOG
_ts = TRACE_SCHEMA or SCHEMA
spark.sql(f"GRANT USE CATALOG ON CATALOG `{_tc}` TO `{SP_CLIENT_ID}`")
spark.sql(f"GRANT USE SCHEMA ON SCHEMA `{_tc}`.`{_ts}` TO `{SP_CLIENT_ID}`")
spark.sql(f"GRANT SELECT ON SCHEMA `{_tc}`.`{_ts}` TO `{SP_CLIENT_ID}`")
spark.sql(f"GRANT MODIFY ON SCHEMA `{_tc}`.`{_ts}` TO `{SP_CLIENT_ID}`")
if _tc == CATALOG and _ts == SCHEMA:
    print(f"  - MODIFY on {_tc}.{_ts}（Delta Table トレース用、同一スキーマ）")
else:
    print(f"✓ トレーススキーマ権限（{_tc}.{_ts}）:")
    print(f"  - USE CATALOG, USE SCHEMA, SELECT, MODIFY")
