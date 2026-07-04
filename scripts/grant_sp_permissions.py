#!/usr/bin/env python3
"""デプロイ後のアプリ SP に必要な権限を一括付与する。

ノートブック（workshop_setup.py）を開かずに、ローカルから全権限を付与できます。

Usage:
    uv run grant-sp-permissions --app-name <名前>        # アプリ名を明示指定（推奨）
    uv run grant-sp-permissions --sp-client-id <UUID>    # SP Client ID を直接指定

付与される権限:
    1. Unity Catalog: USE CATALOG, USE SCHEMA, SELECT, MODIFY
    2. Lakebase PostgreSQL: ロール作成 + スキーマ/テーブル権限
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


def grant_vs_endpoint_permission(
    token: str, host: str, vs_index: str, sp_id: str,
) -> bool:
    """Grant the App SP CAN_USE on the Vector Search endpoint that hosts vs_index.

    新規エンドポイントの ACL は creator + admins のみで、App SP は持たない。
    SP に CAN_USE を付けないと VS API が "Invalid Token" として弾く。
    既存共有エンドポイントの場合は既に他の経路で権限が付いていることが
    多いので冪等に動作する（PATCH なので重複許容）。
    """
    # 1. インデックスから endpoint 名と ID を取得
    idx_req = urllib.request.Request(
        f"{host}/api/2.0/vector-search/indexes/{vs_index}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(idx_req, timeout=30) as resp:
            idx_info = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print_warn(f"VS インデックス情報取得失敗: {str(e)[:200]} → 権限付与スキップ")
        return False
    endpoint_name = idx_info.get("endpoint_name", "")
    if not endpoint_name:
        print_warn("VS インデックスから endpoint 名を解決できず → 権限付与スキップ")
        return False

    ep_req = urllib.request.Request(
        f"{host}/api/2.0/vector-search/endpoints/{endpoint_name}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(ep_req, timeout=30) as resp:
            ep_info = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print_warn(f"VS エンドポイント情報取得失敗: {str(e)[:200]} → 権限付与スキップ")
        return False
    endpoint_id = ep_info.get("id", "")
    if not endpoint_id:
        print_warn(f"VS エンドポイント '{endpoint_name}' の ID を取得できず → 権限付与スキップ")
        return False

    # 2. PATCH で CAN_USE を付与
    payload = json.dumps({
        "access_control_list": [{
            "service_principal_name": sp_id,
            "permission_level": "CAN_USE",
        }],
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{host}/api/2.0/permissions/vector-search-endpoints/{endpoint_id}",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")[:200]
        print_error(f"VS エンドポイント権限付与失敗 ({endpoint_name}): HTTP {e.code}: {body}")
        return False
    except Exception as e:
        print_error(f"VS エンドポイント権限付与失敗: {str(e)[:200]}")
        return False


def grant_memory_store_permission(
    token: str, host: str, memory_store: str, sp_id: str,
) -> bool:
    """Grant the App SP READ_MEMORY_STORE + WRITE_MEMORY_STORE on the UC memory-store.

    Supervisor 版エージェント（agent_supervisor.py）の Managed Memory 機能を
    有効化するために必要。LangGraph 版のみの場合は memory_store が未設定で
    このステップはスキップされる。冪等（PATCH）。
    """
    payload = json.dumps({
        "changes": [{
            "principal": sp_id,
            "add": ["READ_MEMORY_STORE", "WRITE_MEMORY_STORE"],
        }],
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{host}/api/2.1/unity-catalog/permissions/memory_store/{memory_store}",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=30):
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")[:200]
        print_error(f"Memory Store 権限付与失敗 ({memory_store}): HTTP {e.code}: {body}")
        return False
    except Exception as e:
        print_error(f"Memory Store 権限付与失敗: {str(e)[:200]}")
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


def grant_lakebase_permissions(sp_id: str):
    """Lakebase PostgreSQL 内部権限を付与する。

    所有権の規則：
      - quickstart の init_lakebase_tables() でテーブルが事前作成された場合、
        テーブルはこの関数を実行している USER の所有 → SP に GRANT が必要（このスクリプトの主目的）。
      - 事前作成されない場合、初回 app 起動時に SP がテーブルを作成し SP が所有する
        → 明示的な GRANT 不要（OWNER は全権限を持つ）。

    したがって、推奨フローは：
      1. quickstart で `init_lakebase_tables()` を実行（USER がテーブル作成）
      2. `databricks bundle deploy`（アプリ + SP 作成）
      3. このスクリプト（USER のテーブルを SP に GRANT）
      4. アプリ起動 — SP は既に必要権限を持つので permission denied は出ない。再起動不要。
    """
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
        from psycopg import sql
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
    seq_privs_str = "USAGE, SELECT, UPDATE"
    table_privs = [
        TablePrivilege.SELECT, TablePrivilege.INSERT,
        TablePrivilege.UPDATE, TablePrivilege.DELETE,
    ]

    # `public` は標準スキーマで常に存在し、LangGraph (short_term + long_term) のテーブルが作られる場所。
    # `ai_chatbot` / `drizzle` はフロントエンド (Express + Drizzle) が初回起動時に作成するスキーマ。
    # SP がそれらを作る場合は SP が所有者となるため明示的な GRANT は不要（スキップ）。
    target_schemas = ["public", "ai_chatbot", "drizzle"]

    for schema_name in target_schemas:
        # 1. スキーマ権限
        try:
            client.grant_schema(grantee=sp_id, schemas=[schema_name], privileges=schema_privs)
        except Exception as e:
            if "does not exist" in str(e).lower():
                if schema_name != "public":
                    print_warn(
                        f"Lakebase {schema_name} スキーマ未作成（SP がアプリ起動時に作成し所有 → GRANT 不要）"
                    )
                else:
                    print_error(f"Lakebase public スキーマが存在しません: {str(e)[:200]}")
                continue
            else:
                print_error(f"Lakebase {schema_name} スキーマ権限付与失敗: {str(e)[:200]}")
                continue

        # 2. 既存の全テーブル / シーケンスへ GRANT（0 件でもエラーにならない）
        try:
            client.grant_all_tables_in_schema(
                grantee=sp_id, schemas=[schema_name], privileges=table_privs
            )
        except Exception as e:
            print_error(f"Lakebase {schema_name} 既存テーブル GRANT 失敗: {str(e)[:200]}")
            continue

        try:
            seq_grant = sql.SQL(
                "GRANT " + seq_privs_str + " ON ALL SEQUENCES IN SCHEMA {schema} TO {grantee}"
            ).format(
                schema=sql.Identifier(schema_name),
                grantee=sql.Identifier(sp_id),
            )
            client._execute_composed(seq_grant)
        except Exception as e:
            print_error(f"Lakebase {schema_name} 既存シーケンス GRANT 失敗: {str(e)[:200]}")
            continue

        print_success(
            f"Lakebase {schema_name}: スキーマ + 全テーブル / シーケンス権限を付与"
        )


def main():
    parser = argparse.ArgumentParser(
        description="デプロイ後のアプリ SP に必要な権限を一括付与",
    )
    parser.add_argument(
        "--app-name",
        help="Databricks Apps のアプリ名（--sp-client-id を使う場合は不要）",
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
        if not args.app_name:
            print_error("アプリ名を --app-name <名前> で指定してください。\n"
                        "  例: uv run grant-sp-permissions --app-name freshmart-agent-hiroshi-0505\n"
                        "  または、SP Client ID を直接指定: --sp-client-id <UUID>")
            sys.exit(1)
        app_name = args.app_name
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
    # Prompt Registry を使う場合、get_prompt_version_by_alias などで
    # CREATE_FUNCTION / EXECUTE / MANAGE / APPLY_TAG が必要となるため
    # 常時付与しておく（使わない場合も害はない）
    print("=== 1. Unity Catalog データスキーマ権限 ===")
    grant_uc_permissions(token, host, "catalog", catalog, sp_id, ["USE_CATALOG"])
    grant_uc_permissions(token, host, "schema", f"{catalog}.{schema}", sp_id,
                         ["USE_SCHEMA", "SELECT", "MODIFY",
                          "CREATE_FUNCTION", "EXECUTE", "APPLY_TAG"])
    # MANAGE は他の権限と一緒に付与すると API が拒否することがあるので単独で付与
    grant_uc_permissions(token, host, "schema", f"{catalog}.{schema}", sp_id, ["MANAGE"])
    print_success(
        f"データスキーマ: USE_CATALOG, USE_SCHEMA, SELECT, MODIFY, "
        f"CREATE_FUNCTION, EXECUTE, APPLY_TAG, MANAGE on {catalog}.{schema}"
    )

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
        print_success(f"トレーススキーマ: USE_CATALOG, USE_SCHEMA, SELECT, MODIFY on {tc}.{ts}")
    else:
        # 同一スキーマの場合、MODIFY は既にデータスキーマ権限で付与済み
        print_success(f"トレーススキーマ（データスキーマと同一、権限付与済み）: {tc}.{ts}")

    # ── 3. Vector Search エンドポイント権限 ──
    print("\n=== 3. Vector Search エンドポイント権限 ===")
    if vs_index:
        if grant_vs_endpoint_permission(token, host, vs_index, sp_id):
            print_success(f"VS エンドポイント: CAN_USE on (endpoint hosting {vs_index})")
        else:
            print_warn("VS エンドポイント権限付与をスキップしました（手動で確認してください）")
    else:
        print_warn("VECTOR_SEARCH_INDEX 未設定 → VS エンドポイント権限付与スキップ")

    # ── 4. Managed Memory Store 権限（Supervisor 版エージェント用）──
    print("\n=== 4. Managed Memory Store 権限（Supervisor 版用）===")
    memory_store = os.getenv("DATABRICKS_MEMORY_STORE", "").strip()
    if memory_store:
        if grant_memory_store_permission(token, host, memory_store, sp_id):
            print_success(
                f"Memory Store: READ_MEMORY_STORE + WRITE_MEMORY_STORE on {memory_store}"
            )
        else:
            print_warn("Memory Store 権限付与をスキップしました（手動で確認してください）")
    else:
        print_warn(
            "DATABRICKS_MEMORY_STORE 未設定 → Memory Store 権限付与スキップ "
            "(Supervisor 版で長期メモリを使わないなら OK)"
        )

    # ── 5. Lakebase PostgreSQL 権限 ──
    print("\n=== 5. Lakebase PostgreSQL 権限 ===")
    grant_lakebase_permissions(sp_id)

    print(f"\n{'='*60}")
    print("完了! 次のステップ:")
    print(f"  - アプリ未起動なら:  databricks apps start {app_name}")
    print(f"  - 既に起動済みなら: 再起動不要（権限は次回リクエストから有効）")
    print(f"{'='*60}")
