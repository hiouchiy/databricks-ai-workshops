#!/usr/bin/env python3
"""
Streamlit GUI wizard for Databricks agent quickstart setup.

Usage:
    uv run streamlit run scripts/quickstart_gui.py
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import streamlit as st

from scripts import quickstart_core as core

# ─────────────────────────────────────────────────────────────────────
# Session state initialisation
# ─────────────────────────────────────────────────────────────────────

_DEFAULTS = {
    "page": 1,
    "lang": "ja",
    # Auth
    "profile_name": "",
    "host": "",
    "username": "",
    "token": "",
    "auth_ok": False,
    # Workspace
    "catalog": "",
    "schema": "",
    "warehouse_id": "",
    "warehouse_name": "",
    "vs_endpoint": "",
    # Lakebase
    "lakebase_mode": "new",
    "lakebase_project": "",
    "lakebase_branch": "",
    "lakebase_config": None,
    "lakebase_required": False,
    # MLflow
    "mlflow_mode": "new",
    "mlflow_base_name": "",
    "monitoring_name": "",
    "monitoring_id": "",
    "eval_name": "",
    "eval_id": "",
    # Options
    "trace_dest_mode": "mlflow",
    "trace_dest_schema": "",
    "use_prompt_registry": False,
    # Execution
    "setup_started": False,
    "setup_complete": False,
    "setup_log": [],
    # Genie
    "genie_space_id": "",
    "vs_index": "",
    # Existing experiment detection
    "existing_trace_dest": "",
}

for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Sync core language
core.set_language(st.session_state.lang)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _t(ja: str, en: str) -> str:
    """Shorthand for bilingual text using core language."""
    return core.t(ja, en)


def _nav_buttons(current: int, *, can_next: bool = True, can_back: bool = True):
    """Render Back / Next navigation buttons."""
    cols = st.columns(2)
    with cols[0]:
        if can_back and current > 1:
            if st.button(_t("← 戻る", "← Back"), key=f"back_{current}"):
                st.session_state.page = current - 1
                st.rerun()
    with cols[1]:
        if can_next:
            if st.button(_t("次へ →", "Next →"), key=f"next_{current}", type="primary"):
                st.session_state.page = current + 1
                st.rerun()


def _list_warehouses(profile_name: str) -> list[dict]:
    """Fetch warehouse list via CLI."""
    try:
        result = core.run_command(
            ["databricks", "warehouses", "list", "-p", profile_name, "-o", "json"],
            check=True,
        )
        warehouses = json.loads(result.stdout)
        warehouses.sort(key=lambda w: (0 if w.get("state") == "RUNNING" else 1, w.get("name", "")))
        return warehouses
    except Exception:
        return []


def _list_vs_endpoints(token: str, host: str) -> list[dict]:
    """Fetch VS endpoints via REST API."""
    data = core.api_get("/api/2.0/vector-search/endpoints", token, host)
    endpoints = data.get("endpoints", [])
    state_order = {"ONLINE": 0, "PROVISIONING": 1}
    endpoints.sort(key=lambda e: (
        state_order.get(e.get("endpoint_status", {}).get("state", ""), 9),
        e.get("name", ""),
    ))
    return endpoints


# ─────────────────────────────────────────────────────────────────────
# Page 1: Language + Auth
# ─────────────────────────────────────────────────────────────────────

def page_language_auth():
    st.header(_t("1. 言語・認証設定", "1. Language & Authentication"))

    # Language
    lang_options = ["日本語", "English"]
    lang_idx = 0 if st.session_state.lang == "ja" else 1
    selected = st.radio(_t("言語", "Language"), lang_options, index=lang_idx,
                        key="lang_radio", horizontal=True)
    new_lang = "ja" if selected == "日本語" else "en"
    if new_lang != st.session_state.lang:
        st.session_state.lang = new_lang
        core.set_language(new_lang)
        st.rerun()

    st.divider()

    # Profile selector
    profiles = core.get_databricks_profiles()
    profile_names = [p["name"] for p in profiles]

    if not profile_names:
        st.warning(_t("Databricks プロファイルが見つかりません。先に `databricks auth login` を実行してください。",
                       "No Databricks profiles found. Please run `databricks auth login` first."))
        return

    default_idx = 0
    if st.session_state.profile_name in profile_names:
        default_idx = profile_names.index(st.session_state.profile_name)

    selected_profile = st.selectbox(
        _t("Databricks CLI プロファイル", "Databricks CLI Profile"),
        profile_names,
        index=default_idx,
        key="profile_select",
    )

    connect_clicked = st.button(_t("接続", "Connect"), type="primary", key="connect_btn")

    if connect_clicked:
        with st.spinner(_t("プロファイルを検証中...", "Validating profile...")):
            if core.validate_profile(selected_profile):
                st.session_state.profile_name = selected_profile
                st.session_state.host = core.get_databricks_host(selected_profile)
                try:
                    st.session_state.username = core.get_databricks_username(selected_profile)
                except SystemExit:
                    st.error(_t("ユーザー名の取得に失敗しました。", "Failed to get username."))
                    return
                try:
                    st.session_state.token = core.get_auth_token(selected_profile)
                except Exception:
                    st.error(_t("トークンの取得に失敗しました。", "Failed to get auth token."))
                    return
                st.session_state.auth_ok = True
            else:
                st.session_state.auth_ok = False
                st.error(_t(
                    f"プロファイル '{selected_profile}' の認証に失敗しました。`databricks auth login --profile {selected_profile}` を実行してください。",
                    f"Profile '{selected_profile}' is not authenticated. Run `databricks auth login --profile {selected_profile}`."))
                return

    if st.session_state.auth_ok:
        st.success(_t(
            f"認証OK: {st.session_state.username} @ {st.session_state.host}",
            f"Authenticated: {st.session_state.username} @ {st.session_state.host}"))

        # Pre-fill defaults
        if not st.session_state.catalog:
            st.session_state.catalog = st.session_state.username.split("@")[0].replace(".", "_")
        if not st.session_state.schema:
            st.session_state.schema = "retail_agent"

        # Check lakebase
        st.session_state.lakebase_required = core.check_lakebase_required()

        _nav_buttons(1, can_back=False)


# ─────────────────────────────────────────────────────────────────────
# Page 2: Catalog, Schema, Warehouse, VS Endpoint
# ─────────────────────────────────────────────────────────────────────

def page_workspace_config():
    st.header(_t("2. ワークスペース設定", "2. Workspace Configuration"))

    # Catalog
    env_catalog = core.get_env_value("CATALOG") or st.session_state.catalog
    st.session_state.catalog = st.text_input(
        _t("カタログ名", "Catalog name"),
        value=env_catalog,
        key="catalog_input",
    )

    # Schema
    env_schema = core.get_env_value("SCHEMA") or st.session_state.schema
    st.session_state.schema = st.text_input(
        _t("スキーマ名", "Schema name"),
        value=env_schema,
        key="schema_input",
    )

    st.divider()

    # Warehouse
    st.subheader(_t("SQL ウェアハウス", "SQL Warehouse"))
    warehouses = _list_warehouses(st.session_state.profile_name)
    if warehouses:
        wh_labels = [
            f"{w.get('name', '?')} ({w.get('id', '?')}) [{w.get('state', '?')}]"
            for w in warehouses
        ]
        default_wh = 0
        if st.session_state.warehouse_id:
            for i, w in enumerate(warehouses):
                if w.get("id") == st.session_state.warehouse_id:
                    default_wh = i
                    break
        selected_wh = st.selectbox(
            _t("ウェアハウスを選択", "Select warehouse"),
            wh_labels,
            index=default_wh,
            key="wh_select",
        )
        idx = wh_labels.index(selected_wh)
        st.session_state.warehouse_id = warehouses[idx]["id"]
        st.session_state.warehouse_name = warehouses[idx].get("name", "")
    else:
        st.warning(_t("ウェアハウスが見つかりません。", "No warehouses found."))
        st.session_state.warehouse_id = st.text_input(
            _t("ウェアハウス ID (手動入力)", "Warehouse ID (manual)"),
            value=st.session_state.warehouse_id,
        )

    st.divider()

    # VS Endpoint
    st.subheader(_t("Vector Search エンドポイント", "Vector Search Endpoint"))
    endpoints = _list_vs_endpoints(st.session_state.token, st.session_state.host)
    if endpoints:
        ep_labels = [
            f"{e.get('name', '?')} [{e.get('endpoint_status', {}).get('state', '?')}]"
            for e in endpoints
        ]
        default_ep = 0
        if st.session_state.vs_endpoint:
            for i, e in enumerate(endpoints):
                if e.get("name") == st.session_state.vs_endpoint:
                    default_ep = i
                    break
        selected_ep = st.selectbox(
            _t("エンドポイントを選択", "Select endpoint"),
            ep_labels,
            index=default_ep,
            key="ep_select",
        )
        idx = ep_labels.index(selected_ep)
        st.session_state.vs_endpoint = endpoints[idx]["name"]
    else:
        st.warning(_t("Vector Search エンドポイントが見つかりません。", "No VS endpoints found."))
        st.session_state.vs_endpoint = st.text_input(
            _t("エンドポイント名 (手動入力)", "Endpoint name (manual)"),
            value=st.session_state.vs_endpoint,
        )

    _nav_buttons(2)


# ─────────────────────────────────────────────────────────────────────
# Page 3: Lakebase Setup
# ─────────────────────────────────────────────────────────────────────

def page_lakebase():
    st.header(_t("3. Lakebase セットアップ", "3. Lakebase Setup"))

    if not st.session_state.lakebase_required:
        st.info(_t("このテンプレートでは Lakebase は不要です。スキップして次へ進めます。",
                    "Lakebase is not required for this template. You can skip to the next step."))
        _nav_buttons(3)
        return

    mode = st.radio(
        _t("Lakebase インスタンス", "Lakebase instance"),
        [_t("新規作成", "Create new"), _t("既存を使用", "Use existing")],
        index=0 if st.session_state.lakebase_mode == "new" else 1,
        key="lb_mode_radio",
        horizontal=True,
    )
    st.session_state.lakebase_mode = "new" if mode == _t("新規作成", "Create new") else "existing"

    if st.session_state.lakebase_mode == "new":
        project_name = st.text_input(
            _t("プロジェクト名", "Project name"),
            value=st.session_state.lakebase_project,
            key="lb_project_new",
        )
        st.session_state.lakebase_project = project_name

        if st.button(_t("作成", "Create"), key="lb_create_btn", type="primary"):
            if not project_name:
                st.error(_t("プロジェクト名を入力してください。", "Please enter a project name."))
            else:
                with st.spinner(_t("Lakebase プロジェクトを作成中...", "Creating Lakebase project...")):
                    try:
                        w = core.get_workspace_client(st.session_state.profile_name)
                        if not w:
                            st.error(_t("Databricks に接続できません。", "Cannot connect to Databricks."))
                            return
                        from databricks.sdk.service.postgres import Branch, BranchSpec, Project, ProjectSpec
                        project_op = w.postgres.create_project(
                            project=Project(spec=ProjectSpec(display_name=project_name)),
                            project_id=project_name,
                        )
                        project = project_op.wait()
                        project_short = project.name.removeprefix("projects/")

                        branch_id = f"{project_name}-branch"
                        branch_op = w.postgres.create_branch(
                            parent=project.name,
                            branch=Branch(spec=BranchSpec(no_expiry=True)),
                            branch_id=branch_id,
                        )
                        branch = branch_op.wait()
                        branch_name = (
                            branch.name.split("/branches/")[-1]
                            if "/branches/" in branch.name
                            else branch_id
                        )
                        st.session_state.lakebase_project = project_short
                        st.session_state.lakebase_branch = branch_name
                        st.success(_t(
                            f"プロジェクト作成完了: {project_short} / ブランチ: {branch_name}",
                            f"Created project: {project_short} / branch: {branch_name}"))
                    except Exception as e:
                        st.error(_t(f"作成に失敗: {str(e)[:200]}", f"Creation failed: {str(e)[:200]}"))
    else:
        st.session_state.lakebase_project = st.text_input(
            _t("プロジェクト名", "Project name"),
            value=st.session_state.lakebase_project,
            key="lb_project_existing",
        )
        st.session_state.lakebase_branch = st.text_input(
            _t("ブランチ名", "Branch name"),
            value=st.session_state.lakebase_branch,
            key="lb_branch_existing",
        )

    # Validation status
    if st.session_state.lakebase_project and st.session_state.lakebase_branch:
        if st.button(_t("検証", "Validate"), key="lb_validate_btn"):
            with st.spinner(_t("検証中...", "Validating...")):
                info = core.validate_lakebase_autoscaling(
                    st.session_state.profile_name,
                    st.session_state.lakebase_project,
                    st.session_state.lakebase_branch,
                )
                if info:
                    st.session_state.lakebase_config = {
                        "type": "autoscaling",
                        "project": st.session_state.lakebase_project,
                        "branch": st.session_state.lakebase_branch,
                        "database_id": info.get("database_id", ""),
                    }
                    st.success(_t("Lakebase 検証OK", "Lakebase validated"))
                else:
                    st.error(_t("検証に失敗しました。", "Validation failed."))

    _nav_buttons(3)


# ─────────────────────────────────────────────────────────────────────
# Page 4: MLflow Experiments
# ─────────────────────────────────────────────────────────────────────

def page_mlflow():
    st.header(_t("4. MLflow Experiments", "4. MLflow Experiments"))

    mode = st.radio(
        _t("Experiment の設定", "Experiment setup"),
        [_t("新規作成", "Create new"), _t("既存の ID を入力", "Enter existing IDs")],
        index=0 if st.session_state.mlflow_mode == "new" else 1,
        key="mlflow_mode_radio",
        horizontal=True,
    )
    st.session_state.mlflow_mode = "new" if mode == _t("新規作成", "Create new") else "existing"

    if st.session_state.mlflow_mode == "new":
        default_base = f"/Users/{st.session_state.username}/freshmart-agent"
        st.session_state.mlflow_base_name = st.text_input(
            _t("ベース名", "Base name"),
            value=st.session_state.mlflow_base_name or default_base,
            key="mlflow_base",
        )
        st.caption(_t(
            "モニタリング用: {name}-monitoring / 評価用: {name}-evaluation が作成されます",
            "Will create: {name}-monitoring / {name}-evaluation").format(
                name=st.session_state.mlflow_base_name))
    else:
        st.session_state.monitoring_id = st.text_input(
            _t("モニタリング Experiment ID", "Monitoring Experiment ID"),
            value=st.session_state.monitoring_id,
            key="mon_id_input",
        )
        st.session_state.eval_id = st.text_input(
            _t("評価 Experiment ID", "Evaluation Experiment ID"),
            value=st.session_state.eval_id,
            key="eval_id_input",
        )

        if st.session_state.monitoring_id and st.session_state.eval_id:
            if st.button(_t("検証", "Verify"), key="mlflow_verify"):
                with st.spinner(_t("検証中...", "Verifying...")):
                    m_name, m_id = core._verify_experiment(st.session_state.profile_name, st.session_state.monitoring_id)
                    e_name, e_id = core._verify_experiment(st.session_state.profile_name, st.session_state.eval_id)
                    if m_name and e_name:
                        st.session_state.monitoring_name = m_name
                        st.session_state.eval_name = e_name
                        st.success(_t(
                            f"モニタリング: {m_name} / 評価: {e_name}",
                            f"Monitoring: {m_name} / Evaluation: {e_name}"))

                        # Check for Delta Table trace destination
                        try:
                            exp_result = core.run_command(
                                ["databricks", "experiments", "get-experiment",
                                 st.session_state.monitoring_id,
                                 "-p", st.session_state.profile_name, "-o", "json"],
                                check=False,
                            )
                            if exp_result.returncode == 0:
                                exp_data = json.loads(exp_result.stdout)
                                exp_tags = exp_data.get("experiment", exp_data).get("tags", [])
                                for tag in exp_tags:
                                    if tag.get("key") == "mlflow.experiment.databricksTraceDestinationPath":
                                        st.session_state.existing_trace_dest = tag.get("value", "")
                                        break
                            if st.session_state.existing_trace_dest:
                                st.info(_t(
                                    f"Delta Table トレース送信先を検出: {st.session_state.existing_trace_dest}",
                                    f"Delta Table trace destination detected: {st.session_state.existing_trace_dest}"))
                        except Exception:
                            pass
                    else:
                        if not m_name:
                            st.error(_t(
                                f"モニタリング Experiment ID '{st.session_state.monitoring_id}' が見つかりません。",
                                f"Monitoring Experiment ID '{st.session_state.monitoring_id}' not found."))
                        if not e_name:
                            st.error(_t(
                                f"評価 Experiment ID '{st.session_state.eval_id}' が見つかりません。",
                                f"Evaluation Experiment ID '{st.session_state.eval_id}' not found."))

    _nav_buttons(4)


# ─────────────────────────────────────────────────────────────────────
# Page 5: Options
# ─────────────────────────────────────────────────────────────────────

def page_options():
    st.header(_t("5. オプション設定", "5. Options"))

    # Trace destination
    st.subheader(_t("トレース送信先", "Trace Destination"))

    if st.session_state.existing_trace_dest:
        st.info(_t(
            f"既存の Experiment から Delta Table 送信先を検出済み: {st.session_state.existing_trace_dest}",
            f"Delta Table destination detected from existing Experiment: {st.session_state.existing_trace_dest}"))
        st.session_state.trace_dest_mode = "delta"
        st.session_state.trace_dest_schema = st.session_state.existing_trace_dest
    else:
        trace_mode = st.radio(
            _t("送信先", "Destination"),
            [
                _t("MLflow Experiment (デフォルト)", "MLflow Experiment (default)"),
                _t("Unity Catalog Delta Table", "Unity Catalog Delta Table"),
            ],
            index=0 if st.session_state.trace_dest_mode == "mlflow" else 1,
            key="trace_dest_radio",
        )
        st.session_state.trace_dest_mode = "mlflow" if "MLflow" in trace_mode else "delta"

        if st.session_state.trace_dest_mode == "delta":
            default_schema = f"{st.session_state.catalog}.{st.session_state.schema}"
            st.session_state.trace_dest_schema = st.text_input(
                _t("送信先スキーマ", "Destination schema"),
                value=st.session_state.trace_dest_schema or default_schema,
                key="trace_schema_input",
            )

    st.divider()

    # Prompt Registry
    st.subheader(_t("Prompt Registry", "Prompt Registry"))
    st.session_state.use_prompt_registry = st.checkbox(
        _t("Unity Catalog Prompt Registry を使用（バージョン管理・A/Bテスト）",
           "Use Unity Catalog Prompt Registry (version control, A/B testing)"),
        value=st.session_state.use_prompt_registry,
        key="prompt_reg_check",
    )

    st.divider()

    # Summary
    st.subheader(_t("設定サマリー", "Configuration Summary"))

    summary_data = {
        _t("プロファイル", "Profile"): st.session_state.profile_name,
        _t("ワークスペース", "Workspace"): st.session_state.host,
        _t("ユーザー", "User"): st.session_state.username,
        _t("カタログ", "Catalog"): st.session_state.catalog,
        _t("スキーマ", "Schema"): st.session_state.schema,
        _t("ウェアハウス", "Warehouse"): f"{st.session_state.warehouse_name} ({st.session_state.warehouse_id})",
        _t("VS エンドポイント", "VS Endpoint"): st.session_state.vs_endpoint,
        _t("MLflow", "MLflow"): (
            _t("新規作成", "Create new") if st.session_state.mlflow_mode == "new"
            else f"ID: {st.session_state.monitoring_id} / {st.session_state.eval_id}"
        ),
        _t("トレース送信先", "Trace Destination"): (
            "MLflow Experiment" if st.session_state.trace_dest_mode == "mlflow"
            else f"Delta Table ({st.session_state.trace_dest_schema})"
        ),
        _t("Prompt Registry", "Prompt Registry"): (
            _t("使用する", "Yes") if st.session_state.use_prompt_registry
            else _t("使用しない", "No")
        ),
    }
    if st.session_state.lakebase_required:
        summary_data[_t("Lakebase", "Lakebase")] = (
            f"{st.session_state.lakebase_project} / {st.session_state.lakebase_branch}"
            if st.session_state.lakebase_project else _t("未設定", "Not configured")
        )

    for k, v in summary_data.items():
        st.text(f"{k}: {v}")

    _nav_buttons(5)


# ─────────────────────────────────────────────────────────────────────
# Page 6: Execute
# ─────────────────────────────────────────────────────────────────────

def page_execute():
    st.header(_t("6. セットアップ実行", "6. Execute Setup"))

    if st.session_state.setup_complete:
        st.success(_t("セットアップは完了済みです。", "Setup is already complete."))
        if st.button(_t("結果を表示 →", "View results →"), type="primary"):
            st.session_state.page = 7
            st.rerun()
        return

    if not st.session_state.setup_started:
        st.warning(_t(
            "以下のリソースが作成されます。実行後は元に戻せません。",
            "The following resources will be created. This cannot be undone."))
        st.markdown(f"""
