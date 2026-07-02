"""Shared pytest fixtures for the GUI test suite.

Strategy:
- Heavy-mock external boundaries (`core.api_get`, `core.run_command`,
  `core.get_workspace_client`, etc.) with deterministic responses so the
  tests are fast and independent of any live workspace.
- Provide an `app` fixture that returns a `QuickstartWizard` instance with
  authentication already populated, so tests can jump straight to any
  page without going through the OAuth flow.

Live tests against Free Edition live in `tests/test_live_smoke.py` and
are gated by `pytest -m live`.
"""
from __future__ import annotations

import os
import sys
import sysconfig
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── tk init ─────────────────────────────────────────────────────────────────
# uv が管理する `python-build-standalone` は Tcl/Tk のスクリプトライブラリを
# Python の `lib/tcl8.6` に同梱しているが、ランタイムでは
# `.venv/lib/tcl8.6` 等を最初に探してしまうため init.tcl が見つからずクラッシュする。
# テスト実行前に環境変数で正しいパスを指す。
if "TCL_LIBRARY" not in os.environ:
    py_lib = Path(sysconfig.get_config_var("prefix") or sys.prefix) / "lib"
    # uv python の本体（.venv ではなく実体）
    real_lib = Path(sys.base_prefix) / "lib"
    for lib_root in (real_lib, py_lib):
        tcl_dir = lib_root / "tcl8.6"
        tk_dir = lib_root / "tk8.6"
        if (tcl_dir / "init.tcl").exists():
            os.environ["TCL_LIBRARY"] = str(tcl_dir)
            if tk_dir.exists():
                os.environ["TK_LIBRARY"] = str(tk_dir)
            break

# Make scripts/ importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


# ── Default workspace fixture (deterministic mock data) ──────────────────────

# A small but realistic set of workspace resources used by most tests.
DEFAULT_CATALOGS = [
    {"name": "samples"},
    {"name": "main"},
    {"name": "fm_handson_existing_user"},
]
DEFAULT_WAREHOUSES = [
    # Names match the validator's character set (alphanumeric + _ + -, no spaces)
    {"id": "wh-001", "name": "starter-warehouse", "state": "RUNNING"},
    {"id": "wh-002", "name": "shared-pro", "state": "STOPPED"},
]
DEFAULT_VS_ENDPOINTS = [
    {"name": "shared-vs-endpoint", "endpoint_status": {"state": "ONLINE"}},
]
DEFAULT_LLM_MODELS = [
    {"name": "databricks-claude-sonnet-4-6", "task": "llm/v1/chat", "state": {"ready": "READY"}},
    {"name": "databricks-claude-haiku-4-5", "task": "llm/v1/chat", "state": {"ready": "READY"}},
]
DEFAULT_GATEWAY_MODEL_SERVICES = [
    "system.ai.claude-sonnet-5",
    "system.ai.claude-opus-4-6",
    "system.ai.gpt-oss-120b",
]


