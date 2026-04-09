# Databricks notebook source
# MAGIC %md
# MAGIC # フレッシュマート AI エージェント ワークショップ — セットアップノートブック
# MAGIC
# MAGIC このノートブックには、ローカル（`uv run quickstart`）では実行できない
# MAGIC Databricks 上専用のコマンドと、代表者がチームメンバーに権限を付与するセルが含まれています。
# MAGIC
# MAGIC **セル一覧：**
# MAGIC 1. **トレース送信先の設定** — Delta Table にトレースを送信する場合のみ（全員）
# MAGIC 2. **アプリの SP 権限付与** — Databricks Apps にデプロイする場合のみ（各自）
# MAGIC 3. **チームメンバーへの権限付与** — チーム利用時のみ（代表者）
# MAGIC
# MAGIC `uv run quickstart` を実行済みの場合、プレースホルダーは自動入力されています。
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
EVAL_EXPERIMENT_ID = "<EVAL-EXPERIMENT-ID>"              # 例: "2019445883421301"
GENIE_SPACE_ID = "<GENIE-SPACE-ID>"                      # 例: "01f132..."
LAKEBASE_PROJECT = "<LAKEBASE-PROJECT>"                  # 例: "my-fresh-mart"
LAKEBASE_BRANCH = "<LAKEBASE-BRANCH>"                    # 例: "my-fresh-mart-branch"
SP_CLIENT_ID = "<SP_CLIENT_ID>"            # 例: "9bf3f616-..." （Apps デプロイ後に取得）

# チームメンバーのメールアドレス（代表者のみ使用）
TEAM_MEMBERS = [
    # "member1@company.com",
    # "member2@company.com",
]

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
# MAGIC ## 3. チームメンバーへの権限付与（代表者のみ）
# MAGIC
# MAGIC 代表者がリソースを作成した後、他のメンバーがアクセスできるように権限を付与します。
# MAGIC 先頭の設定セルで `TEAM_MEMBERS` にメンバーのメールアドレスを追加してから実行してください。
# MAGIC
# MAGIC **前提：** クイックスタートが完了していること（カタログ・スキーマ・各リソースが作成済み）。
# MAGIC
# MAGIC **自動付与される権限：**
# MAGIC - Unity Catalog: USE CATALOG, USE SCHEMA, SELECT, MODIFY
# MAGIC - MLflow Experiment: CAN_MANAGE（モニタリング + 評価）
# MAGIC - Genie Space: CAN_RUN
# MAGIC - Lakebase: プロジェクト CAN_USE + DB スキーマ権限
# MAGIC - SQL Warehouse: CAN_USE
# MAGIC
# MAGIC **手動で共有が必要：**
# MAGIC - アプリの SP 権限: 各メンバーがデプロイ後にセル 2 を各自で実行

# COMMAND ----------

import requests

if not TEAM_MEMBERS:
    print("⚠ TEAM_MEMBERS が空です。先頭の設定セルにメンバーのメールアドレスを追加してください。")
