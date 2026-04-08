#!/usr/bin/env python3
"""
ワークショップで作成したリソースを一括削除するスクリプト。

.env ファイルからリソース情報を読み取り、一つ一つ確認しながら削除します。

Usage:
    uv run cleanup
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env", override=True)


def print_header(text: str):
    print(f"\n{'=' * 60}")
    print(text)
    print("=" * 60)


def print_success(text: str):
    print(f"  ✓ {text}")


def print_skip(text: str):
    print(f"  → スキップ: {text}")


def print_error(text: str):
    print(f"  ✗ {text}")


def confirm(prompt: str) -> bool:
    """ユーザーに確認を求める。y/N でデフォルトは No。"""
    response = input(f"  {prompt} (y/N): ").strip().lower()
    return response == "y"


def get_profile() -> str:
    return os.getenv("DATABRICKS_CONFIG_PROFILE", "DEFAULT")


def run_cmd(cmd: list[str], check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def get_app_name() -> str:
    """databricks.yml からアプリ名を取得。"""
    yml_path = Path("databricks.yml")
    if not yml_path.exists():
        return ""
    content = yml_path.read_text()
    match = re.search(r'name:\s*"([^"]+)"', content)
    return match.group(1) if match else ""


def get_catalog_schema() -> tuple[str, str]:
    """VECTOR_SEARCH_INDEX から catalog と schema を推定。"""
    vs_index = os.getenv("VECTOR_SEARCH_INDEX", "")
    if vs_index and "." in vs_index:
        parts = vs_index.replace("/", ".").split(".")
        if len(parts) >= 2:
            return parts[0], parts[1]
    return "", ""


def delete_app(profile: str):
    """Databricks App を削除。"""
    app_name = get_app_name()
    if not app_name:
        print("  アプリ名が databricks.yml から取得できません")
        return

    print(f"\n  アプリ名: {app_name}")
    result = run_cmd(["databricks", "apps", "get", app_name, "-p", profile, "-o", "json"])
    if result.returncode != 0:
        print_skip("アプリが存在しません")
        return

    app_data = json.loads(result.stdout)
    url = app_data.get("url", "?")
    state = app_data.get("app_status", {}).get("state", "?")
    print(f"  URL: {url}")
    print(f"  ステータス: {state}")

    if not confirm(f"アプリ '{app_name}' を削除しますか？"):
        print_skip("ユーザーがキャンセル")
        return

    result = run_cmd(["databricks", "apps", "delete", app_name, "-p", profile])
    if result.returncode == 0:
        print_success(f"アプリ '{app_name}' を削除しました")
    else:
        print_error(f"アプリ削除に失敗: {result.stderr[:200]}")


def delete_experiment(profile: str, exp_id: str, label: str):
    """MLflow Experiment を削除。"""
    if not exp_id:
        print_skip(f"{label}: ID 未設定")
        return

    result = run_cmd(["databricks", "experiments", "get-experiment", exp_id, "-p", profile, "-o", "json"])
    if result.returncode != 0:
        print_skip(f"{label}: Experiment {exp_id} が存在しません")
        return

    exp_data = json.loads(result.stdout)
    exp = exp_data.get("experiment", exp_data)
    name = exp.get("name", "?")
    print(f"\n  {label}")
    print(f"  名前: {name}")
    print(f"  ID: {exp_id}")

    if not confirm(f"Experiment '{name}' を削除しますか？"):
        print_skip("ユーザーがキャンセル")
        return

    result = run_cmd(["databricks", "experiments", "delete-experiment", exp_id, "-p", profile])
    if result.returncode == 0:
        print_success(f"Experiment '{name}' を削除しました")
    else:
        print_error(f"削除に失敗: {result.stderr[:200]}")


def delete_vector_search_index(profile: str):
    """Vector Search インデックスを削除。"""
    vs_index = os.getenv("VECTOR_SEARCH_INDEX", "")
    if not vs_index:
        print_skip("VECTOR_SEARCH_INDEX 未設定")
        return

    # ドット形式に正規化
    index_name = vs_index.replace("/", ".")
    print(f"\n  インデックス: {index_name}")

    result = run_cmd(["databricks", "api", "get", f"/api/2.0/vector-search/indexes/{index_name}", "-p", profile])
    if result.returncode != 0 or "error" in result.stdout.lower():
        print_skip(f"インデックス {index_name} が存在しません")
        return

    if not confirm(f"Vector Search インデックス '{index_name}' を削除しますか？"):
        print_skip("ユーザーがキャンセル")
        return

    result = run_cmd(["databricks", "api", "delete", f"/api/2.0/vector-search/indexes/{index_name}", "-p", profile])
    if result.returncode == 0:
        print_success(f"インデックス '{index_name}' を削除しました")
    else:
        print_error(f"削除に失敗: {result.stderr[:200]}")


def delete_genie_space(profile: str):
    """Genie Space を削除。"""
    space_id = os.getenv("GENIE_SPACE_ID", "")
    if not space_id:
        print_skip("GENIE_SPACE_ID 未設定")
        return

    print(f"\n  Genie Space ID: {space_id}")

    if not confirm(f"Genie Space '{space_id}' を削除しますか？"):
        print_skip("ユーザーがキャンセル")
        return

    result = run_cmd(["databricks", "api", "delete", f"/api/2.0/genie/spaces/{space_id}", "-p", profile])
    if result.returncode == 0:
        print_success(f"Genie Space を削除しました")
    else:
        print_error(f"削除に失敗: {result.stderr[:200]}")


def delete_lakebase(profile: str):
    """Lakebase プロジェクトを削除。"""
    project = os.getenv("LAKEBASE_AUTOSCALING_PROJECT", "")
    if not project:
        print_skip("LAKEBASE_AUTOSCALING_PROJECT 未設定")
        return

    branch = os.getenv("LAKEBASE_AUTOSCALING_BRANCH", "")
    print(f"\n  プロジェクト: {project}")
    print(f"  ブランチ: {branch}")

    if not confirm(f"Lakebase プロジェクト '{project}' を削除しますか？（ブランチも一緒に削除されます）"):
        print_skip("ユーザーがキャンセル")
        return

    result = run_cmd(["databricks", "api", "delete", f"/api/2.0/postgres/projects/{project}", "-p", profile])
    if result.returncode == 0:
        print_success(f"Lakebase プロジェクト '{project}' を削除しました")
    else:
        print_error(f"削除に失敗: {result.stderr[:200]}")


def delete_schema(profile: str):
    """Unity Catalog スキーマを CASCADE で削除（テーブル・トレーステーブルも一緒に削除）。"""
    catalog, schema = get_catalog_schema()
    if not catalog or not schema:
        print_skip("カタログ/スキーマが特定できません")
        return

    full_schema = f"{catalog}.{schema}"
    print(f"\n  スキーマ: {full_schema}")
    print(f"  ⚠ CASCADE 削除：スキーマ内の全テーブル・インデックス・トレーステーブルが削除されます")

    if not confirm(f"スキーマ '{full_schema}' を CASCADE で削除しますか？"):
        print_skip("ユーザーがキャンセル")
        return

    # Warehouse ID を取得
    warehouse_id = os.getenv("MLFLOW_TRACING_SQL_WAREHOUSE_ID", "")
    if not warehouse_id:
        warehouse_id = input("  SQL Warehouse ID を入力してください: ").strip()
        if not warehouse_id:
            print_skip("Warehouse ID が未指定")
            return

    import urllib.request
    import urllib.error

    # トークン取得
    token_result = run_cmd(["databricks", "auth", "token", "-p", profile, "-o", "json"])
    if token_result.returncode != 0:
        print_error("トークン取得に失敗")
        return
    token = json.loads(token_result.stdout)["access_token"]

    host = os.getenv("DATABRICKS_HOST", "")
    if not host:
        host_result = run_cmd(["databricks", "auth", "describe", "-p", profile, "-o", "json"])
        if host_result.returncode == 0:
            host_data = json.loads(host_result.stdout)
            host = host_data.get("host", "")

    if not host:
        print_error("DATABRICKS_HOST が取得できません")
        return

    stmt = f"DROP SCHEMA IF EXISTS `{catalog}`.`{schema}` CASCADE"
    payload = json.dumps({
        "warehouse_id": warehouse_id,
        "statement": stmt,
        "wait_timeout": "50s",
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{host}/api/2.0/sql/statements",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        state = data.get("status", {}).get("state", "UNKNOWN")
        if state in ("SUCCEEDED", "CLOSED"):
            print_success(f"スキーマ '{full_schema}' を削除しました（CASCADE）")
        else:
            err = data.get("status", {}).get("error", {}).get("message", "")
            print_error(f"スキーマ削除: {state} {err[:200]}")
    except Exception as e:
        print_error(f"スキーマ削除に失敗: {e}")


def delete_local_files():
    """ローカルファイルの削除。"""
    files_to_delete = [
        (".env", "環境変数ファイル"),
        (".venv", "Python 仮想環境"),
        ("backend.log", "バックエンドログ"),
        ("frontend.log", "フロントエンドログ"),
        (".databricks", "バンドルステート"),
    ]

    for path_str, desc in files_to_delete:
        path = Path(path_str)
        if not path.exists():
            continue
        print(f"\n  {desc}: {path_str}")
        if not confirm(f"'{path_str}' を削除しますか？"):
            print_skip("ユーザーがキャンセル")
            continue

        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        print_success(f"'{path_str}' を削除しました")


def delete_bundle_workspace(profile: str):
    """ワークスペース上のバンドルファイルを削除。"""
    result = run_cmd(["databricks", "current-user", "me", "-p", profile, "-o", "json"])
    if result.returncode != 0:
        print_skip("ユーザー情報が取得できません")
        return

    username = json.loads(result.stdout).get("userName", "")
    bundle_path = f"/Workspace/Users/{username}/.bundle/retail_grocery_ltm_memory"
    print(f"\n  バンドルパス: {bundle_path}")

    if not confirm(f"ワークスペースのバンドルファイルを削除しますか？"):
        print_skip("ユーザーがキャンセル")
        return

    result = run_cmd(["databricks", "workspace", "delete", bundle_path, "--recursive", "-p", profile])
    if result.returncode == 0:
        print_success("バンドルファイルを削除しました")
    else:
        print_error(f"削除に失敗: {result.stderr[:200]}")


def main():
    print_header("フレッシュマート AI エージェント — リソースクリーンアップ")
    print()
    print("このスクリプトは、ワークショップで作成したリソースを一つずつ確認しながら削除します。")
    print(".env ファイルからリソース情報を読み取ります。")
    print()

    env_path = Path(".env")
    if not env_path.exists():
        print("⚠ .env ファイルが見つかりません。削除対象のリソースを特定できません。")
        sys.exit(1)

    profile = get_profile()
    print(f"Databricks プロファイル: {profile}")

    if not confirm("クリーンアップを開始しますか？"):
        print("\nキャンセルしました。")
        return

    # 1. Databricks App
    print_header("[1/8] Databricks App")
    delete_app(profile)

    # 2. MLflow Experiments
    print_header("[2/8] MLflow Experiments")
    delete_experiment(profile, os.getenv("MLFLOW_EXPERIMENT_ID", ""), "モニタリング Experiment")
    delete_experiment(profile, os.getenv("MLFLOW_EVAL_EXPERIMENT_ID", ""), "評価 Experiment")

    # 3. Vector Search Index
    print_header("[3/8] Vector Search インデックス")
    delete_vector_search_index(profile)

    # 4. Genie Space
    print_header("[4/8] Genie Space")
    delete_genie_space(profile)

    # 5. Lakebase
    print_header("[5/8] Lakebase プロジェクト")
    delete_lakebase(profile)

    # 6. Unity Catalog スキーマ（テーブル・トレーステーブルを含む）
    print_header("[6/8] Unity Catalog スキーマ")
    delete_schema(profile)

    # 7. ワークスペースのバンドルファイル
    print_header("[7/8] ワークスペースのバンドルファイル")
    delete_bundle_workspace(profile)

    # 8. ローカルファイル
    print_header("[8/8] ローカルファイル")
    delete_local_files()

    print_header("クリーンアップ完了")
    print("\n削除をスキップしたリソースは手動で削除してください。\n")


if __name__ == "__main__":
    main()
