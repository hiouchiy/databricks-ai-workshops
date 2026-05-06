"""Tests for the cleanup script — VS endpoint and SQL warehouse deletion paths.

We can't easily import cleanup.py as a module (it loads .env at import time),
so we drive it as a subprocess with --yes flag against a synthetic .env that
points at non-existent resources. The script must:
  - exit cleanly
  - skip resources that don't exist (returncode 0)
  - skip when _NEW_* tracking flags aren't set
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def _run_cleanup(env_dir: Path, profile: str = "free-edition", env_lines: list[str] = None):
    """Run `python -m scripts.cleanup --yes` in `env_dir`. Returns (returncode, stdout, stderr)."""
    if env_lines:
        (env_dir / ".env").write_text("\n".join(env_lines) + "\n")
    # Provide an empty databricks.yml so the script can find an app name slot
    if not (env_dir / "databricks.yml").exists():
        (env_dir / "databricks.yml").write_text(
            'resources:\n  apps:\n    foo:\n      name: "fm-agent-nonexistent-9999"\n'
        )
    res = subprocess.run(
        [PYTHON, "-m", "scripts.cleanup", "--yes"],
        cwd=str(env_dir),
        env={**os.environ, "PYTHONPATH": str(REPO)},
        capture_output=True,
        text=True,
        timeout=120,
    )
    return res.returncode, res.stdout, res.stderr


def test_cleanup_no_new_resources_skips_warehouse_and_endpoint(tmp_path):
    """When _NEW_WAREHOUSE_ID and _NEW_VS_ENDPOINT are not set, the cleanup
    script must skip those steps without errors."""
    env_lines = [
        "DATABRICKS_CONFIG_PROFILE=free-edition",
        # Intentionally NOT setting _NEW_WAREHOUSE_ID or _NEW_VS_ENDPOINT
    ]
    rc, out, err = _run_cleanup(tmp_path, env_lines=env_lines)
    assert rc == 0, f"Cleanup failed: {err}"
    # The two new sections must announce they're skipping
    assert "[4/10] Vector Search エンドポイント" in out
    assert "[8/10] SQL Warehouse" in out
    assert "新規作成された VS Endpoint が記録されていません" in out
    assert "新規作成された SQL Warehouse が記録されていません" in out


def test_cleanup_with_yes_flag_no_prompts_block(tmp_path):
    """Confirm --yes makes the script run end-to-end without blocking on stdin."""
    env_lines = [
        "DATABRICKS_CONFIG_PROFILE=free-edition",
        "_NEW_WAREHOUSE_ID=wh-doesnotexist-12345",
        "_NEW_VS_ENDPOINT=ep-doesnotexist-99",
    ]
    rc, out, err = _run_cleanup(tmp_path, env_lines=env_lines)
    assert rc == 0, f"Cleanup failed: {err}"
    # The auto-yes hint should appear because confirm() emits it
    assert "[auto: --yes]" in out
    # And the script reaches the final summary
    assert "クリーンアップ完了" in out


def test_cleanup_step_numbering_is_10(tmp_path):
    """Make sure the renumbering 8 -> 10 is consistent."""
    rc, out, err = _run_cleanup(tmp_path, env_lines=["DATABRICKS_CONFIG_PROFILE=free-edition"])
    assert rc == 0, err
    # All 10 step headers should appear
    for n in range(1, 11):
        assert f"[{n}/10]" in out, f"Missing step header [{n}/10]"