@pytest.fixture
def mock_core(monkeypatch):
    """Patch every `core.*` function the GUI calls during page rendering.

    The returned object is a SimpleNamespace whose attributes are the
    individual MagicMocks, so a test can override responses by assigning to
    e.g. `mock_core.api_get.side_effect = lambda path, *a, **k: {...}`.
    """
    import scripts.quickstart_core as core

    mocks = {}

    # --- API GET dispatcher ---
    def _api_get(path: str, token: str = "", host: str = ""):
        if path == "/api/2.1/unity-catalog/catalogs":
            return {"catalogs": DEFAULT_CATALOGS}
        if path.startswith("/api/2.1/unity-catalog/catalogs/"):
            name = path.rsplit("/", 1)[-1]
            for c in DEFAULT_CATALOGS:
                if c["name"] == name:
                    return c
            return {"error": "404"}
        if path.startswith("/api/2.1/unity-catalog/schemas/"):
            return {"error": "404"}  # default: no schema exists
        if path == "/api/2.0/sql/warehouses":
            return {"warehouses": DEFAULT_WAREHOUSES}
        if path == "/api/2.0/vector-search/endpoints":
            return {"endpoints": DEFAULT_VS_ENDPOINTS}
        if path.startswith("/api/2.0/vector-search/endpoints/"):
            name = path.rsplit("/", 1)[-1]
            for ep in DEFAULT_VS_ENDPOINTS:
                if ep["name"] == name:
                    return ep
            return {"error": "404"}
        if path.startswith("/api/2.0/apps/"):
            return {"error": "404"}  # no app by that name by default
        if path.startswith("/api/2.0/serving-endpoints"):
            return {"endpoints": DEFAULT_LLM_MODELS}
        return {"error": f"unmocked path: {path}"}

    mocks["api_get"] = MagicMock(side_effect=_api_get)
    monkeypatch.setattr(core, "api_get", mocks["api_get"])

    # --- API POST dispatcher ---
    def _api_post(path: str, token: str = "", host: str = "", body=None):
        if path == "/api/2.0/sql/warehouses":
            return {"id": "wh-new-001", "name": (body or {}).get("name", "")}
        if path == "/api/2.0/vector-search/endpoints":
            return {"name": (body or {}).get("name", ""), "endpoint_status": {"state": "PROVISIONING"}}
        return {"error": f"unmocked POST {path}"}

    mocks["api_post"] = MagicMock(side_effect=_api_post)
    monkeypatch.setattr(core, "api_post", mocks["api_post"])

    # --- run_command (databricks CLI subprocess) ---
    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = "[]"  # empty list by default
    fake_result.stderr = ""
    mocks["run_command"] = MagicMock(return_value=fake_result)
    monkeypatch.setattr(core, "run_command", mocks["run_command"])

    # --- WorkspaceClient (Lakebase / SDK calls) ---
    fake_ws = MagicMock()
    fake_ws.postgres.get_project.side_effect = Exception("not found")  # default: project doesn't exist
    mocks["get_workspace_client"] = MagicMock(return_value=fake_ws)
    monkeypatch.setattr(core, "get_workspace_client", mocks["get_workspace_client"])
    mocks["workspace_client"] = fake_ws

    # --- list_lakebase_projects (Lakebase existing-mode dropdown) ---
    # Default: two existing projects so the dropdown branch renders.
    mocks["list_lakebase_projects"] = MagicMock(
        return_value=["fm-lakebase-existing-0501", "shared-team-lakebase"]
    )
    monkeypatch.setattr(core, "list_lakebase_projects", mocks["list_lakebase_projects"])

    # --- list_gateway_chat_model_services (LLM page, Unity AI Gateway) ---
    mocks["list_gateway_chat_model_services"] = MagicMock(return_value=DEFAULT_GATEWAY_MODEL_SERVICES)
    monkeypatch.setattr(
        core, "list_gateway_chat_model_services", mocks["list_gateway_chat_model_services"]
    )
    # --- check_ai_gateway_available (assume enabled in tests) ---
    mocks["check_ai_gateway_available"] = MagicMock(return_value=True)
    monkeypatch.setattr(core, "check_ai_gateway_available", mocks["check_ai_gateway_available"])

    # --- get_env_value (.env reader) ---
    mocks["get_env_value"] = MagicMock(return_value="")
    monkeypatch.setattr(core, "get_env_value", mocks["get_env_value"])

    # --- filter_usable_warehouses ---
    mocks["filter_usable_warehouses"] = MagicMock(return_value=[
        {**w, "_user_permission": "CAN_USE"} for w in DEFAULT_WAREHOUSES
    ])
    monkeypatch.setattr(core, "filter_usable_warehouses", mocks["filter_usable_warehouses"])

    # --- get_databricks_username / get_databricks_host (called from GUI auth) ---
    mocks["get_databricks_username"] = MagicMock(return_value="taro@example.com")
    monkeypatch.setattr(core, "get_databricks_username", mocks["get_databricks_username"])
    mocks["get_databricks_host"] = MagicMock(return_value="https://example.cloud.databricks.com")
    monkeypatch.setattr(core, "get_databricks_host", mocks["get_databricks_host"])

    # --- get_auth_token ---
    mocks["get_auth_token"] = MagicMock(return_value="fake-token")
    monkeypatch.setattr(core, "get_auth_token", mocks["get_auth_token"])

    return mocks


@pytest.fixture
def app(mock_core, monkeypatch):
    """Return a `QuickstartWizard` with authentication populated.

    Skip the OAuth login flow by directly setting `self.data` with valid
    profile/token/host/username so tests can call `app.show_page(N)` to
    jump to any page (>= 2 needs auth) and exercise it.

    Also stubs out `_run_setup` so navigation to page 14 (execute) does
    not spawn a background thread that calls live APIs and dirties
    pytest's thread-exception capture.
    """
    import scripts.quickstart_gui as gui

    # Force language to "ja" so we don't get prompted at startup.
    import scripts.quickstart_core as core
    core.set_language("ja")

    application = gui.QuickstartWizard()

    # Pre-populate auth state so non-auth pages can render.
    application.data["profile_name"] = "fake-profile"
    application.data["host"] = "https://example.cloud.databricks.com"
    application.data["username"] = "taro@example.com"
    application.data["token"] = "fake-token"
    application.data["auth_ok"] = True
    application.data["catalog"] = ""
    application.data["schema"] = ""
    application.data["mlflow_base_name"] = ""

    # Prevent the execute page from spawning a background setup thread.
    monkeypatch.setattr(application, "_run_setup", lambda: None)

    application.update()
    yield application
    try:
        application.destroy()
    except Exception:
        pass


def goto_page(app, n: int) -> None:
    """Navigate the wizard to page index `n` (0-indexed) and run update()."""
    app.show_page(n)
    app.update()
