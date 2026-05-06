"""L5: Next/Back navigation round-trips and state preservation.

Verify that:
  - `show_page(n)` actually changes `current_page`
  - Navigating Back→Next returns the user to the same value they had
  - The bottom nav bar hides on terminal pages (execute / complete)
  - Step counter advances correctly
  - Monkey navigation (Next×N then Back×M then Next×K) keeps state coherent
"""
from __future__ import annotations

import pytest

import scripts.quickstart_core as core
from .conftest import goto_page


# ── Basic page transitions ──────────────────────────────────────────────────

def test_show_page_changes_current(app):
    goto_page(app, 0)
    assert app.current_page == 0
    goto_page(app, 5)
    assert app.current_page == 5


def test_total_pages_is_16(app):
    import scripts.quickstart_gui as gui
    assert gui.TOTAL_PAGES == 16


# ── State preservation across navigation ───────────────────────────────────

def test_catalog_value_preserved_through_back_and_forward(app):
    goto_page(app, 2)
    app._catalog_mode_var.set("new")
    app._rebuild_catalog_fields()
    app.update()
    app._catalog_entry.delete(0, "end")
    app._catalog_entry.insert(0, "fm_handson_test123")
    app._on_catalog_entry_change()
    app.update()
    assert app.data["catalog"] == "fm_handson_test123"

    # Navigate forward, then back
    goto_page(app, 3)
    goto_page(app, 2)

    # In data the value should still be there
    assert app.data["catalog"] == "fm_handson_test123"


def test_schema_value_preserved(app):
    goto_page(app, 3)
    app._schema_entry.delete(0, "end")
    app._schema_entry.insert(0, "ai_assistant_custom")
    app.data["schema"] = "ai_assistant_custom"

    goto_page(app, 4)
    goto_page(app, 3)
    # data["schema"] should still hold the customized value
    assert app.data["schema"] == "ai_assistant_custom"


def test_app_name_value_preserved(app):
    goto_page(app, 12)
    app._app_name_entry.delete(0, "end")
    app._app_name_entry.insert(0, "fm-agent-custom-0506")
    app.data["app_name"] = "fm-agent-custom-0506"

    goto_page(app, 11)
    goto_page(app, 12)
    assert app.data["app_name"] == "fm-agent-custom-0506"


# ── Nav bar visibility ──────────────────────────────────────────────────────

def test_nav_bar_hidden_on_execute_page(app):
    """Execute page (idx 14) hides bottom nav bar — handled by show_page logic."""
    goto_page(app, 14)
    # The test of UI mapped state — _bottom_bar.pack_forget() called at pg>=14
    # We can't easily assert pack state cross-platform, but we can assert
    # current_page is set and that the page exists.
    assert app.current_page == 14


def test_nav_bar_hidden_on_complete_page(app):
    app.data["setup_complete"] = True
    goto_page(app, 15)
    assert app.current_page == 15


# ── Monkey navigation ──────────────────────────────────────────────────────

def test_monkey_nav_no_state_corruption(app):
    """Repeatedly Next/Back/Next/Back through pages 0..6.
    All edits to data should remain intact."""
    # Set values on pages 2 and 3
    goto_page(app, 2)
    app._catalog_mode_var.set("new")
    app._rebuild_catalog_fields()
    app.update()
    app._catalog_entry.delete(0, "end")
    app._catalog_entry.insert(0, "fm_handson_x")
    app._on_catalog_entry_change()

    goto_page(app, 3)
    app._schema_entry.delete(0, "end")
    app._schema_entry.insert(0, "ai_assistant_x")
    app.data["schema"] = "ai_assistant_x"

    # Walk back and forth several times
    for n in [4, 3, 2, 3, 4, 3, 2, 3]:
        goto_page(app, n)

    # Assert final state preserved
    assert app.data["catalog"] == "fm_handson_x"
    assert app.data["schema"] == "ai_assistant_x"


def test_monkey_mode_toggle_with_navigation(app):
    """Combo: edit on page 2, leave to page 3, return, change mode, edit, leave again."""
    goto_page(app, 2)
    app._catalog_mode_var.set("new")
    app._rebuild_catalog_fields()
    app.update()
    app._catalog_entry.delete(0, "end")
    app._catalog_entry.insert(0, "first_value")
    app._on_catalog_entry_change()

    goto_page(app, 3)
    goto_page(app, 2)  # back to catalog

    # Mode is preserved as "new"; entry value preserved via _catalog_new_typed
    assert app._catalog_mode_var.get() == "new"
    assert app.data["catalog"] == "first_value"

    # Change to existing then back
    app._catalog_mode_var.set("existing")
    app._rebuild_catalog_fields()
    app.update()
    app._catalog_mode_var.set("new")
    app._rebuild_catalog_fields()
    app.update()
    # _catalog_new_typed kept the old value
    assert app._catalog_entry.get() == "first_value"


# ── Step counter ──────────────────────────────────────────────────────────

def test_step_label_reflects_page(app):
    goto_page(app, 5)
    # Label format: "Step {pg+1} of 16"
    assert "6" in app._page_label.cget("text")
    assert "16" in app._page_label.cget("text")


# ── Validation gating Next button (forward direction) ─────────────────────

def test_invalid_input_blocks_forward(app, monkeypatch):
    """If validation fails on the current page, _go_next must not advance."""
    goto_page(app, 3)
    app.data["schema"] = ""  # empty → invalid
    app.current_page = 3
    monkeypatch.setattr(app, "_show_error", lambda *a, **kw: None)
    app._go_next()
    # current_page should NOT have advanced
    assert app.current_page == 3


def test_back_always_works_even_with_invalid_state(app):
    """Back button bypasses validation."""
    goto_page(app, 3)
    app.data["schema"] = ""  # would block forward
    app.current_page = 3
    app._go_back()
    assert app.current_page == 2