- **{_t("カタログ・スキーマ", "Catalog & Schema")}**: `{st.session_state.catalog}.{st.session_state.schema}`
- **{_t("構造化データ", "Structured data")}**: 6 {_t("テーブル", "tables")}
- **{_t("Vector Search インデックス", "Vector Search index")}**
- **{_t("Genie Space", "Genie Space")}**
- **{_t("MLflow Experiments", "MLflow Experiments")}**
""")

        if st.button(_t("セットアップを実行", "Run Setup"), type="primary", key="run_setup"):
            st.session_state.setup_started = True
            st.rerun()

        st.button(_t("← 戻る", "← Back"), key="back_6", on_click=lambda: _go_back(5))
        return

    # ── Run the actual setup ──
    _run_setup()


def _go_back(page: int):
    st.session_state.page = page


def _run_setup():
    """Execute all setup steps with live progress."""
    token = st.session_state.token
    host = st.session_state.host
    profile_name = st.session_state.profile_name
    username = st.session_state.username
    catalog = st.session_state.catalog
    schema = st.session_state.schema
    warehouse_id = st.session_state.warehouse_id
    vs_endpoint = st.session_state.vs_endpoint
    log = st.session_state.setup_log

    with st.status(_t("セットアップ実行中...", "Running setup..."), expanded=True) as status:
        try:
            # .env setup
            st.write(_t("設定ファイルをセットアップ中...", "Setting up config files..."))
            core.setup_env_file()
            core.update_env_file("DATABRICKS_CONFIG_PROFILE", profile_name)
            core.update_env_file("MLFLOW_TRACKING_URI", f'"databricks://{profile_name}"')
            core.update_env_file("DATABRICKS_HOST", host)
            log.append(_t("✓ .env 作成完了", "✓ .env created"))
            st.write(log[-1])

            # Catalog & Schema
            st.write(_t("カタログ・スキーマを作成中...", "Creating catalog & schema..."))
            core.create_catalog_schema(token, host, warehouse_id, catalog, schema)
            log.append(_t("✓ カタログ・スキーマ作成完了", "✓ Catalog & schema created"))
            st.write(log[-1])

            # Data generation
            st.write(_t("データを生成中（5〜10分かかる場合があります）...",
                         "Generating data (may take 5-10 minutes)..."))
            core.generate_data(profile_name, warehouse_id, catalog, schema,
                               token=token, host=host)
            log.append(_t("✓ データ生成完了", "✓ Data generated"))
            st.write(log[-1])

            # CDF
            st.write(_t("Change Data Feed を有効化中...", "Enabling Change Data Feed..."))
            core.enable_cdf(token, host, warehouse_id, catalog, schema)
            log.append(_t("✓ CDF 有効化完了", "✓ CDF enabled"))
            st.write(log[-1])

            # Vector Search Index
            vs_index = ""
            if vs_endpoint:
                st.write(_t("Vector Search インデックスを作成中...",
                             "Creating Vector Search index..."))
                vs_index = core.create_vector_search_index(
                    token, host, catalog, schema, vs_endpoint)
                log.append(_t(f"✓ VS インデックス: {vs_index}", f"✓ VS index: {vs_index}"))
                st.write(log[-1])
            else:
                vs_index = f"{catalog}.{schema}.policy_docs_index"
                log.append(_t("⚠ VS エンドポイント未指定（インデックスは手動作成が必要）",
                               "⚠ VS endpoint not specified (manual index creation needed)"))
                st.write(log[-1])
            st.session_state.vs_index = vs_index

            # Genie Space
            st.write(_t("Genie Space を作成中...", "Creating Genie Space..."))
            tables = ["customers", "products", "stores", "transactions",
                      "transaction_items", "payment_history"]
            serialized = core._build_serialized_space(catalog, schema, tables)
            body = {
                "title": "フレッシュマート 小売データ",
                "description": "フレッシュマートの小売データに対する自然言語クエリ。",
                "warehouse_id": warehouse_id,
                "serialized_space": serialized,
            }
            result = core.api_post("/api/2.0/genie/spaces", token, host, body)
            genie_space_id = result.get("space_id", "")
            if not genie_space_id and "error" in result:
                log.append(_t(f"⚠ Genie Space 自動作成に失敗: {str(result['error'])[:100]}",
                               f"⚠ Genie Space auto-creation failed: {str(result['error'])[:100]}"))
                st.write(log[-1])
            else:
                st.session_state.genie_space_id = genie_space_id
                log.append(_t(f"✓ Genie Space 作成完了 (ID: {genie_space_id})",
                               f"✓ Genie Space created (ID: {genie_space_id})"))
                st.write(log[-1])

            # Lakebase
            lakebase_config = None
            if st.session_state.lakebase_required and st.session_state.lakebase_project:
                st.write(_t("Lakebase を設定中...", "Setting up Lakebase..."))
                branch_info = core.validate_lakebase_autoscaling(
                    profile_name,
                    st.session_state.lakebase_project,
                    st.session_state.lakebase_branch,
                )
                if branch_info:
                    lakebase_config = {
                        "type": "autoscaling",
                        "project": st.session_state.lakebase_project,
                        "branch": st.session_state.lakebase_branch,
                        "database_id": branch_info.get("database_id", ""),
                    }
                    st.session_state.lakebase_config = lakebase_config
                    core.update_env_file("LAKEBASE_AUTOSCALING_PROJECT", lakebase_config["project"])
                    core.update_env_file("LAKEBASE_AUTOSCALING_BRANCH", lakebase_config["branch"])
                    pg_host = branch_info.get("host", "")
                    if pg_host:
                        core.update_env_file("PGHOST", pg_host)
                    core.update_env_file("PGUSER", username)
                    core.update_env_file("PGDATABASE", "databricks_postgres")
                    core.update_databricks_yml_lakebase(lakebase_config)
                    core.update_app_yaml_lakebase(lakebase_config)
                    log.append(_t("✓ Lakebase 設定完了", "✓ Lakebase configured"))
                    st.write(log[-1])
                else:
                    log.append(_t("⚠ Lakebase 検証に失敗", "⚠ Lakebase validation failed"))
                    st.write(log[-1])

            # MLflow Experiments
            st.write(_t("MLflow Experiments を設定中...", "Setting up MLflow Experiments..."))
            if st.session_state.mlflow_mode == "new":
                base = st.session_state.mlflow_base_name or f"/Users/{username}/freshmart-agent"
                m_name, m_id = core._create_single_experiment(profile_name, f"{base}-monitoring")
                e_name, e_id = core._create_single_experiment(profile_name, f"{base}-evaluation")
                st.session_state.monitoring_name = m_name
                st.session_state.monitoring_id = m_id
                st.session_state.eval_name = e_name
                st.session_state.eval_id = e_id
            # else: IDs already in session_state from page 4

            monitoring_id = st.session_state.monitoring_id
            eval_id = st.session_state.eval_id
            log.append(_t(f"✓ MLflow Experiments: {monitoring_id} / {eval_id}",
                           f"✓ MLflow Experiments: {monitoring_id} / {eval_id}"))
            st.write(log[-1])

            # .env updates
            st.write(_t("環境変数を更新中...", "Updating environment variables..."))
            core.update_env_file("MLFLOW_EXPERIMENT_ID", monitoring_id)
            core.update_env_file("MLFLOW_EVAL_EXPERIMENT_ID", eval_id)
            core.update_env_file("GENIE_SPACE_ID", st.session_state.genie_space_id)
            core.update_env_file("VECTOR_SEARCH_INDEX", vs_index)
            core.update_databricks_yml_experiment(monitoring_id)
            core.update_databricks_yml_resources(st.session_state.genie_space_id, vs_index)

            # Tracing
            tracing_dest = ""
            if st.session_state.trace_dest_mode == "delta":
                tracing_dest = st.session_state.trace_dest_schema
                if tracing_dest:
                    core.update_env_file("MLFLOW_TRACING_DESTINATION", tracing_dest)
                    core.update_env_file("MLFLOW_TRACING_SQL_WAREHOUSE_ID", warehouse_id)
                    core.append_env_to_app_yaml("MLFLOW_TRACING_DESTINATION", tracing_dest)
                    core.append_env_to_app_yaml("MLFLOW_TRACING_SQL_WAREHOUSE_ID", warehouse_id)
                    log.append(_t(f"✓ トレース送信先: {tracing_dest}",
                                   f"✓ Trace destination: {tracing_dest}"))
                    st.write(log[-1])

                    # Run trace table setup if new (not existing)
                    if not st.session_state.existing_trace_dest and "." in tracing_dest:
                        st.write(_t("トレーステーブルを作成中...", "Creating trace tables..."))
                        _cat, _sch = tracing_dest.split(".", 1)
                        ok = core.run_trace_setup_on_databricks(
                            profile_name=profile_name,
                            username=username,
                            catalog=_cat,
                            schema=_sch,
                            warehouse_id=warehouse_id,
                            experiment_id=monitoring_id,
                        )
                        if ok:
                            log.append(_t("✓ トレーステーブル作成完了",
                                           "✓ Trace tables created"))
                        else:
                            log.append(_t("⚠ トレーステーブル自動作成に失敗",
                                           "⚠ Trace table auto-creation failed"))
                        st.write(log[-1])

            # Prompt Registry
            if st.session_state.use_prompt_registry:
                prompt_name = f"{catalog}.{schema}.freshmart_system_prompt"
                st.write(_t(f"プロンプト登録中: {prompt_name}",
                             f"Registering prompt: {prompt_name}"))
                try:
                    result = subprocess.run(
                        ["uv", "run", "register-prompt", "--name", prompt_name],
                        capture_output=True, text=True,
                    )
                    if result.returncode == 0:
                        core.update_env_file("PROMPT_REGISTRY_NAME", prompt_name)
                        core.append_env_to_app_yaml("PROMPT_REGISTRY_NAME", prompt_name)
                        log.append(_t(f"✓ Prompt Registry: {prompt_name}",
                                       f"✓ Prompt Registry: {prompt_name}"))
                    else:
                        log.append(_t("⚠ プロンプト登録に失敗（ハードコード版を使用）",
                                       "⚠ Prompt registration failed (using hardcoded)"))
                except Exception:
                    log.append(_t("⚠ プロンプト登録に失敗", "⚠ Prompt registration failed"))
                st.write(log[-1])

            # workshop_setup.py
            setup_notebook = Path("workshop_setup.py")
            if setup_notebook.exists():
                content = setup_notebook.read_text()
                replacements = {
                    '"<CATALOG>"': f'"{catalog}"',
                    '"<SCHEMA>"': f'"{schema}"',
                    '"<WAREHOUSE-ID>"': f'"{warehouse_id}"',
                    '"<MONITORING-EXPERIMENT-ID>"': f'"{monitoring_id}"',
                    '"<EVAL-EXPERIMENT-ID>"': f'"{eval_id}"',
                    '"<GENIE-SPACE-ID>"': f'"{st.session_state.genie_space_id}"',
                    '"<LAKEBASE-PROJECT>"': (
                        f'"{lakebase_config["project"]}"' if lakebase_config
                        else '"<LAKEBASE-PROJECT>"'
                    ),
                    '"<LAKEBASE-BRANCH>"': (
                        f'"{lakebase_config["branch"]}"' if lakebase_config
                        else '"<LAKEBASE-BRANCH>"'
                    ),
                }
                for old, new in replacements.items():
                    content = content.replace(old, new)
                setup_notebook.write_text(content)
                log.append(_t("✓ workshop_setup.py 更新完了",
                               "✓ workshop_setup.py updated"))
                st.write(log[-1])

            # Dependencies
            st.write(_t("依存関係をインストール中...", "Installing dependencies..."))
            core.install_dependencies()
            log.append(_t("✓ 依存関係インストール完了", "✓ Dependencies installed"))
            st.write(log[-1])

            st.session_state.setup_complete = True
            status.update(label=_t("セットアップ完了!", "Setup complete!"), state="complete")

        except SystemExit:
            status.update(label=_t("セットアップに失敗しました", "Setup failed"), state="error")
            st.error(_t("セットアップ中にエラーが発生しました。ログを確認してください。",
                         "An error occurred during setup. Please check the log."))
        except Exception as e:
            status.update(label=_t("セットアップに失敗しました", "Setup failed"), state="error")
            st.error(f"{_t('エラー', 'Error')}: {e}")

    if st.session_state.setup_complete:
        if st.button(_t("結果を表示 →", "View results →"), type="primary", key="go_results"):
            st.session_state.page = 7
            st.rerun()


# ─────────────────────────────────────────────────────────────────────
# Page 7: Complete
# ─────────────────────────────────────────────────────────────────────

def page_complete():
    st.header(_t("セットアップ完了!", "Setup Complete!"))

    st.balloons()

    # Summary
    monitoring_id = st.session_state.monitoring_id
    eval_id = st.session_state.eval_id
    catalog = st.session_state.catalog
    schema = st.session_state.schema
    vs_index = st.session_state.vs_index
    genie_space_id = st.session_state.genie_space_id
    host = st.session_state.host
    vs_endpoint = st.session_state.vs_endpoint
    lakebase_config = st.session_state.lakebase_config

    st.subheader(_t("作成されたリソース", "Created Resources"))
    resources = f"""
