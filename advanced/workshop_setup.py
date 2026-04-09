# Databricks notebook source
# MAGIC %md
# MAGIC # フレッシュマート AI エージェント ワークショップ — セットアップノートブック
# MAGIC
# MAGIC このノートブックには、ワークショップのインストラクション（WORKSHOP_INSTRUCTIONS.md）で
# MAGIC Databricks 上での実行が必要なコマンドが集約されています。
# MAGIC
# MAGIC **使い方：** 各セルの `<CATALOG>` 等のプレースホルダーを自分の値に置き換えてから、
# MAGIC 該当するステップのセルを実行してください。すべてのセルを順番に実行する必要はありません。
# MAGIC
# MAGIC ---

# COMMAND ----------

# MAGIC %md
# MAGIC ## 設定（最初に実行）
# MAGIC
# MAGIC 以下のプレースホルダーを自分の環境に合わせて設定してください。
# MAGIC `uv run quickstart` を実行済みの場合は自動的に値が入っています。

# COMMAND ----------

# ── プレースホルダー（ここを自分の値に書き換えてください）──
CATALOG = "<CATALOG>"                      # 例: "hiroshi"
SCHEMA = "<SCHEMA>"                        # 例: "retail_agent"
WAREHOUSE_ID = "<WAREHOUSE-ID>"            # 例: "4b9b953939869799"
MONITORING_EXPERIMENT_ID = "<MONITORING-EXPERIMENT-ID>"  # 例: "2019445883421300"
SP_CLIENT_ID = "<SP_CLIENT_ID>"            # 例: "9bf3f616-..." （ステップ 11 で使用）

# チームメンバーのメールアドレス（チーム利用時のみ。末尾の「チームメンバーへの権限付与」で使用）
TEAM_MEMBERS = [
    # "member1@company.com",
    # "member2@company.com",
]

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## ステップ 1：カタログとスキーマの作成
# MAGIC
# MAGIC > 管理者が事前に作成済みの場合はスキップしてください。

# COMMAND ----------

spark.sql(f"CREATE CATALOG IF NOT EXISTS `{CATALOG}`")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{CATALOG}`.`{SCHEMA}`")
print(f"✓ カタログ: {CATALOG}")
print(f"✓ スキーマ: {CATALOG}.{SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## ステップ 3：Change Data Feed の有効化
# MAGIC
# MAGIC ポリシー文書チャンクテーブルに CDF を有効化します（Vector Search インデックス作成に必要）。

# COMMAND ----------

spark.sql(f"""
    ALTER TABLE `{CATALOG}`.`{SCHEMA}`.policy_docs_chunked
    SET TBLPROPERTIES (delta.enableChangeDataFeed = true)
""")
print(f"✓ CDF 有効化完了: {CATALOG}.{SCHEMA}.policy_docs_chunked")

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## トレース送信先の設定（オプション）
# MAGIC
# MAGIC Unity Catalog の Delta Table にトレースを送信する場合のみ実行してください。
# MAGIC
# MAGIC **注意：**
# MAGIC - 紐付ける Experiment にはトレースが1件も入っていない必要があります
# MAGIC - `set_experiment_trace_location` はこのノートブック上でのみ実行可能です（ローカル不可）

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
# MAGIC ## ステップ 11-6：サービスプリンシパルへの Unity Catalog パーミッション付与
# MAGIC
# MAGIC Databricks Apps にデプロイする場合のみ実行してください。
# MAGIC `SP_CLIENT_ID` は以下のコマンドで取得できます：
# MAGIC ```
# MAGIC databricks apps get <アプリ名> --output json --profile DEFAULT | jq -r '.service_principal_client_id'
# MAGIC ```

# COMMAND ----------

spark.sql(f"GRANT USE CATALOG ON CATALOG `{CATALOG}` TO `{SP_CLIENT_ID}`")
spark.sql(f"GRANT USE SCHEMA ON SCHEMA `{CATALOG}`.`{SCHEMA}` TO `{SP_CLIENT_ID}`")
spark.sql(f"GRANT SELECT ON SCHEMA `{CATALOG}`.`{SCHEMA}` TO `{SP_CLIENT_ID}`")
spark.sql(f"GRANT MODIFY ON SCHEMA `{CATALOG}`.`{SCHEMA}` TO `{SP_CLIENT_ID}`")
print(f"✓ SP {SP_CLIENT_ID} に以下の権限を付与:")
print(f"  - USE CATALOG on {CATALOG}")
print(f"  - USE SCHEMA on {CATALOG}.{SCHEMA}")
print(f"  - SELECT on {CATALOG}.{SCHEMA}")
print(f"  - MODIFY on {CATALOG}.{SCHEMA}（Delta Table トレース用）")

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## チームメンバーへの権限付与（チーム利用時のみ）
# MAGIC
# MAGIC 代表者がリソースを作成した後、他のメンバーがアクセスできるように権限を付与します。
# MAGIC 先頭の設定セルで `TEAM_MEMBERS` にメンバーのメールアドレスを追加してから実行してください。
# MAGIC
# MAGIC **前提：** ステップ 1（カタログ・スキーマ作成）が完了していること。
# MAGIC
# MAGIC **注意：** Genie Space と MLflow Experiment の共有は UI から手動で行ってください。

# COMMAND ----------

if not TEAM_MEMBERS:
    print("⚠ TEAM_MEMBERS が空です。先頭の設定セルにメンバーのメールアドレスを追加してください。")
else:
    for member in TEAM_MEMBERS:
        spark.sql(f"GRANT USE CATALOG ON CATALOG `{CATALOG}` TO `{member}`")
        spark.sql(f"GRANT USE SCHEMA ON SCHEMA `{CATALOG}`.`{SCHEMA}` TO `{member}`")
        spark.sql(f"GRANT SELECT ON SCHEMA `{CATALOG}`.`{SCHEMA}` TO `{member}`")
        print(f"✓ {member} に USE CATALOG, USE SCHEMA, SELECT を付与")
    print(f"\n✓ {len(TEAM_MEMBERS)} 名のメンバーに権限を付与しました")
    print("\n以下は UI から手動で共有してください：")
    print("  - Genie Space: Genie > 対象のスペース > Share > Can Run で追加")
    print("  - MLflow Experiment: Experiments > Permissions > Can Manage で追加")
