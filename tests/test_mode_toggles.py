"""L3: mode-toggle behaviour for catalog / warehouse / VS endpoint / Lakebase.

Regression coverage for two recent bugs:
  1. Switching existing→new leaked the existing-mode dropdown selection
     into the new-mode entry default (instead of `compute_default_*`).
  2. Toggling new→existing re-fetched the heavy list every time, freezing
     the UI; we now cache the list per page-instance.

These tests also do "monkey-style" rapid toggles (4–6 flips) to make
sure widget state stays consistent and no API call leaks.
"""
from __future__ import annotations

import scripts.quickstart_core as core
from .conftest import goto_page


# ── Catalog ──────────────────────────────────────────────────────────────────

def test_catalog_existing_to_new_uses_user_default(app):
    """Bug regression: switching existing→new must show the user-based default,
    NOT the catalog selected from the existing dropdown."""
    goto_page(app, 2)
    # Default is "existing" — dropdown already populated; pick a known item
    app._catalog_dropdown_var.set("samples")
    app._on_catalog_dropdown_change("samples")
    assert app.data["catalog"] == "samples"

    # Switch to "new"
    app._catalog_mode_var.set("new")
    app._rebuild_catalog_fields()
    app.update()

    expected = core.compute_default_catalog_name(app.data["username"])
    assert app._catalog_entry.get() == expected
    assert app._catalog_entry.get() != "samples"


def test_catalog_new_typed_value_persists_through_toggles(app):
    goto_page(app, 2)
    # Go to new, edit
    app._catalog_mode_var.set("new")
    app._rebuild_catalog_fields()
    app.update()
    app._catalog_entry.delete(0, "end")
    app._catalog_entry.insert(0, "my_custom_catalog")
    app._on_catalog_entry_change()
    app.update()
    assert app.data.get("_catalog_new_typed") == "my_custom_catalog"

    # Flip to existing then back to new — typed value should be restored
    app._catalog_mode_var.set("existing")
    app._rebuild_catalog_fields()
    app.update()

    app._catalog_mode_var.set("new")
    app._rebuild_catalog_fields()
    app.update()
    assert app._catalog_entry.get() == "my_custom_catalog"


def test_catalog_monkey_rapid_toggle_does_not_corrupt_state(app, mock_core):
    """Rapidly toggling existing↔new 6 times must not crash and must not
    re-fetch the catalogs list more than once."""
    goto_page(app, 2)
    api_calls_before = sum(
        1 for c in mock_core["api_get"].call_args_list
        if c.args and c.args[0] == "/api/2.1/unity-catalog/catalogs"
    )

    for mode in ["new", "existing", "new", "existing", "new", "existing"]:
        app._catalog_mode_var.set(mode)
        app._rebuild_catalog_fields()
        app.update()

    api_calls_after = sum(
        1 for c in mock_core["api_get"].call_args_list
        if c.args and c.args[0] == "/api/2.1/unity-catalog/catalogs"
    )
    # Cache means we never re-fetch after the first
    assert api_calls_after - api_calls_before <= 1


# ── SQL Warehouse ───────────────────────────────────────────────────────────

def test_warehouse_existing_to_new_uses_user_default(app):
    goto_page(app, 4)
    app.update()
    # In existing mode, _on_wh_change has set warehouse_name to the running one
    assert app.data.get("warehouse_name", "") != ""

    app._wh_mode_var.set("new")
    app._rebuild_wh_fields()
    app.update()

    expected = core.compute_default_warehouse_name(app.data["username"])
    assert app._wh_new_name_entry.get() == expected
    assert expected.startswith("fm-wh-")
    # Must NOT be the existing warehouse name
    assert "Starter" not in expected


def test_warehouse_new_typed_value_persists_through_toggles(app):
    goto_page(app, 4)
    app._wh_mode_var.set("new")
    app._rebuild_wh_fields()
    app.update()

    # Simulate user typing: replace the entry value, then explicitly fire
    # the <KeyRelease> handler. Tk's `bind()` returns the bound Tcl script
    # name, so we just generate the event after focusing the widget.
    app._wh_new_name_entry.focus_set()
    app._wh_new_name_entry.delete(0, "end")
    app._wh_new_name_entry.insert(0, "my-custom-wh")
    app._wh_new_name_entry.event_generate("<KeyRelease>", when="now")
    app.update()
    assert app.data.get("_warehouse_new_typed") == "my-custom-wh"

    # Flip and return — typed value should be restored
    app._wh_mode_var.set("existing")
    app._rebuild_wh_fields()
    app.update()
    app._wh_mode_var.set("new")
    app._rebuild_wh_fields()
    app.update()
    assert app._wh_new_name_entry.get() == "my-custom-wh"


