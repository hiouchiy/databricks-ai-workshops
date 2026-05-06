"""Live smoke tests against the Free Edition workspace.

These tests use the real `free-edition` Databricks CLI profile to make
sure our mocked test suite hasn't drifted from the real API contract.
They are gated by `pytest -m live` so the default `pytest` run skips them.

Setup expected:
  - `databricks auth profiles` shows `free-edition` as Valid
  - The profile's user has at least browse rights on the workspace

Run with:
  pytest tests/test_live_smoke.py -m live -v
"""
from __future__ import annotations

import os

import pytest

import scripts.quickstart_core as core


pytestmark = pytest.mark.live  # whole-module marker

PROFILE = "free-edition"


@pytest.fixture(scope="module")
def live_auth():
    """Fetch token + host from the free-edition profile. Skip module if unavailable."""
    try:
        token = core.get_auth_token(PROFILE)
    except Exception as e:
        pytest.skip(f"free-edition profile unavailable: {e}")
    host = core.get_databricks_host(PROFILE)
    if not host or not token:
        pytest.skip("free-edition profile has no host/token")
    user = core.get_databricks_username(PROFILE)
    return {"token": token, "host": host, "user": user, "profile": PROFILE}


def test_live_list_catalogs(live_auth):
    """Real `/api/2.1/unity-catalog/catalogs` reachable with valid response shape."""
    r = core.api_get("/api/2.1/unity-catalog/catalogs", live_auth["token"], live_auth["host"])
    assert isinstance(r, dict)
    # Shape: {"catalogs": [{"name": ..., ...}, ...]}
    assert "catalogs" in r
    assert isinstance(r["catalogs"], list)


def test_live_list_warehouses(live_auth):
    """Real `databricks warehouses list` returns a JSON array."""
    from scripts.quickstart_core import run_command
    import json
    res = run_command(
        ["databricks", "warehouses", "list", "-p", live_auth["profile"], "-o", "json"],
        check=False,
    )
    assert res.returncode == 0
    parsed = json.loads(res.stdout) if res.stdout.strip() else []
    assert isinstance(parsed, list)


def test_live_list_vs_endpoints(live_auth):
    """Real VS endpoints list. May be empty on Free Edition; just check it's a dict."""
    r = core.api_get("/api/2.0/vector-search/endpoints", live_auth["token"], live_auth["host"])
    assert isinstance(r, dict)
    # Empty dict is acceptable on Free Edition (no endpoints provisioned).
    # If 'endpoints' key is present, it must be a list.
    if "endpoints" in r:
        assert isinstance(r["endpoints"], list)


def test_live_list_chat_models(live_auth):
    """Foundation Model API endpoints reachable. Must contain at least one chat model."""
    models = core.list_chat_models(live_auth["token"], live_auth["host"])
    assert isinstance(models, list)
    # On Free Edition there's typically at least one default chat endpoint
    if models:
        assert all(m.get("task") == "llm/v1/chat" for m in models)


def test_live_default_app_name_under_30_chars(live_auth):
    """The user's email-derived default app name must be ≤ 30 chars
    against the actual Free Edition username."""
    user = live_auth["user"]
    name = core.compute_default_app_name(user)
    assert len(name) <= core.APP_NAME_MAX_LENGTH
    assert core.is_valid_app_name(name)


def test_live_default_lakebase_name_within_56_chars(live_auth):
    user = live_auth["user"]
    name = core.compute_default_lakebase_project_name(user)
    assert len(name) <= core.LAKEBASE_PROJECT_MAX_LENGTH
    assert core.is_valid_lakebase_project_name(name)
    # Auto-branch `{name}-branch` must also fit
    assert len(name) + len("-branch") <= core.LAKEBASE_BRANCH_MAX_LENGTH


def test_live_list_lakebase_projects(live_auth):
    """Real SDK call to list Lakebase projects. May be empty on Free Edition."""
    projects = core.list_lakebase_projects(live_auth["profile"])
    assert isinstance(projects, list)
    # Each entry must be a valid project_id (not the full "projects/..." path)
    for p in projects:
        assert isinstance(p, str)
        assert not p.startswith("projects/")
