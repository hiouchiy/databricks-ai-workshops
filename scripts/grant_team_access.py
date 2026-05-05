#!/usr/bin/env python3
"""チームメンバー（またはグループ）にワークショップリソースへのアクセス権限を一括付与する。

代表者がクイックスタート実行後にローカルから実行します。
.env からリソース情報を読み取り、指定されたメンバー/グループに権限を付与します。

Usage:
    # メンバーを個別に指定
    uv run grant-team-access alice@company.com bob@company.com

    # Databricks グループを指定（推奨: 新規メンバー追加時は再実行不要）
    uv run grant-team-access --group workshop-members

    # 初回実行後、アプリが一度起動しテーブルが作成された後に再実行
    # （Lakebase テーブル権限の完全付与のため）
    uv run grant-team-access --group workshop-members

付与される権限:
    - Unity Catalog: USE_CATALOG, USE_SCHEMA, SELECT, MODIFY（REST API、ウェアハウス不要）
    - MLflow Experiment: CAN_MANAGE（モニタリング + 評価）
    - Genie Space: CAN_RUN
    - Lakebase プロジェクト: CAN_USE（層1）
    - Lakebase PostgreSQL: ロール作成 + スキーマ/テーブル権限（層2）
    - SQL Warehouse: CAN_USE
"""

import argparse
import json
import os
import subprocess
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
        return {"error": f"HTTP {e.code}: {e.read().decode('utf-8')[:300]}"}
    except Exception as e:
        return {"error": str(e)}


