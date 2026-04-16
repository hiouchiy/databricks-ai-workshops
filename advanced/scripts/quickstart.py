#!/usr/bin/env python3
"""
Quickstart setup script for Databricks agent development.

This script handles:
- Checking prerequisites (uv, nvm, Node 20, Databricks CLI)
- Databricks authentication (OAuth)
- MLflow experiment creation
- Environment variable configuration (.env)
- Lakebase instance setup (for memory-enabled templates)

Usage:
    uv run quickstart [OPTIONS]

Options:
    --profile NAME    Use specified Databricks profile (non-interactive)
    --host URL        Databricks workspace URL (for initial setup)
    --lakebase-autoscaling-project NAME  Autoscaling Lakebase project name
    --lakebase-autoscaling-branch NAME   Autoscaling Lakebase branch name
    -h, --help        Show this help message
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from scripts.quickstart_core import (
    LANG,
    set_language,
    t,
    print_header,
    print_step,
    print_success,
    print_error,
    print_troubleshooting_auth,
    print_troubleshooting_api,
    command_exists,
    run_command,
    get_command_output,
    check_prerequisites,
    check_missing_prerequisites,
    check_node_version,
    setup_env_file,
    update_env_file,
    read_env_file,
    get_env_value,
    get_databricks_profiles,
    validate_profile,
    authenticate_profile,
    select_profile_interactive,
    setup_databricks_auth,
    get_databricks_host,
    get_databricks_username,
    _create_single_experiment,
    _verify_experiment,
    create_mlflow_experiment,
    check_lakebase_required,
    get_workspace_client,
    create_lakebase_instance,
    select_lakebase_interactive,
    validate_lakebase_autoscaling,
    setup_lakebase,
    _replace_lakebase_env_vars,
    _replace_lakebase_resource,
    update_databricks_yml_lakebase,
    update_app_yaml_lakebase,
    append_env_to_app_yaml,
    update_databricks_yml_experiment,
    update_databricks_yml_resources,
    get_auth_token,
    run_sql_statement,
    api_get,
    api_post,
    run_trace_setup_on_databricks,
    select_vs_endpoint_interactive,
    select_warehouse_interactive,
    create_catalog_schema,
    check_tables_exist,
    check_chunked_table_exists,
    generate_data,
    enable_cdf,
    create_vector_search_index,
    _get_table_columns,
    _build_serialized_space,
    create_genie_space,
    install_dependencies,
    init_lakebase_tables,
)


def select_language():
    """Prompt user to select language at the very beginning."""
    print("=" * 50)
    print("  Language / 言語選択")
    print("=" * 50)
    print("  1) 日本語")
    print("  2) English")
    choice = input("\n  Select / 選択 [1]: ").strip()
    if choice == "2":
        set_language("en")
        print("\n  → English selected\n")
    else:
        set_language("ja")
        print("\n  → 日本語を選択しました\n")


def main():
    parser = argparse.ArgumentParser(
        description="FreshMart AI Agent - Quickstart Setup",
    )
    parser.add_argument("--profile", default=None, help="Databricks CLI profile name")
    parser.add_argument("--host", default=None, help="Databricks workspace URL")
    parser.add_argument("--catalog", default=None, help="Unity Catalog name")
    parser.add_argument("--schema", default=None, help="Schema name")
    parser.add_argument("--warehouse-id", default=None, help="SQL Warehouse ID")
    parser.add_argument("--vs-endpoint", default=None, help="Vector Search endpoint name")
    parser.add_argument(
        "--lakebase-autoscaling-project",
        help="Lakebase autoscaling project name",
    )
    parser.add_argument(
        "--lakebase-autoscaling-branch",
        help="Lakebase autoscaling branch name",
    )
    parser.add_argument(
        "--lang", choices=["ja", "en"], default=None,
        help="Language (ja/en). Skips interactive language selection.",
    )
    args = parser.parse_args()

    if args.lang:
        set_language(args.lang)
    else:
        select_language()

    # 全 CLI 引数が揃っていれば非対話モード
    non_interactive = all([
        args.profile, args.catalog, args.schema, args.vs_endpoint,
        args.lakebase_autoscaling_project, args.lakebase_autoscaling_branch,
    ])

    try:
        print_header(t("フレッシュマート AI エージェント - クイックスタートセットアップ",
                        "FreshMart AI Agent - Quickstart Setup"))

        # ── Phase 1: 前提条件チェック ──
        print_step(t("[1/8] 前提条件チェック", "[1/8] Prerequisites check"))
        prereqs = check_prerequisites()
        missing = check_missing_prerequisites(prereqs)
        if missing:
            print_error(t("不足している前提条件:", "Missing prerequisites:"))
            for item in missing:
                print(f"  • {item}")
            print(t("\nインストール後に再実行してください。",
                     "\nPlease install the above and run again."))
            sys.exit(1)
        node_error = check_node_version()
        if node_error:
            print_error(t(f"Node.js バージョンエラー: {node_error}",
                           f"Node.js version error: {node_error}"))
            sys.exit(1)
        print_success(t("前提条件OK", "Prerequisites OK"))
        setup_env_file()

        # ── Phase 2: 認証 ──
        print_step(t("[2/8] Databricks 認証", "[2/8] Databricks authentication"))
        profile_name = setup_databricks_auth(args.profile, args.host)
        username = get_databricks_username(profile_name)
        host = get_databricks_host(profile_name)
        token = get_auth_token(profile_name)
        print_success(t(f"認証OK: {username}", f"Authenticated: {username}"))
        print(t(f"  ワークスペース: {host}", f"  Workspace: {host}"))

        # ── Phase 3: ユーザー入力 ──
        print_step(t("[3/8] ワークスペース設定", "[3/8] Workspace configuration"))

        # Catalog
        if args.catalog:
            catalog = args.catalog
            print_success(t(f"カタログ: {catalog}", f"Catalog: {catalog}"))
        else:
            default_catalog = username.split("@")[0].replace(".", "_")
            catalog = input(t(f"  カタログ名 [{default_catalog}]: ",
                               f"  Catalog name [{default_catalog}]: ")).strip() or default_catalog

        # Schema
        if args.schema:
            schema = args.schema
            print_success(t(f"スキーマ: {schema}", f"Schema: {schema}"))
        else:
            default_schema = "retail_agent"
            schema = input(t(f"  スキーマ名 [{default_schema}]: ",
                              f"  Schema name [{default_schema}]: ")).strip() or default_schema

        # Warehouse
        if args.warehouse_id:
            warehouse_id = args.warehouse_id
            print_success(f"Warehouse ID: {warehouse_id}")
        elif non_interactive:
            # 非対話: 最初の RUNNING ウェアハウスを自動選択
            wh_result = run_command(
                ["databricks", "warehouses", "list", "-p", profile_name, "-o", "json"],
                check=True,
            )
            warehouses = json.loads(wh_result.stdout)
            running = [w for w in warehouses if w.get("state") == "RUNNING"]
            picked = running[0] if running else warehouses[0]
            warehouse_id = picked["id"]
            print_success(t(f"ウェアハウスを自動選択: {picked.get('name', '')} ({warehouse_id})",
                             f"Auto-selected warehouse: {picked.get('name', '')} ({warehouse_id})"))
        else:
            warehouse_id, _ = select_warehouse_interactive(profile_name)

        # VS Endpoint
        if args.vs_endpoint:
            vs_endpoint = args.vs_endpoint
            # Verify the provided endpoint exists
            ep_status = api_get(f"/api/2.0/vector-search/endpoints/{vs_endpoint}", token, host)
            if "error" not in ep_status:
                ep_state = ep_status.get("endpoint_status", {}).get("state", "UNKNOWN")
                print_success(t(f"VS エンドポイント: {vs_endpoint} ({ep_state})",
                                 f"VS endpoint: {vs_endpoint} ({ep_state})"))
            else:
                print(t(f"  ⚠ エンドポイント {vs_endpoint} が見つかりません。",
                         f"  Warning: Endpoint {vs_endpoint} not found."))
                vs_endpoint = ""
        else:
            vs_endpoint = select_vs_endpoint_interactive(token, host)

        # ── Phase 4: リソース作成 ──
        print_step(t("[4/8] リソース作成", "[4/8] Resource creation"))

        # 4-1: Catalog & Schema
        create_catalog_schema(token, host, warehouse_id, catalog, schema)

        # 4-2 & 4-3: Data generation (skip if tables already exist)
        generate_data(profile_name, warehouse_id, catalog, schema, token=token, host=host)

        # 4-4: CDF
        enable_cdf(token, host, warehouse_id, catalog, schema)

        # 4-5: Vector Search Index
        vs_index = ""
        if vs_endpoint:
            vs_index = create_vector_search_index(token, host, catalog, schema, vs_endpoint)
        else:
            vs_index = f"{catalog}.{schema}.policy_docs_index"
            print(t("  ⚠ VS エンドポイント未指定。インデックスは手動で作成してください。",
                     "  Warning: VS endpoint not specified. Please create the index manually."))

        # 4-6: Genie Space
        if non_interactive:
            # 非対話モード: API で自動作成
            print_step(t("Genie Space を自動作成中...", "Auto-creating Genie Space..."))
            tables = ["customers", "products", "stores", "transactions",
                      "transaction_items", "payment_history"]
            serialized = _build_serialized_space(catalog, schema, tables)
            body = {
                "title": "フレッシュマート 小売データ",
                "description": "フレッシュマートの小売データに対する自然言語クエリ。",
                "warehouse_id": warehouse_id,
                "serialized_space": serialized,
            }
            result = api_post("/api/2.0/genie/spaces", token, host, body)
            genie_space_id = result.get("space_id", "")
            if genie_space_id:
                print_success(t(f"Genie Space 作成完了 (ID: {genie_space_id})",
                                 f"Genie Space created (ID: {genie_space_id})"))
            else:
                print_error(t(f"Genie Space 作成失敗: {result.get('error', '')[:200]}",
                               f"Genie Space creation failed: {result.get('error', '')[:200]}"))
                genie_space_id = ""
        else:
            genie_space_id = create_genie_space(token, host, warehouse_id, catalog, schema)

        # 4-7: Lakebase
        lakebase_config = None
        lakebase_required = (
            (args.lakebase_autoscaling_project and args.lakebase_autoscaling_branch)
            or check_lakebase_required()
        )
        if lakebase_required:
            if non_interactive and args.lakebase_autoscaling_project:
                # 非対話: バリデーション → 失敗ならプロジェクト+ブランチ自動作成
                project = args.lakebase_autoscaling_project
                branch = args.lakebase_autoscaling_branch
                print_step(t(f"Lakebase を検証/作成中: {project}/{branch}",
                              f"Validating/creating Lakebase: {project}/{branch}"))
                branch_info = validate_lakebase_autoscaling(profile_name, project, branch)
                if not branch_info:
                    # プロジェクトが存在しない → SDK で直接作成
                    print(t("  プロジェクトを自動作成中...", "  Auto-creating project..."))
                    try:
                        w = get_workspace_client(profile_name)
                        from databricks.sdk.service.postgres import Branch, BranchSpec, Project, ProjectSpec
                        proj_op = w.postgres.create_project(
                            project=Project(spec=ProjectSpec(display_name=project)),
                            project_id=project,
                        )
                        created_proj = proj_op.wait()
                        print_success(t(f"プロジェクト作成完了: {project}",
                                         f"Project created: {project}"))
                        branch_op = w.postgres.create_branch(
                            parent=created_proj.name,
                            branch=Branch(spec=BranchSpec(no_expiry=True)),
                            branch_id=branch,
                        )
                        created_branch = branch_op.wait()
                        branch = created_branch.name.split("/branches/")[-1] if "/branches/" in created_branch.name else branch
                        print_success(t(f"ブランチ作成完了: {branch}",
                                         f"Branch created: {branch}"))
                    except Exception as e:
                        print_error(f"Lakebase auto-create failed: {str(e)[:200]}")
                    branch_info = validate_lakebase_autoscaling(profile_name, project, branch)
                if branch_info:
                    update_env_file("LAKEBASE_AUTOSCALING_PROJECT", project)
                    update_env_file("LAKEBASE_AUTOSCALING_BRANCH", branch)
                    pg_host = branch_info.get("host", "")
                    if pg_host:
                        update_env_file("PGHOST", pg_host)
                    update_env_file("PGUSER", username)
                    update_env_file("PGDATABASE", "databricks_postgres")
                    lakebase_config = {
                        "type": "autoscaling",
                        "project": project,
                        "branch": branch,
                        "database_id": branch_info.get("database_id", ""),
                    }
                    print_success(t(f"Lakebase: {project} (branch: {branch})",
                                     f"Lakebase: {project} (branch: {branch})"))
                else:
                    print_error(t("Lakebase セットアップに失敗", "Lakebase setup failed"))
            else:
                lakebase_config = setup_lakebase(
                    profile_name, username,
                    autoscaling_project=args.lakebase_autoscaling_project,
                    autoscaling_branch=args.lakebase_autoscaling_branch,
                )
            if lakebase_config:
                update_databricks_yml_lakebase(lakebase_config)
                update_app_yaml_lakebase(lakebase_config)

        # 4-8: MLflow Experiments
        if non_interactive:
            base = f"/Users/{username}/freshmart-agent"
            monitoring_name, monitoring_id = _create_single_experiment(profile_name, f"{base}-monitoring")
            eval_name, eval_id = _create_single_experiment(profile_name, f"{base}-evaluation")
        else:
            monitoring_name, monitoring_id, eval_name, eval_id = create_mlflow_experiment(
                profile_name, username
            )

        # ── Phase 5: .env 更新 ──
        print_step(t("[5/8] 環境設定 (.env)", "[5/8] Environment configuration (.env)"))
        update_env_file("DATABRICKS_HOST", host)
        update_env_file("MLFLOW_EXPERIMENT_ID", monitoring_id)
        update_env_file("MLFLOW_EVAL_EXPERIMENT_ID", eval_id)
        update_env_file("GENIE_SPACE_ID", genie_space_id)
        update_env_file("VECTOR_SEARCH_INDEX", vs_index)
        update_databricks_yml_experiment(monitoring_id)
        update_databricks_yml_resources(genie_space_id, vs_index)
        print_success(t(".env / databricks.yml 更新完了",
                         ".env / databricks.yml updated"))

        # Delta Table tracing
        # 既存 Experiment に UC テーブル紐付けがあるか確認
        tracing_dest = ""
        _existing_dest = ""
        try:
            exp_result = run_command(
                ["databricks", "experiments", "get-experiment", monitoring_id, "-p", profile_name, "-o", "json"],
                check=False,
            )
            if exp_result.returncode == 0:
                exp_data = json.loads(exp_result.stdout)
                exp_tags = exp_data.get("experiment", exp_data).get("tags", [])
                for tag in exp_tags:
                    if tag.get("key") == "mlflow.experiment.databricksTraceDestinationPath":
                        _existing_dest = tag.get("value", "")
                        break
        except Exception:
            pass

        if _existing_dest:
            # 既存 Experiment に Delta Table 紐付けが既にある
            tracing_dest = _existing_dest
            update_env_file("MLFLOW_TRACING_DESTINATION", tracing_dest)
            update_env_file("MLFLOW_TRACING_SQL_WAREHOUSE_ID", warehouse_id)
            append_env_to_app_yaml("MLFLOW_TRACING_DESTINATION", tracing_dest)
            append_env_to_app_yaml("MLFLOW_TRACING_SQL_WAREHOUSE_ID", warehouse_id)
            print_success(t(f"トレース送信先: Unity Catalog ({tracing_dest})（既存 Experiment から検出）",
                             f"Trace destination: Unity Catalog ({tracing_dest}) (detected from existing Experiment)"))
        elif non_interactive:
            print_success(t("トレース送信先: MLflow Experiment（デフォルト）",
                             "Trace destination: MLflow Experiment (default)"))
            use_delta = "n"
        else:
            print()
            print(t("  トレース送信先の選択:", "  Select trace destination:"))
            print(t("    デフォルト: MLflow Experiment（すぐに使える）",
                     "    Default: MLflow Experiment (ready to use)"))
            print(t("    オプション: Unity Catalog Delta Table（SQL クエリ可能、長期保持）",
                     "    Option: Unity Catalog Delta Table (SQL queryable, long-term retention)"))
            use_delta = input(t("\n  Unity Catalog Delta Table に送信しますか？ (y/N): ",
                                 "\n  Send traces to Unity Catalog Delta Table? (y/N): ")).strip().lower()
            if use_delta == "y":
                default_dest = f"{catalog}.{schema}"
                tracing_dest = input(t(f"  送信先スキーマ [{default_dest}]: ",
                                        f"  Destination schema [{default_dest}]: ")).strip() or default_dest

                # カタログ・スキーマの存在確認、なければ作成
                if "." in tracing_dest:
                    _t_cat, _t_sch = tracing_dest.split(".", 1)
                    verify = run_sql_statement(f"DESCRIBE SCHEMA `{_t_cat}`.`{_t_sch}`", token, host, warehouse_id)
                    if verify.get("status", {}).get("state") not in ("SUCCEEDED", "CLOSED"):
                        print(t(f"  スキーマ {tracing_dest} が存在しません。作成します...",
                                 f"  Schema {tracing_dest} does not exist. Creating..."))
                        run_sql_statement(f"CREATE CATALOG IF NOT EXISTS `{_t_cat}`", token, host, warehouse_id)
                        run_sql_statement(f"CREATE SCHEMA IF NOT EXISTS `{_t_cat}`.`{_t_sch}`", token, host, warehouse_id)
                        verify2 = run_sql_statement(f"DESCRIBE SCHEMA `{_t_cat}`.`{_t_sch}`", token, host, warehouse_id)
                        if verify2.get("status", {}).get("state") in ("SUCCEEDED", "CLOSED"):
                            print_success(t(f"スキーマ作成完了: {tracing_dest}",
                                             f"Schema created: {tracing_dest}"))
                        else:
                            print_error(t(f"スキーマ {tracing_dest} の作成に失敗しました。権限を確認してください。",
                                           f"Failed to create schema {tracing_dest}. Please check permissions."))

                update_env_file("MLFLOW_TRACING_DESTINATION", tracing_dest)
                update_env_file("MLFLOW_TRACING_SQL_WAREHOUSE_ID", warehouse_id)
                append_env_to_app_yaml("MLFLOW_TRACING_DESTINATION", tracing_dest)
                append_env_to_app_yaml("MLFLOW_TRACING_SQL_WAREHOUSE_ID", warehouse_id)
                print_success(t(f"トレース送信先: Unity Catalog ({tracing_dest})",
                                 f"Trace destination: Unity Catalog ({tracing_dest})"))
                print_success(t(".env と app.yaml の両方に設定を追加しました",
                                 "Settings added to both .env and app.yaml"))

                # トレーステーブルの初期作成を即座に実行
                _t_cat2, _t_sch2 = tracing_dest.split(".", 1)
                print()
                print(t("  トレーステーブルを Databricks 上で自動作成します...",
                         "  Auto-creating trace tables on Databricks..."))
                trace_setup_ok = run_trace_setup_on_databricks(
                    profile_name=profile_name,
                    username=username,
                    catalog=_t_cat2,
                    schema=_t_sch2,
                    warehouse_id=warehouse_id,
                    experiment_id=monitoring_id,
                )
                if trace_setup_ok:
                    print_success(t("トレーステーブル作成完了!",
                                     "Trace table setup complete!"))
                    print(t("  以下の Delta Table が作成されました:",
                             "  The following Delta Tables were created:"))
                    print(f"    - {tracing_dest}.mlflow_experiment_trace_otel_spans")
                    print(f"    - {tracing_dest}.mlflow_experiment_trace_otel_logs")
                    print(f"    - {tracing_dest}.mlflow_experiment_trace_otel_metrics")
                else:
                    print_error(t("自動作成に失敗しました。手動で実行してください:",
                                   "Automatic setup failed. Please run manually:"))
                    print()
                    print("```python")
                    print("import os")
                    print(f'os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = "{warehouse_id}"')
                    print("import mlflow")
                    print("from mlflow.entities import UCSchemaLocation")
                    print(f'mlflow.tracing.set_experiment_trace_location(')
                    print(f'    location=UCSchemaLocation(catalog_name="{_t_cat2}", schema_name="{_t_sch2}"),')
                    print(f'    experiment_id="{monitoring_id}",')
                    print(")")
                    print("```")
            else:
                print_success(t("トレース送信先: MLflow Experiment（デフォルト）",
                                 "Trace destination: MLflow Experiment (default)"))

        # Prompt Registry
        if non_interactive:
            use_prompt_registry = "n"
            print_success(t("Prompt Registry: 使用しない（ハードコード版）",
                             "Prompt Registry: Not used (hardcoded version)"))
        else:
            print()
            print(t("  Prompt Registry の選択:", "  Prompt Registry selection:"))
            print(t("    デフォルト: ハードコード（agent.py に組み込み済み、設定不要）",
                     "    Default: Hardcoded (built into agent.py, no setup needed)"))
            print(t("    オプション: Unity Catalog Prompt Registry（バージョン管理・A/Bテスト・ロールバック）",
                     "    Option: Unity Catalog Prompt Registry (version control, A/B testing, rollback)"))
            use_prompt_registry = input(t("\n  Prompt Registry を使用しますか？ (y/N): ",
                                           "\n  Use Prompt Registry? (y/N): ")).strip().lower()
        if use_prompt_registry == "y":
            prompt_name = f"{catalog}.{schema}.freshmart_system_prompt"
            print(t(f"  プロンプト登録中: {prompt_name} ...",
                     f"  Registering prompt: {prompt_name} ..."))
            try:
                result = subprocess.run(
                    ["uv", "run", "register-prompt", "--name", prompt_name],
                    capture_output=True, text=True,
                )
                if result.returncode == 0:
                    update_env_file("PROMPT_REGISTRY_NAME", prompt_name)
                    append_env_to_app_yaml("PROMPT_REGISTRY_NAME", prompt_name)
                    print_success(f"Prompt Registry: {prompt_name}")
                else:
                    print_error(t(f"プロンプト登録に失敗: {result.stderr[-200:]}",
                                   f"Prompt registration failed: {result.stderr[-200:]}"))
                    print(t("  ハードコード版を使用します。",
                             "  Using hardcoded version."))
            except Exception as e:
                print_error(t(f"プロンプト登録に失敗: {e}",
                               f"Prompt registration failed: {e}"))
                print(t("  ハードコード版を使用します。",
                         "  Using hardcoded version."))
        else:
            print_success(t("Prompt Registry: 使用しない（ハードコード版）",
                             "Prompt Registry: Not used (hardcoded version)"))

        # workshop_setup.py のプレースホルダーを更新
        setup_notebook = Path("workshop_setup.py")
        if setup_notebook.exists():
            content = setup_notebook.read_text()
            replacements = {
                '"<CATALOG>"': f'"{catalog}"',
                '"<SCHEMA>"': f'"{schema}"',
                '"<WAREHOUSE-ID>"': f'"{warehouse_id}"',
                '"<MONITORING-EXPERIMENT-ID>"': f'"{monitoring_id}"',
                '"<EVAL-EXPERIMENT-ID>"': f'"{eval_id}"',
                '"<GENIE-SPACE-ID>"': f'"{genie_space_id}"',
                '"<LAKEBASE-PROJECT>"': f'"{lakebase_config["project"]}"' if lakebase_config else '"<LAKEBASE-PROJECT>"',
                '"<LAKEBASE-BRANCH>"': f'"{lakebase_config["branch"]}"' if lakebase_config else '"<LAKEBASE-BRANCH>"',
            }
            for old, new in replacements.items():
                content = content.replace(old, new)
            setup_notebook.write_text(content)
            print_success(t("workshop_setup.py のプレースホルダーを更新しました",
                             "Updated placeholders in workshop_setup.py"))

        # ── Phase 6: 依存関係 ──
        print_step(t("[6/8] 依存関係のインストール", "[6/8] Installing dependencies"))
        install_dependencies()

        # ── Phase 7: Lakebase テーブル初期化 ──
        if lakebase_config:
            print_step(t("[7/8] Lakebase テーブル初期化", "[7/8] Lakebase table initialization"))
            init_lakebase_tables()

        # ── Phase 8: サマリー ──
        print_header(t("セットアップ完了！", "Setup Complete!"))

        # Access LANG from core module
        from scripts import quickstart_core as core
        if core.LANG == "ja":
            summary = f"""
