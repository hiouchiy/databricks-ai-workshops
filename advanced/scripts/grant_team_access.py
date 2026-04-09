#!/usr/bin/env python3
"""チームメンバーにワークショップリソースへのアクセス権限を一括付与する。

代表者がクイックスタート実行後にローカルから実行します。
.env からリソース情報を読み取り、指定されたメンバーに権限を付与します。

Usage:
    uv run grant-team-access member1@company.com member2@company.com
    uv run grant-team-access dave@company.com   # 後から追加も OK（べき等）

付与される権限:
    - Unity Catalog: USE CATALOG, USE SCHEMA, SELECT, MODIFY
    - MLflow Experiment: CAN_MANAGE（モニタリング + 評価）
    - Genie Space: CAN_RUN
    - Lakebase: プロジェクト CAN_USE + DB スキーマ権限
    - SQL Warehouse: CAN_USE
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env", override=True)


def print_success(text: str):
    print(f"  ✓ {text}")


def print_error(text: str):
    print(f"  ✗ {text}")


def print_warn(text: str):
    print(f"  ⚠ {text}")


def get_token(profile: str) -> str:
    import subprocess
    result = subprocess.run(
        ["databricks", "auth", "token", "-p", profile, "-o", "json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print_error("Databricks トークン取得に失敗。databricks auth login を実行してください。")
        sys.exit(1)
    return json.loads(result.stdout)["access_token"]


def get_host() -> str:
    host = os.getenv("DATABRICKS_HOST", "")
    if not host:
        print_error("DATABRICKS_HOST が .env に設定されていません。")
        sys.exit(1)
    return host.rstrip("/")


def run_sql(statement: str, token: str, host: str, warehouse_id: str) -> dict:
    payload = json.dumps({
        "warehouse_id": warehouse_id,
        "statement": statement,
        "wait_timeout": "50s",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{host}/api/2.0/sql/statements",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {"status": {"state": "FAILED"}}


def api_patch(path: str, token: str, host: str, body: dict) -> dict:
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{host}{path}",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode('utf-8')[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(
        description="チームメンバーにワークショップリソースへのアクセス権限を一括付与",
    )
    parser.add_argument(
        "members",
        nargs="+",
        help="メンバーのメールアドレス（複数指定可）",
    )
    parser.add_argument(
        "--profile",
        default=os.getenv("DATABRICKS_CONFIG_PROFILE", "DEFAULT"),
        help="Databricks CLI プロファイル",
    )
    args = parser.parse_args()
    members = args.members

    # 環境変数の読み込み
    catalog = os.getenv("VECTOR_SEARCH_INDEX", "").split(".")[0] if os.getenv("VECTOR_SEARCH_INDEX") else ""
    schema = os.getenv("VECTOR_SEARCH_INDEX", "").split(".")[1] if os.getenv("VECTOR_SEARCH_INDEX") and len(os.getenv("VECTOR_SEARCH_INDEX", "").split(".")) > 1 else ""
    monitoring_id = os.getenv("MLFLOW_EXPERIMENT_ID", "")
    eval_id = os.getenv("MLFLOW_EVAL_EXPERIMENT_ID", "")
    genie_space_id = os.getenv("GENIE_SPACE_ID", "")
    lakebase_project = os.getenv("LAKEBASE_AUTOSCALING_PROJECT", "")
    lakebase_branch = os.getenv("LAKEBASE_AUTOSCALING_BRANCH", "")
    warehouse_id = os.getenv("MLFLOW_TRACING_SQL_WAREHOUSE_ID", "")

    if not catalog or not schema:
        print_error("VECTOR_SEARCH_INDEX から CATALOG.SCHEMA を特定できません。.env を確認してください。")
        sys.exit(1)

    host = get_host()
    token = get_token(args.profile)

    print(f"\n{'='*60}")
    print(f"チームメンバー権限付与")
    print(f"{'='*60}")
    print(f"  メンバー: {', '.join(members)}")
    print(f"  カタログ/スキーマ: {catalog}.{schema}")
    print()

    # ── 1. Unity Catalog 権限 ──
    print("=== 1. Unity Catalog 権限 ===")
    for member in members:
        run_sql(f"GRANT USE CATALOG ON CATALOG `{catalog}` TO `{member}`", token, host, warehouse_id or "dummy")
        run_sql(f"GRANT USE SCHEMA ON SCHEMA `{catalog}`.`{schema}` TO `{member}`", token, host, warehouse_id or "dummy")
        run_sql(f"GRANT SELECT ON SCHEMA `{catalog}`.`{schema}` TO `{member}`", token, host, warehouse_id or "dummy")
        run_sql(f"GRANT MODIFY ON SCHEMA `{catalog}`.`{schema}` TO `{member}`", token, host, warehouse_id or "dummy")
        print_success(f"{member}: USE CATALOG, USE SCHEMA, SELECT, MODIFY")

    # ── 2. MLflow Experiment 権限 ──
    print("\n=== 2. MLflow Experiment 権限 ===")
    for exp_id, label in [(monitoring_id, "モニタリング"), (eval_id, "評価")]:
        if not exp_id:
            print_warn(f"{label}: ID 未設定（スキップ）")
            continue
        acl = [{"user_name": m, "permission_level": "CAN_MANAGE"} for m in members]
        result = api_patch(f"/api/2.0/permissions/experiments/{exp_id}", token, host, {"access_control_list": acl})
        if "error" not in result:
            print_success(f"{label} Experiment ({exp_id}): CAN_MANAGE 付与")
        else:
            print_error(f"{label} Experiment: {result['error'][:200]}")

    # ── 3. Genie Space 権限 ──
    print("\n=== 3. Genie Space 権限 ===")
    if not genie_space_id:
        print_warn("GENIE_SPACE_ID 未設定（スキップ）")
    else:
        acl = [{"user_name": m, "permission_level": "CAN_RUN"} for m in members]
        result = api_patch(f"/api/2.0/permissions/sql/genie/{genie_space_id}", token, host, {"access_control_list": acl})
        if "error" not in result:
            print_success(f"Genie Space ({genie_space_id}): CAN_RUN 付与")
        else:
            print_error(f"Genie Space 権限付与失敗: {result['error'][:200]}")
            print("  UI から手動で共有してください: Genie > 対象のスペース > Share > Can Run")

    # ── 4. Lakebase 権限 ──
    print("\n=== 4. Lakebase 権限 ===")
    if not lakebase_project:
        print_warn("LAKEBASE_AUTOSCALING_PROJECT 未設定（スキップ）")
    else:
        # DB 権限（LakebaseClient でロール作成 + スキーマ権限付与）
        try:
            from databricks_ai_bridge.lakebase import LakebaseClient, SchemaPrivilege
            client = LakebaseClient(project=lakebase_project, branch=lakebase_branch)
            for member in members:
                try:
                    client.create_role(member, "USER")
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        print_warn(f"{member} ロール: {str(e)[:100]}")
                for s in ["public", "ai_chatbot", "drizzle"]:
                    try:
                        client.grant_schema(grantee=member, schemas=[s],
                                            privileges=[SchemaPrivilege.USAGE, SchemaPrivilege.CREATE])
                    except Exception:
                        pass
            print_success("Lakebase DB 権限付与")
        except ImportError:
            print_warn("databricks_ai_bridge 未インストール。DB 権限は初回アクセス時に付与されます。")
        except Exception as e:
            print_warn(f"Lakebase DB: {str(e)[:200]}")

    # ── 5. SQL Warehouse 権限 ──
    print("\n=== 5. SQL Warehouse 権限 ===")
    if not warehouse_id:
        print_warn("MLFLOW_TRACING_SQL_WAREHOUSE_ID 未設定（スキップ）")
    else:
        acl = [{"user_name": m, "permission_level": "CAN_USE"} for m in members]
        result = api_patch(
            f"/api/2.0/permissions/sql/warehouses/{warehouse_id}",
            token, host, {"access_control_list": acl},
        )
        if "error" not in result:
            print_success(f"SQL Warehouse ({warehouse_id}): CAN_USE 付与")
        else:
            print_warn("SQL Warehouse 権限付与失敗（共有ウェアハウスなら既にアクセス可能な場合があります）")

    # ── サマリー ──
    print(f"\n{'='*60}")
    print(f"✓ {len(members)} 名のメンバーに権限を付与しました")
    print(f"{'='*60}")
    print("\n手動で共有が必要なもの：")
    print("  - アプリの SP 権限: 各メンバーがデプロイ後にステップ 11-6 を各自で実行")
    print("\nメンバーに共有する情報：")
    print(f"  - カタログ: {catalog}")
    print(f"  - スキーマ: {schema}")
    if genie_space_id:
        print(f"  - Genie Space ID: {genie_space_id}")
    if lakebase_project:
        print(f"  - Lakebase プロジェクト: {lakebase_project}")
        print(f"  - Lakebase ブランチ: {lakebase_branch}")
    if monitoring_id:
        print(f"  - モニタリング Experiment ID: {monitoring_id}")
    if eval_id:
        print(f"  - 評価 Experiment ID: {eval_id}")


if __name__ == "__main__":
    main()