def grant_uc_permissions(
    token: str, host: str, securable_type: str, full_name: str,
    principals: list[tuple[str, str]], privileges: list[str],
) -> bool:
    """Unity Catalog 権限を REST API で付与（ウェアハウス不要）。

    principals: [(identity, principal_type), ...]  principal_type = "user" | "group"
    """
    changes = []
    for identity, ptype in principals:
        changes.append({"principal": identity, "add": privileges})
    payload = json.dumps({"changes": changes}).encode("utf-8")
    req = urllib.request.Request(
        f"{host}/api/2.1/unity-catalog/permissions/{securable_type}/{full_name}",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")[:200]
        print_error(f"UC 権限付与失敗 ({securable_type}/{full_name}): HTTP {e.code}: {body}")
        return False
    except Exception as e:
        print_error(f"UC 権限付与失敗: {str(e)[:200]}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="チームメンバー（またはグループ）にワークショップリソースへのアクセス権限を一括付与",
    )
    parser.add_argument(
        "members",
        nargs="*",
        help="メンバーのメールアドレス（複数指定可、--group と排他）",
    )
    parser.add_argument(
        "--group",
        help="Databricks グループ名（メンバー個別指定の代わりに使用。新規メンバー追加時は再実行不要）",
    )
    parser.add_argument(
        "--profile",
        default=os.getenv("DATABRICKS_CONFIG_PROFILE", "DEFAULT"),
        help="Databricks CLI プロファイル",
    )
    args = parser.parse_args()

    if args.group and args.members:
        print_error("--group とメンバー個別指定は排他です。どちらか一方のみ指定してください。")
        sys.exit(1)
    if not args.group and not args.members:
        print_error("メンバー名または --group を指定してください。")
        sys.exit(1)

    # プリンシパル情報
    if args.group:
        principals = [(args.group, "group")]
        principals_label = f"グループ: {args.group}"
    else:
        principals = [(m, "user") for m in args.members]
        principals_label = f"メンバー: {', '.join(args.members)}"

    # 環境変数の読み込み
    vs_index = os.getenv("VECTOR_SEARCH_INDEX", "")
    parts = vs_index.split(".")
    catalog = parts[0] if len(parts) >= 2 else ""
    schema = parts[1] if len(parts) >= 2 else ""
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
    print(f"  {principals_label}")
    print(f"  カタログ/スキーマ: {catalog}.{schema}")
    print()

    # ── 1. Unity Catalog 権限（REST API、ウェアハウス不要）──
    print("=== 1. Unity Catalog 権限 ===")
    grant_uc_permissions(token, host, "catalog", catalog, principals, ["USE_CATALOG"])
    grant_uc_permissions(token, host, "schema", f"{catalog}.{schema}",
                         principals, ["USE_SCHEMA", "SELECT", "MODIFY"])
    print_success(f"データスキーマ: USE_CATALOG, USE_SCHEMA, SELECT, MODIFY on {catalog}.{schema}")

    # ── 2. MLflow Experiment 権限 ──
    print("\n=== 2. MLflow Experiment 権限 ===")
    for exp_id, label in [(monitoring_id, "モニタリング"), (eval_id, "評価")]:
        if not exp_id:
            print_warn(f"{label}: ID 未設定（スキップ）")
            continue
        acl = []
        for identity, ptype in principals:
            if ptype == "group":
                acl.append({"group_name": identity, "permission_level": "CAN_MANAGE"})
            else:
                acl.append({"user_name": identity, "permission_level": "CAN_MANAGE"})
        result = api_patch(f"/api/2.0/permissions/experiments/{exp_id}", token, host,
                           {"access_control_list": acl})
        if "error" not in result:
            print_success(f"{label} Experiment ({exp_id}): CAN_MANAGE 付与")
        else:
            print_error(f"{label} Experiment: {result['error'][:200]}")

    # ── 3. Genie Space 権限 ──
    print("\n=== 3. Genie Space 権限 ===")
    if not genie_space_id:
        print_warn("GENIE_SPACE_ID 未設定（スキップ）")
    else:
        acl = []
        for identity, ptype in principals:
            if ptype == "group":
                acl.append({"group_name": identity, "permission_level": "CAN_RUN"})
            else:
                acl.append({"user_name": identity, "permission_level": "CAN_RUN"})
        result = api_patch(f"/api/2.0/permissions/sql/genie/{genie_space_id}", token, host,
                           {"access_control_list": acl})
        if "error" not in result:
            print_success(f"Genie Space ({genie_space_id}): CAN_RUN 付与")
        else:
            print_error(f"Genie Space 権限付与失敗: {result['error'][:200]}")

    # ── 4. Lakebase プロジェクト権限（層1: CAN_USE）──
    print("\n=== 4. Lakebase プロジェクト権限（層1）===")
    if not lakebase_project:
        print_warn("LAKEBASE_AUTOSCALING_PROJECT 未設定（スキップ）")
    else:
        acl = []
        for identity, ptype in principals:
            if ptype == "group":
                acl.append({"group_name": identity, "permission_level": "CAN_USE"})
            else:
                acl.append({"user_name": identity, "permission_level": "CAN_USE"})
        result = api_patch(f"/api/2.0/permissions/database-projects/{lakebase_project}",
                           token, host, {"access_control_list": acl})
        if "error" not in result:
            print_success(f"Lakebase プロジェクト ({lakebase_project}): CAN_USE 付与")
        else:
            print_error(f"Lakebase プロジェクト権限付与失敗: {result['error'][:200]}")

    # ── 5. Lakebase PostgreSQL 権限（層2: ロール + スキーマ/テーブル）──
    print("\n=== 5. Lakebase PostgreSQL 権限（層2）===")
    if not lakebase_project or not lakebase_branch:
        print_warn("Lakebase プロジェクト/ブランチ未設定（スキップ）")
    else:
        try:
            from databricks_ai_bridge.lakebase import (
                LakebaseClient, SchemaPrivilege, TablePrivilege,
            )
            client = LakebaseClient(project=lakebase_project, branch=lakebase_branch)
            schema_privs = [SchemaPrivilege.USAGE, SchemaPrivilege.CREATE]
            table_privs = [TablePrivilege.SELECT, TablePrivilege.INSERT,
                           TablePrivilege.UPDATE, TablePrivilege.DELETE]

            schema_tables = {
                "public": [
                    "checkpoint_migrations", "checkpoint_writes", "checkpoints", "checkpoint_blobs",
                    "store_migrations", "store", "store_vectors", "vector_migrations",
                ],
                "ai_chatbot": ["Chat", "Message", "User", "Vote"],
                "drizzle": ["__drizzle_migrations"],
            }

            for identity, ptype in principals:
                # ロール作成（name をそのまま使用: Lakebase は name ベース）
                identity_for_role = identity
                role_type = "GROUP" if ptype == "group" else "USER"

                try:
                    client.create_role(identity_for_role, role_type)
                    print_success(f"PG ロール作成: {identity} ({role_type})")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        print_success(f"PG ロール既存: {identity}（スキップ）")
                    else:
                        print_warn(f"PG ロール作成失敗: {str(e)[:150]}")

                # スキーマ + テーブル権限
                # grantee は PG ロール名（= identity_for_role）
                granted_schemas = 0
                granted_tables = 0
                skipped_tables = 0
                for schema_name, tables in schema_tables.items():
                    try:
                        client.grant_schema(grantee=identity_for_role,
                                            schemas=[schema_name], privileges=schema_privs)
                        granted_schemas += 1
                    except Exception as e:
                        if "does not exist" not in str(e).lower():
                            print_warn(f"  スキーマ {schema_name}: {str(e)[:100]}")
                        continue
                    for table in tables:
                        try:
                            client.grant_table(grantee=identity_for_role,
                                               tables=[f"{schema_name}.{table}"],
                                               privileges=table_privs)
                            granted_tables += 1
                        except Exception as e:
                            if "does not exist" in str(e).lower():
                                skipped_tables += 1
                            else:
                                print_warn(f"  {schema_name}.{table}: {str(e)[:100]}")

                msg = f"{identity}: {granted_schemas} スキーマ, {granted_tables} テーブル"
                if skipped_tables > 0:
                    msg += f"（{skipped_tables} テーブル未作成 — アプリ初回起動後に再実行）"
                print_success(msg)

        except ImportError:
            print_warn("databricks_ai_bridge 未インストール。uv sync を実行してください。")
        except Exception as e:
            print_warn(f"Lakebase PG: {str(e)[:200]}")

    # ── 6. SQL Warehouse 権限 ──
    print("\n=== 6. SQL Warehouse 権限 ===")
    if not warehouse_id:
        print_warn("MLFLOW_TRACING_SQL_WAREHOUSE_ID 未設定（スキップ）")
    else:
        acl = []
        for identity, ptype in principals:
            if ptype == "group":
                acl.append({"group_name": identity, "permission_level": "CAN_USE"})
            else:
                acl.append({"user_name": identity, "permission_level": "CAN_USE"})
        result = api_patch(f"/api/2.0/permissions/warehouses/{warehouse_id}", token, host,
                           {"access_control_list": acl})
        if "error" not in result:
            print_success(f"SQL Warehouse ({warehouse_id}): CAN_USE 付与")
        else:
            print_error(f"SQL Warehouse 権限付与失敗: {result['error'][:200]}")

    # ── 共有情報の表示 ──
    print(f"\n{'='*60}")
    print("メンバーに共有する情報")
    print(f"{'='*60}")
    print(f"  カタログ名:            {catalog}")
    print(f"  スキーマ名:            {schema}")
    print(f"  VS エンドポイント名:   {os.getenv('VS_ENDPOINT_NAME', '（共有先で確認）')}")
    print(f"  Genie Space ID:        {genie_space_id}")
    if lakebase_project:
        print(f"  Lakebase プロジェクト:  {lakebase_project}")
        print(f"  （メンバー個人ブランチがクイックスタート実行時に自動作成されます）")
    print(f"  モニタリング Exp ID:   {monitoring_id}")
    print(f"  評価 Exp ID:           {eval_id}")
    print()
    if args.group:
        print(f"  💡 グループ '{args.group}' に新規メンバーを追加するだけで")
        print(f"     権限が自動継承されます（本スクリプトの再実行は不要）。")
    print()