✓ カタログ: {catalog}
✓ スキーマ: {catalog}.{schema}
✓ 構造化データ: 6テーブル生成済み
✓ ポリシー文書: チャンク分割済み
✓ Vector Search: {vs_index}
✓ Genie Space ID: {genie_space_id}

✓ MLflow モニタリング実験: {monitoring_name}
  ID: {monitoring_id}
✓ MLflow 評価実験: {eval_name}
  ID: {eval_id}"""
        else:
            summary = f"""
✓ Catalog: {catalog}
✓ Schema: {catalog}.{schema}
✓ Structured data: 6 tables generated
✓ Policy documents: Chunked
✓ Vector Search: {vs_index}
✓ Genie Space ID: {genie_space_id}

✓ MLflow monitoring experiment: {monitoring_name}
  ID: {monitoring_id}
✓ MLflow evaluation experiment: {eval_name}
  ID: {eval_id}"""

        if host:
            summary += f"\n  {host}/ml/experiments/{monitoring_id}"

        if tracing_dest:
            summary += t(f"\n\n✓ トレース送信先: Unity Catalog ({tracing_dest})",
                          f"\n\n✓ Trace destination: Unity Catalog ({tracing_dest})")
        else:
            summary += t("\n\n✓ トレース送信先: MLflow Experiment（デフォルト）",
                          "\n\n✓ Trace destination: MLflow Experiment (default)")

        if lakebase_config:
            summary += f"\n\n✓ Lakebase: {lakebase_config['project']} (branch: {lakebase_config['branch']})"

        summary += t("\n\n次のステップ: uv run start-app\n",
                      "\n\nNext step: uv run start-app\n")
        print(summary)

        # チームメンバーへの共有情報
        print()
        print("=" * 60)
        print(t("チームメンバーに共有する情報",
                 "Information to share with team members"))
        print("=" * 60)
        print()
        print(t("チームでハンズオンを実施する場合、以下の情報をメンバーに共有してください。",
                 "If running a team hands-on, share the following information with members."))
        print(t("メンバーはクイックスタート実行時にこれらの値を入力します。",
                 "Members will enter these values when running quickstart."))
        print()
        print(t(f"  カタログ名:            {catalog}",
                 f"  Catalog:               {catalog}"))
        print(t(f"  スキーマ名:            {schema}",
                 f"  Schema:                {schema}"))
        print(t(f"  VS エンドポイント名:   {vs_endpoint}",
                 f"  VS endpoint:           {vs_endpoint}"))
        print(f"  Genie Space ID:        {genie_space_id}")
        if lakebase_config:
            print(t(f"  Lakebase プロジェクト:  {lakebase_config['project']}",
                     f"  Lakebase project:      {lakebase_config['project']}"))
            print(t(f"  Lakebase ブランチ:      {lakebase_config['branch']}",
                     f"  Lakebase branch:       {lakebase_config['branch']}"))
        print(t(f"  モニタリング Exp ID:   {monitoring_id}",
                 f"  Monitoring Exp ID:     {monitoring_id}"))
        print(t(f"  評価 Exp ID:           {eval_id}",
                 f"  Evaluation Exp ID:     {eval_id}"))
        print()
        print(t("メンバーの権限付与は以下で実行できます：",
                 "Grant permissions to members with:"))
        print(f"  uv run grant-team-access member1@company.com member2@company.com")
        print("=" * 60)

    except KeyboardInterrupt:
        print(t("\n\nセットアップが中断されました。",
                 "\n\nSetup was interrupted."))
        sys.exit(1)
    except Exception as e:
        print_error(t(f"セットアップ中にエラーが発生しました: {e}",
                       f"Error during setup: {e}"))
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