| {_t("リソース", "Resource")} | {_t("値", "Value")} |
|---|---|
| {_t("カタログ", "Catalog")} | `{catalog}` |
| {_t("スキーマ", "Schema")} | `{catalog}.{schema}` |
| Vector Search | `{vs_index}` |
| Genie Space ID | `{genie_space_id}` |
| {_t("モニタリング Experiment", "Monitoring Experiment")} | `{monitoring_id}` |
| {_t("評価 Experiment", "Evaluation Experiment")} | `{eval_id}` |
"""
    if lakebase_config:
        resources += f"| Lakebase | `{lakebase_config['project']}` (branch: `{lakebase_config['branch']}`) |\n"

    if st.session_state.trace_dest_mode == "delta" and st.session_state.trace_dest_schema:
        resources += f"| {_t('トレース送信先', 'Trace Dest')} | `{st.session_state.trace_dest_schema}` |\n"

    st.markdown(resources)

    if host and monitoring_id:
        st.markdown(f"[{_t('Experiment を開く', 'Open Experiment')}]({host}/ml/experiments/{monitoring_id})")

    st.divider()

    # Team sharing
    st.subheader(_t("チームメンバーへの共有情報", "Team Sharing Info"))

    share_text_lines = [
        f"{_t('カタログ名', 'Catalog')}: {catalog}",
        f"{_t('スキーマ名', 'Schema')}: {schema}",
        f"{_t('VS エンドポイント', 'VS Endpoint')}: {vs_endpoint}",
        f"Genie Space ID: {genie_space_id}",
    ]
    if lakebase_config:
        share_text_lines.append(f"{_t('Lakebase プロジェクト', 'Lakebase project')}: {lakebase_config['project']}")
        share_text_lines.append(f"{_t('Lakebase ブランチ', 'Lakebase branch')}: {lakebase_config['branch']}")
    share_text_lines.append(f"{_t('モニタリング Exp ID', 'Monitoring Exp ID')}: {monitoring_id}")
    share_text_lines.append(f"{_t('評価 Exp ID', 'Evaluation Exp ID')}: {eval_id}")

    share_text = "\n".join(share_text_lines)

    st.code(share_text, language=None)

    st.caption(_t(
        "権限付与: `uv run grant-team-access member1@company.com member2@company.com`",
        "Grant access: `uv run grant-team-access member1@company.com member2@company.com`"))

    st.divider()

    # Next steps
    st.subheader(_t("次のステップ", "Next Steps"))
    st.code("uv run start-app", language="bash")
    st.caption(_t("エージェントサーバーとチャット UI を起動します。",
                   "Starts the agent server and chat UI."))


# ─────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────

PAGE_MAP = {
    1: page_language_auth,
    2: page_workspace_config,
    3: page_lakebase,
    4: page_mlflow,
    5: page_options,
    6: page_execute,
    7: page_complete,
}

# Page config
st.set_page_config(
    page_title="FreshMart Agent - Quickstart",
    page_icon="🚀",
    layout="centered",
)

# Sidebar progress
with st.sidebar:
    st.title("FreshMart Agent")
    st.caption("Quickstart Setup")
    st.divider()

    page_labels = {
        1: _t("1. 言語・認証", "1. Language & Auth"),
        2: _t("2. ワークスペース", "2. Workspace"),
        3: _t("3. Lakebase", "3. Lakebase"),
        4: _t("4. MLflow", "4. MLflow"),
        5: _t("5. オプション", "5. Options"),
        6: _t("6. 実行", "6. Execute"),
        7: _t("7. 完了", "7. Complete"),
    }

    current = st.session_state.page
    for num, label in page_labels.items():
        if num == current:
            st.markdown(f"**→ {label}**")
        elif num < current:
            st.markdown(f"✓ {label}")
        else:
            st.markdown(f"  {label}")

# Render current page
page_fn = PAGE_MAP.get(st.session_state.page, page_language_auth)
page_fn()
