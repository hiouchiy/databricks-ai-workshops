"""L2: each page renders with the correct user-derived defaults on first visit.

These tests jump directly to a given page (auth state pre-populated by the
`app` fixture) and verify that the entry widgets show the deterministic
default values driven by the workspace username.
"""
from __future__ import annotations

import pytest

import scripts.quickstart_core as core
from .conftest import goto_page


# ── Page 3: Catalog ─────────────────────────────────────────────────────────

def test_catalog_default_is_user_derived_in_new_mode(app):
    goto_page(app, 2)
    # Switch to "new" mode so the entry is exposed
    app._catalog_mode_var.set("new")
    app._rebuild_catalog_fields()
    app.update()

    expected = core.compute_default_catalog_name(app.data["username"])
    assert app._catalog_entry.get() == expected
    assert expected.startswith("fm_handson_")
    assert app.data["catalog"] == expected


def test_catalog_existing_mode_lists_workspace_catalogs(app, mock_core):
    goto_page(app, 2)
    app._catalog_mode_var.set("existing")
    app._rebuild_catalog_fields()
    app.update()
    # The dropdown is populated from the (mocked) catalogs list
    assert app._catalogs_cache is not None
    # There should be at least one entry from DEFAULT_CATALOGS
    assert any("samples" in c for c in app._catalogs_cache)


# ── Page 4: Schema ──────────────────────────────────────────────────────────

def test_schema_default_is_ai_assistant_with_user_suffix(app):
    goto_page(app, 3)
    expected = core.compute_default_schema_name(app.data["username"])
    assert app._schema_entry.get() == expected
    assert expected.startswith("ai_assistant_")


# ── Page 5: SQL Warehouse ───────────────────────────────────────────────────

def test_warehouse_new_mode_default_is_user_derived(app):
    goto_page(app, 4)
    # Existing mode renders the dropdown by default — switch to new
    app._wh_mode_var.set("new")
    app._rebuild_wh_fields()
    app.update()

    expected = core.compute_default_warehouse_name(app.data["username"])
    assert app._wh_new_name_entry.get() == expected
    assert expected.startswith("fm-wh-")


def test_warehouse_existing_mode_populates_from_cache(app):
    goto_page(app, 4)
    # Default initial mode is "existing"; the dropdown should be present
    app.update()
    assert app._warehouses_cache is not None
    assert len(app._warehouses_cache) >= 1


# ── Page 6: Vector Search Endpoint ──────────────────────────────────────────

def test_vs_endpoint_new_mode_default_is_user_derived(app):
    goto_page(app, 5)
    app._ep_mode_var.set("new")
    app._rebuild_ep_fields()
    app.update()

    expected = core.compute_default_vs_endpoint_name(app.data["username"])
    assert app._ep_new_name_entry.get() == expected
    assert expected.startswith("fm-vs-")


# ── Page 8: Lakebase ────────────────────────────────────────────────────────

def test_lakebase_project_default_is_user_derived(app):
    # Lakebase only renders fields if `lakebase_required` is True.
    app.data["lakebase_required"] = True
    goto_page(app, 7)
    # Default mode is "new"
    expected = core.compute_default_lakebase_project_name(app.data["username"])
    assert app._lb_proj_entry.get() == expected
    assert expected.startswith("fm-lakebase-")


# ── Page 13: App name ───────────────────────────────────────────────────────

def test_app_name_default_is_user_derived(app):
    goto_page(app, 12)
    expected = core.compute_default_app_name(app.data["username"])
    assert app._app_name_entry.get() == expected
    assert expected.startswith("fm-agent-")
    assert len(expected) <= core.APP_NAME_MAX_LENGTH


# ── Defaults are within their respective length limits ─────────────────────

def test_all_defaults_pass_their_validators(app):
    u = app.data["username"]
    assert core.validate_uc_object_name(core.compute_default_catalog_name(u))[0]
    assert core.validate_uc_object_name(core.compute_default_schema_name(u))[0]
    assert core.validate_sql_warehouse_name(core.compute_default_warehouse_name(u))[0]
    assert core.validate_vs_endpoint_name(core.compute_default_vs_endpoint_name(u))[0]
    assert core.is_valid_lakebase_project_name(core.compute_default_lakebase_project_name(u))
    assert core.is_valid_app_name(core.compute_default_app_name(u))
