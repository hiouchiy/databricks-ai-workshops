"""L4: validation rejection on Next + conflict-detection dialog Yes/No flow.

For each `_check_inputs(pg)` branch we:
  - assert valid input passes (returns True)
  - assert invalid input is rejected (returns False) AND surfaces an error
  - for "create new" pages, simulate a name conflict and verify the
    Yes/No dialog drives the right outcome (use existing vs stay)
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import scripts.quickstart_core as core
from .conftest import goto_page


# ── Helpers ─────────────────────────────────────────────────────────────────

@pytest.fixture
def silenced_error(app, monkeypatch):
    """Replace `_show_error` with a recording mock so tests can assert on
    the message without a real modal dialog blocking."""
    mock = MagicMock()
    monkeypatch.setattr(app, "_show_error", mock)
    return mock


@pytest.fixture
def yes_dialog(app, monkeypatch):
    """Force `_confirm_use_existing` to always return True (user says 'use existing')."""
    monkeypatch.setattr(app, "_confirm_use_existing", lambda *a, **kw: True)


@pytest.fixture
def no_dialog(app, monkeypatch):
    """Force `_confirm_use_existing` to always return False (user wants different name)."""
    monkeypatch.setattr(app, "_confirm_use_existing", lambda *a, **kw: False)


# ── Catalog (page index 2) ──────────────────────────────────────────────────

def test_catalog_valid_name_passes(app, silenced_error):
    goto_page(app, 2)
    app._catalog_mode_var.set("new")
    app._rebuild_catalog_fields()
    app.data["catalog"] = "fm_handson_test"
    app.data["_catalog_mode"] = "new"
    assert ((setattr(app, "current_page", 2) or app._validate_current_page())) is True
    silenced_error.assert_not_called()


def test_catalog_invalid_name_rejected(app, silenced_error):
    goto_page(app, 2)
    app._catalog_mode_var.set("new")
    app._rebuild_catalog_fields()
    app.data["catalog"] = "my-catalog"  # hyphen forbidden by validator
    app.data["_catalog_mode"] = "new"
    assert ((setattr(app, "current_page", 2) or app._validate_current_page())) is False
    silenced_error.assert_called_once()


def test_catalog_conflict_yes_proceeds(app, silenced_error, yes_dialog):
    """User entered an already-existing catalog → dialog → Yes → check passes."""
    goto_page(app, 2)
    app._catalog_mode_var.set("new")
    app._rebuild_catalog_fields()
    # 'samples' is in the mocked workspace → _resource_exists returns True
    app.data["catalog"] = "samples"
    app.data["_catalog_mode"] = "new"
    assert ((setattr(app, "current_page", 2) or app._validate_current_page())) is True
    assert app.data.get("_catalog_reused") is True


def test_catalog_conflict_no_blocks(app, silenced_error, no_dialog):
    goto_page(app, 2)
    app._catalog_mode_var.set("new")
    app._rebuild_catalog_fields()
    app.data["catalog"] = "samples"  # already exists
    app.data["_catalog_mode"] = "new"
    assert ((setattr(app, "current_page", 2) or app._validate_current_page())) is False  # stayed on page
    assert app.data.get("_catalog_reused") is not True


# ── Schema (page index 3) ───────────────────────────────────────────────────

def test_schema_valid_passes(app, silenced_error):
    goto_page(app, 3)
    app.data["schema"] = "ai_assistant_test"
    assert ((setattr(app, "current_page", 3) or app._validate_current_page())) is True


def test_schema_invalid_rejected(app, silenced_error):
    goto_page(app, 3)
    app.data["schema"] = "schema with space"
    assert ((setattr(app, "current_page", 3) or app._validate_current_page())) is False
    silenced_error.assert_called_once()


# ── Warehouse (page index 4) ────────────────────────────────────────────────

def test_warehouse_new_invalid_name_rejected(app, silenced_error):
    goto_page(app, 4)
    app._wh_mode_var.set("new")
    app._rebuild_wh_fields()
    app.update()
    app._wh_new_name_entry.delete(0, "end")
    app._wh_new_name_entry.insert(0, "wh space invalid")
    app.data["_warehouse_create_pending"] = True
    assert ((setattr(app, "current_page", 4) or app._validate_current_page())) is False
    silenced_error.assert_called_once()


def test_warehouse_new_conflict_yes_proceeds(app, silenced_error, yes_dialog):
    goto_page(app, 4)
    app._wh_mode_var.set("new")
    app._rebuild_wh_fields()
    app.update()
    app._wh_new_name_entry.delete(0, "end")
    app._wh_new_name_entry.insert(0, "starter-warehouse")  # exists in mock
    app.data["_warehouse_create_pending"] = True
    assert ((setattr(app, "current_page", 4) or app._validate_current_page())) is True
    assert app.data.get("_warehouse_reused") is True


def test_warehouse_existing_mode_requires_selection(app, silenced_error):
    goto_page(app, 4)
    # Default mode is "existing"; clear the auto-selected id
    app.data["warehouse_id"] = ""
    app.data["_warehouse_create_pending"] = False
    assert ((setattr(app, "current_page", 4) or app._validate_current_page())) is False


# ── VS Endpoint (page index 5) ──────────────────────────────────────────────

def test_vs_endpoint_new_invalid_rejected(app, silenced_error):
    goto_page(app, 5)
    app._ep_mode_var.set("new")
    app._rebuild_ep_fields()
    app.update()
    app._ep_new_name_entry.delete(0, "end")
    app._ep_new_name_entry.insert(0, "ep with space")
    app.data["_ep_create_pending"] = True
    assert ((setattr(app, "current_page", 5) or app._validate_current_page())) is False


def test_vs_endpoint_new_conflict_yes_proceeds(app, silenced_error, yes_dialog):
    goto_page(app, 5)
    app._ep_mode_var.set("new")
    app._rebuild_ep_fields()
    app.update()
    app._ep_new_name_entry.delete(0, "end")
    app._ep_new_name_entry.insert(0, "shared-vs-endpoint")  # exists
    app.data["_ep_create_pending"] = True
    assert ((setattr(app, "current_page", 5) or app._validate_current_page())) is True
    assert app.data.get("_ep_reused") is True


# ── App name (page index 12) ────────────────────────────────────────────────

def test_app_name_too_long_rejected(app, silenced_error):
    goto_page(app, 12)
    app._app_name_entry.delete(0, "end")
    # Bypass the validatecommand by setting data directly
    app.data["app_name"] = "fm-agent-" + "x" * 30  # > 30 chars
    assert ((setattr(app, "current_page", 12) or app._validate_current_page())) is False


def test_app_name_valid_passes(app, silenced_error, monkeypatch):
    """Valid name AND no existing app → passes."""
    goto_page(app, 12)
    # Force _resource_exists to return False for app
    monkeypatch.setattr(app, "_resource_exists", lambda kind, name: False)
    app._app_name_entry.delete(0, "end")
    app._app_name_entry.insert(0, "fm-agent-test-0506")
    assert ((setattr(app, "current_page", 12) or app._validate_current_page())) is True


# ── maxlen validatecommand ─────────────────────────────────────────────────

def test_app_name_entry_blocks_input_past_30_chars(app):
    """Verify the validatecommand prevents typing past APP_NAME_MAX_LENGTH."""
    goto_page(app, 12)
    app._app_name_entry.delete(0, "end")
    # Insert exactly 30 chars
    long_name = "a" * 30
    app._app_name_entry.insert(0, long_name)
    assert app._app_name_entry.get() == long_name
    # Try to add one more — validatecommand should reject
    app._app_name_entry.insert("end", "X")
    assert len(app._app_name_entry.get()) == 30


def test_lakebase_project_entry_blocks_past_56_chars(app):
    app.data["lakebase_required"] = True
    goto_page(app, 7)
    app._lb_proj_entry.delete(0, "end")
    long_name = "a" * 56
    app._lb_proj_entry.insert(0, long_name)
    app._lb_proj_entry.insert("end", "X")
    assert len(app._lb_proj_entry.get()) == 56