else:
    # API 認証情報の取得
    _ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
    _host = _ctx.apiUrl().getOrElse(None)
    _token = _ctx.apiToken().getOrElse(None)
    _headers = {"Authorization": f"Bearer {_token}", "Content-Type": "application/json"}

    # ── 1. Unity Catalog 権限（SQL）──
    print("=== 1. Unity Catalog 権限 ===")
    for member in TEAM_MEMBERS:
        spark.sql(f"GRANT USE CATALOG ON CATALOG `{CATALOG}` TO `{member}`")
        spark.sql(f"GRANT USE SCHEMA ON SCHEMA `{CATALOG}`.`{SCHEMA}` TO `{member}`")
        spark.sql(f"GRANT SELECT ON SCHEMA `{CATALOG}`.`{SCHEMA}` TO `{member}`")
        spark.sql(f"GRANT MODIFY ON SCHEMA `{CATALOG}`.`{SCHEMA}` TO `{member}`")
        print(f"  ✓ {member}: USE CATALOG, USE SCHEMA, SELECT, MODIFY")

    # ── 2. MLflow Experiment 権限（REST API）──
    print("\n=== 2. MLflow Experiment 権限 ===")
    for exp_id, exp_label in [(MONITORING_EXPERIMENT_ID, "モニタリング"), (EVAL_EXPERIMENT_ID, "評価")]:
        if not exp_id or exp_id.startswith("<"):
            print(f"  → {exp_label}: ID 未設定（スキップ）")
            continue
        acl = [{"user_name": m, "permission_level": "CAN_MANAGE"} for m in TEAM_MEMBERS]
        resp = requests.patch(
            f"{_host}/api/2.0/permissions/experiments/{exp_id}",
            headers=_headers,
            json={"access_control_list": acl},
        )
        if resp.status_code == 200:
            print(f"  ✓ {exp_label} Experiment ({exp_id}): CAN_MANAGE 付与")
        else:
            print(f"  ✗ {exp_label} Experiment 権限付与失敗: {resp.text[:200]}")

    # ── 3. Genie Space 権限（REST API）──
    print("\n=== 3. Genie Space 権限 ===")
    if not GENIE_SPACE_ID or GENIE_SPACE_ID.startswith("<"):
        print("  → GENIE_SPACE_ID 未設定（スキップ）")
    else:
        acl = [{"user_name": m, "permission_level": "CAN_RUN"} for m in TEAM_MEMBERS]
        _genie_ok = False
        for api_path in [f"/api/2.0/permissions/dashboards/{GENIE_SPACE_ID}",
                         f"/api/2.0/permissions/genie-spaces/{GENIE_SPACE_ID}"]:
            resp = requests.patch(f"{_host}{api_path}", headers=_headers, json={"access_control_list": acl})
            if resp.status_code == 200:
                print(f"  ✓ Genie Space ({GENIE_SPACE_ID}): CAN_RUN 付与")
                _genie_ok = True
                break
        if not _genie_ok:
            print(f"  ✗ Genie Space の自動権限付与に失敗。UI から手動で共有してください。")
            print(f"    Genie > 対象のスペース > Share > メンバーを Can Run で追加")

    # ── 4. Lakebase 権限 ──
    print("\n=== 4. Lakebase 権限 ===")
    if not LAKEBASE_PROJECT or LAKEBASE_PROJECT.startswith("<"):
        print("  → LAKEBASE_PROJECT 未設定（スキップ）")
    else:
        # プロジェクト ACL（CAN_USE）
        acl = [{"user_name": m, "permission_level": "CAN_USE"} for m in TEAM_MEMBERS]
        resp = requests.patch(
            f"{_host}/api/2.0/permissions/postgres/projects/{LAKEBASE_PROJECT}",
            headers=_headers,
            json={"access_control_list": acl},
        )
        if resp.status_code == 200:
            print(f"  ✓ プロジェクト CAN_USE 付与")
        else:
            print(f"  ⚠ プロジェクト ACL 付与失敗: {resp.text[:200]}")

        # DB 権限（LakebaseClient）
        try:
            from databricks_ai_bridge.lakebase import LakebaseClient, SchemaPrivilege
            lakebase_client = LakebaseClient(project=LAKEBASE_PROJECT, branch=LAKEBASE_BRANCH)
            for member in TEAM_MEMBERS:
                try:
                    lakebase_client.create_role(member, "USER")
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        print(f"  ⚠ {member} のロール作成: {str(e)[:100]}")
                for schema_name in ["public", "ai_chatbot", "drizzle"]:
                    try:
                        lakebase_client.grant_schema(grantee=member, schemas=[schema_name],
                                                     privileges=[SchemaPrivilege.USAGE, SchemaPrivilege.CREATE])
                    except Exception:
                        pass
            print(f"  ✓ Lakebase DB 権限付与")
        except Exception as e:
            print(f"  ⚠ Lakebase DB 権限: {str(e)[:200]}")

    # ── 5. SQL Warehouse 権限 ──
    print("\n=== 5. SQL Warehouse 権限 ===")
    if not WAREHOUSE_ID or WAREHOUSE_ID.startswith("<"):
        print("  → WAREHOUSE_ID 未設定（スキップ）")
    else:
        acl = [{"user_name": m, "permission_level": "CAN_USE"} for m in TEAM_MEMBERS]
        resp = requests.patch(
            f"{_host}/api/2.0/permissions/sql/warehouses/{WAREHOUSE_ID}",
            headers=_headers,
            json={"access_control_list": acl},
        )
        if resp.status_code == 200:
            print(f"  ✓ SQL Warehouse CAN_USE 付与")
        else:
            print(f"  ⚠ SQL Warehouse 権限付与失敗（共有ウェアハウスなら既にアクセス可能な場合があります）")

    # ── サマリー ──
    print(f"\n{'='*50}")
    print(f"✓ {len(TEAM_MEMBERS)} 名のメンバーに権限を付与しました")
    print(f"{'='*50}")
    print("\n手動で共有が必要なもの：")
    print("  - アプリの SP 権限: 各メンバーがデプロイ後にセル 2 を各自で実行")
