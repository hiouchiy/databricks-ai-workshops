#!/usr/bin/env python3
"""デプロイ後のアプリ SP に必要な権限を一括付与する。

ノートブック（workshop_setup.py）を開かずに、ローカルから全権限を付与できます。

Usage:
    uv run grant-sp-permissions                          # アプリ名は databricks.yml から自動取得
    uv run grant-sp-permissions --app-name my-agent      # アプリ名を指定
    uv run grant-sp-permissions --sp-client-id <UUID>    # SP Client ID を直接指定

付与される権限:
    1. Unity Catalog: USE CATALOG, USE SCHEMA, SELECT, MODIFY
    2. Lakebase PostgreSQL: ロール作成 + スキーマ/テーブル権限
"""

import argparse
import json
import os
import re
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


def grant_uc_permissions(
    token: str, host: str, securable_type: str, full_name: str,
    principal: str, privileges: list[str],
) -> bool:
    """Grant Unity Catalog permissions via REST API (no warehouse needed).

    securable_type: "catalog", "schema"
    """
    payload = json.dumps({
        "changes": [{
            "principal": principal,
            "add": privileges,
        }],
    }).encode("utf-8")
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


def get_sp_client_id(app_name: str, profile: str) -> str:
    """アプリ名から SP Client ID を取得する。"""
    result = subprocess.run(
        ["databricks", "apps", "get", app_name, "--output", "json", "-p", profile],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print_error(f"アプリ '{app_name}' の情報を取得できません: {result.stderr.strip()[:200]}")
        sys.exit(1)
    data = json.loads(result.stdout)
    sp_id = data.get("service_principal_client_id", "")
    if not sp_id:
        print_error(f"アプリ '{app_name}' に SP が割り当てられていません。デプロイ済みか確認してください。")
        sys.exit(1)
    return sp_id


def get_app_name_from_yml() -> str | None:
    """databricks.yml からアプリ名を取得する。"""
    from pathlib import Path
    yml = Path("databricks.yml")
    if not yml.exists():
        return None
    content = yml.read_text()
    # dev target の name: を探す（最初の name: がアプリ名）
    m = re.search(r'^\s+name:\s*["\']?([^"\'#\n]+)', content, re.MULTILINE)
    return m.group(1).strip() if m else None


def grant_lakebase_permissions(sp_id: str):
    """Lakebase PostgreSQL 内部権限を付与する。"""
    project = os.getenv("LAKEBASE_AUTOSCALING_PROJECT", "")
    branch = os.getenv("LAKEBASE_AUTOSCALING_BRANCH", "")
    instance_name = os.getenv("LAKEBASE_INSTANCE_NAME", "")

    if not project and not instance_name:
        print_warn("Lakebase 未設定（スキップ）")
        return

    try:
        from databricks_ai_bridge.lakebase import (
            LakebaseClient,
            SchemaPrivilege,
            TablePrivilege,
        )
    except ImportError:
        print_warn("databricks-ai-bridge がインストールされていません。Lakebase 権限はスキップします。")
        return

    client = LakebaseClient(
        instance_name=instance_name or None,
        project=project or None,
        branch=branch or None,
    )

    # ロール作成
    try:
        client.create_role(sp_id, "SERVICE_PRINCIPAL")
        print_success("Lakebase ロール作成")
    except Exception as e:
        if "already exists" in str(e).lower():
            print_success("Lakebase ロール既存（スキップ）")
        else:
            print_error(f"Lakebase ロール作成失敗: {str(e)[:200]}")
            return

    schema_privs = [SchemaPrivilege.USAGE, SchemaPrivilege.CREATE]
    table_privs = [TablePrivilege.SELECT, TablePrivilege.INSERT, TablePrivilege.UPDATE, TablePrivilege.DELETE]

    # Short-term memory (LangGraph checkpointer)
    short_term_tables = [
        "checkpoint_migrations", "checkpoint_writes", "checkpoints", "checkpoint_blobs",
    ]
    # Long-term memory (DatabricksStore)
    long_term_tables = [
        "store_migrations", "store", "store_vectors", "vector_migrations",
    ]
    # Frontend (Express chat history)
    frontend_schemas = {
        "ai_chatbot": ["Chat", "Message", "User", "Vote"],
        "drizzle": ["__drizzle_migrations"],
    }

    # 全スキーマをまとめて処理
    all_schemas = {
        "public": short_term_tables + long_term_tables,
        **frontend_schemas,
    }

    for schema_name, tables in all_schemas.items():
        # スキーマ権限
        try:
            client.grant_schema(grantee=sp_id, schemas=[schema_name], privileges=schema_privs)
        except Exception as e:
            if "does not exist" in str(e).lower():
                print_warn(f"Lakebase {schema_name} スキーマ未作成（初回起動後に再実行してください）")
                continue
            else:
                print_error(f"Lakebase {schema_name} スキーマ権限付与失敗: {str(e)[:200]}")
                continue

        # テーブル権限（1テーブルずつ、存在しないテーブルはスキップ）
        granted = 0
        skipped = 0
        for table in tables:
            try:
                client.grant_table(grantee=sp_id, tables=[f"{schema_name}.{table}"], privileges=table_privs)
                granted += 1
            except Exception as e:
                if "does not exist" in str(e).lower():
                    skipped += 1
                else:
                    print_error(f"  {schema_name}.{table}: {str(e)[:150]}")

        if granted > 0:
            msg = f"Lakebase {schema_name}: {granted} テーブル権限付与"
            if skipped > 0:
                msg += f"（{skipped} テーブル未作成 — 初回起動後に再実行）"
            print_success(msg)
        elif skipped > 0:
            print_warn(f"Lakebase {schema_name}: 全 {skipped} テーブル未作成（初回起動後に再実行してください）")


def main():
    parser = argparse.ArgumentParser(
        description="デプロイ後のアプリ SP に必要な権限を一括付与",
    )
    parser.add_argument(
        "--app-name",
        help="Databricks Apps のアプリ名（省略時は databricks.yml から自動取得）",
    )
    parser.add_argument(
        "--sp-client-id",
        help="SP Client ID を直接指定（アプリ名からの自動取得をスキップ）",
    )
    parser.add_argument(
        "--profile",
        default=os.getenv("DATABRICKS_CONFIG_PROFILE", "DEFAULT"),
        help="Databricks CLI プロファイル",
    )
    args = parser.parse_args()

    # SP Client ID の取得
    if args.sp_client_id:
        sp_id = args.sp_client_id
        app_name = args.app_name or "(direct)"
    else:
        app_name = args.app_name or get_app_name_from_yml()
        if not app_name:
            print_error("アプリ名を --app-name で指定するか、databricks.yml を配置してください。")
            sys.exit(1)
        print(f"アプリ '{app_name}' の SP Client ID を取得中...")
        sp_id = get_sp_client_id(app_name, args.profile)

    # 環境変数の読み込み
    vs_index = os.getenv("VECTOR_SEARCH_INDEX", "")
    parts = vs_index.split(".")
    catalog = parts[0] if len(parts) >= 2 else ""
    schema = parts[1] if len(parts) >= 2 else ""
    trace_dest = os.getenv("MLFLOW_TRACING_DESTINATION", "")

    if not catalog or not schema:
        print_error("VECTOR_SEARCH_INDEX から CATALOG.SCHEMA を特定できません。.env を確認してください。")
        sys.exit(1)

    host = get_host()
    token = get_token(args.profile)

    print(f"\n{'='*60}")
    print(f"アプリ SP 権限一括付与")
    print(f"{'='*60}")
    print(f"  アプリ名:        {app_name}")
    print(f"  SP Client ID:    {sp_id}")
    print(f"  カタログ/スキーマ: {catalog}.{schema}")
    print()

    # ── 1. Unity Catalog データスキーマ権限（UC Permissions API、ウェアハウス不要）──
    print("=== 1. Unity Catalog データスキーマ権限 ===")
    grant_uc_permissions(token, host, "catalog", catalog, sp_id, ["USE_CATALOG"])
    grant_uc_permissions(token, host, "schema", f"{catalog}.{schema}", sp_id,
                         ["USE_SCHEMA", "SELECT"])
    print_success(f"データスキーマ: USE_CATALOG, USE_SCHEMA, SELECT on {catalog}.{schema}")

    # トレーススキーマ権限
    print("\n=== 2. Unity Catalog トレーススキーマ権限 ===")
    if trace_dest:
        trace_parts = trace_dest.split(".")
        tc = trace_parts[0] if len(trace_parts) >= 2 else catalog
        ts = trace_parts[1] if len(trace_parts) >= 2 else schema
    else:
        tc, ts = catalog, schema

    if tc != catalog:
        grant_uc_permissions(token, host, "catalog", tc, sp_id, ["USE_CATALOG"])
    if tc != catalog or ts != schema:
        grant_uc_permissions(token, host, "schema", f"{tc}.{ts}", sp_id,
                             ["USE_SCHEMA", "SELECT", "MODIFY"])
    else:
        grant_uc_permissions(token, host, "schema", f"{tc}.{ts}", sp_id, ["MODIFY"])

    if tc == catalog and ts == schema:
        print_success(f"トレーススキーマ（同一）: MODIFY on {tc}.{ts}")
    else:
        print_success(f"トレーススキーマ: USE_CATALOG, USE_SCHEMA, SELECT, MODIFY on {tc}.{ts}")

    # ── 3. Lakebase PostgreSQL 権限 ──
    print("\n=== 3. Lakebase PostgreSQL 権限 ===")
    grant_lakebase_permissions(sp_id)

    print(f"\n{'='*60}")
    print("完了! アプリを再起動してください:")
    print(f"  databricks apps stop {app_name} --profile {args.profile}")
    print(f"  databricks apps start {app_name} --profile {args.profile}")
    print(f"{'='*60}")