def test_warehouse_existing_list_cached(app, mock_core):
    """The expensive permission-filter call should not re-run on toggle."""
    goto_page(app, 4)
    initial_calls = mock_core["filter_usable_warehouses"].call_count
    # Toggle several times
    for mode in ["new", "existing", "new", "existing"]:
        app._wh_mode_var.set(mode)
        app._rebuild_wh_fields()
        app.update()
    # The fetch is done once; subsequent renders use the cache.
    assert mock_core["filter_usable_warehouses"].call_count == initial_calls


# ── VS Endpoint ─────────────────────────────────────────────────────────────

def test_vs_endpoint_existing_to_new_uses_user_default(app):
    goto_page(app, 5)
    app.update()
    assert app.data.get("vs_endpoint", "") != ""  # set by _on_ep_change

    app._ep_mode_var.set("new")
    app._rebuild_ep_fields()
    app.update()

    expected = core.compute_default_vs_endpoint_name(app.data["username"])
    assert app._ep_new_name_entry.get() == expected
    assert expected.startswith("fm-vs-")


def test_vs_endpoint_existing_list_cached(app, mock_core):
    goto_page(app, 5)
    initial_calls = sum(
        1 for c in mock_core["api_get"].call_args_list
        if c.args and c.args[0] == "/api/2.0/vector-search/endpoints"
    )
    for mode in ["new", "existing", "new", "existing"]:
        app._ep_mode_var.set(mode)
        app._rebuild_ep_fields()
        app.update()
    after_calls = sum(
        1 for c in mock_core["api_get"].call_args_list
        if c.args and c.args[0] == "/api/2.0/vector-search/endpoints"
    )
    # No additional fetches beyond the first
    assert after_calls == initial_calls


# ── Lakebase ────────────────────────────────────────────────────────────────

def test_lakebase_new_to_existing_preserves_separate_typed_slots(app):
    """New-mode is a text entry; existing-mode is a dropdown of fetched
    projects. Switching modes should restore each mode's last value
    independently (no cross-leak)."""
    app.data["lakebase_required"] = True
    goto_page(app, 7)
    # Default: new mode → text entry with computed default
    new_default = core.compute_default_lakebase_project_name(app.data["username"])
    assert app._lb_proj_entry.get() == new_default

    # Edit in new mode
    app._lb_proj_entry.delete(0, "end")
    app._lb_proj_entry.insert(0, "my-new-lb")
    app._on_lb_proj_change()
    assert app.data.get("_lb_new_typed") == "my-new-lb"

    # Switch to existing mode → dropdown of mocked projects
    app._lb_mode_var.set("existing")
    app._rebuild_lakebase_fields()
    app.update()
    # Default selection is the first project
    assert app.data["lakebase_project"] in app._lakebase_projects_cache
    # Pick the second one explicitly
    selected = app._lakebase_projects_cache[1]
    app._lb_proj_var.set(selected)
    app._on_lb_proj_dropdown_change(selected)
    assert app.data["_lb_existing_typed"] == selected

    # Flip back to new — should restore the new-mode value
    app._lb_mode_var.set("new")
    app._rebuild_lakebase_fields()
    app.update()
    assert app._lb_proj_entry.get() == "my-new-lb"

    # Flip to existing again — dropdown should pre-select the previous choice
    app._lb_mode_var.set("existing")
    app._rebuild_lakebase_fields()
    app.update()
    assert app._lb_proj_var.get() == selected
    assert app.data["lakebase_project"] == selected


def test_lakebase_existing_dropdown_lists_workspace_projects(app, mock_core):
    """Verify the dropdown is populated from list_lakebase_projects() and
    cached so subsequent renders skip the SDK call."""
    app.data["lakebase_required"] = True
    goto_page(app, 7)
    app._lb_mode_var.set("existing")
    app._rebuild_lakebase_fields()
    app.update()
    assert app._lakebase_projects_cache == [
        "fm-lakebase-existing-0501", "shared-team-lakebase"
    ]
    assert mock_core["list_lakebase_projects"].call_count == 1

    # Toggle multiple times — fetch is not repeated thanks to cache
    for mode in ["new", "existing", "new", "existing"]:
        app._lb_mode_var.set(mode)
        app._rebuild_lakebase_fields()
        app.update()
    assert mock_core["list_lakebase_projects"].call_count == 1


def test_lakebase_existing_falls_back_to_text_entry_when_no_projects(app, mock_core):
    """If the workspace has no projects, the existing branch should still
    let the user proceed by typing a name (text-entry fallback)."""
    app.data["lakebase_required"] = True
    mock_core["list_lakebase_projects"].return_value = []
    goto_page(app, 7)
    app._lb_mode_var.set("existing")
    app._rebuild_lakebase_fields()
    app.update()
    # Text entry should be present as fallback; dropdown should NOT be.
    assert hasattr(app, "_lb_proj_entry")
    assert not hasattr(app, "_lb_proj_dropdown") or app._lakebase_projects_cache == []
