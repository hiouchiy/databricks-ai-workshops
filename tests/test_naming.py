"""L1: pure-function tests for resource naming and validation.

These don't touch the GUI at all — they exercise the helpers in
`quickstart_core.py` that compute defaults, sanitize input, and
validate resource names against per-resource constraints (length /
character set).
"""
from __future__ import annotations

import pytest

import scripts.quickstart_core as core


# ── sanitizers ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("hiroshi.ouchiyama@databricks.com", "hiroshi"),       # first dot-segment of local part
    ("Tanaka.Taro@example.co.jp",        "tanaka"),
    ("a@b.com",                          "a"),
    ("user",                             "user"),
    ("",                                 ""),
])
def test_sanitize_app_name_part_first_segment(raw, expected):
    assert core.sanitize_app_name_part(raw) == expected


def test_sanitize_app_name_part_full_when_disabled():
    assert core.sanitize_app_name_part("hiroshi.ouchiyama@x", prefer_first_segment=False) == "hiroshi-ouchiyama"
    assert core.sanitize_app_name_part("Tanaka_Taro+x@y", prefer_first_segment=False) == "tanaka-taro-x"


@pytest.mark.parametrize("raw, expected", [
    ("hiroshi.ouchiyama@databricks.com", "hiroshi_ouchiyama"),
    ("Tanaka.Taro@example.co.jp",        "tanaka_taro"),
    ("user",                             "user"),
    ("123abc@x",                         "u_123abc"),  # leading-digit guard
    ("a@b.com",                          "a"),
])
def test_sanitize_uc_name_part(raw, expected):
    assert core.sanitize_uc_name_part(raw) == expected


# ── default name generators ─────────────────────────────────────────────────

@pytest.mark.parametrize("user, expected", [
    ("hiroshi.ouchiyama@databricks.com", "fm_handson_hiroshi_ouchiyama"),
    ("alice@x.com",                      "fm_handson_alice"),
    ("user",                             "fm_handson_user"),
])
def test_default_catalog_name(user, expected):
    n = core.compute_default_catalog_name(user)
    assert n == expected
    assert core.validate_uc_object_name(n)[0]


@pytest.mark.parametrize("user, expected", [
    ("hiroshi.ouchiyama@databricks.com", "ai_assistant_hiroshi_ouchiyama"),
    ("alice@x.com",                      "ai_assistant_alice"),
    ("",                                 "ai_assistant"),
    (None,                               "ai_assistant"),
])
def test_default_schema_name(user, expected):
    n = core.compute_default_schema_name(user)
    assert n == expected
    assert core.validate_uc_object_name(n)[0]


@pytest.mark.parametrize("user, day, expected", [
    ("hiroshi.ouchiyama@databricks.com", "2026-05-06", "fm-wh-hiroshi-0506"),
    ("alice@x.com",                      "2026-04-13", "fm-wh-alice-0413"),
    ("a@b.com",                          "2026-12-31", "fm-wh-a-1231"),
])
def test_default_warehouse_name(user, day, expected):
    n = core.compute_default_warehouse_name(user, today=day)
    assert n == expected
    assert core.validate_sql_warehouse_name(n)[0]


@pytest.mark.parametrize("user, day, expected", [
    ("hiroshi.ouchiyama@databricks.com", "2026-05-06", "fm-vs-hiroshi-0506"),
    ("alice@x.com",                      "2026-04-13", "fm-vs-alice-0413"),
])
def test_default_vs_endpoint_name(user, day, expected):
    n = core.compute_default_vs_endpoint_name(user, today=day)
    assert n == expected
    assert core.validate_vs_endpoint_name(n)[0]


@pytest.mark.parametrize("user, day, time, expected", [
    ("hiroshi.ouchiyama@databricks.com", "2026-05-06", "1234", "fm-lakebase-hiroshi-0506-1234"),
    ("alice@x.com",                      "2026-04-13", "0959", "fm-lakebase-alice-0413-0959"),
])
def test_default_lakebase_project(user, day, time, expected):
    # HHMM 付きでソフト削除された project との衝突を避ける（quickstart_core.py 参照）
    n = core.compute_default_lakebase_project_name(user, today=day, hhmm=time)
    assert n == expected
    assert core.is_valid_lakebase_project_name(n)
    # Branch auto-name `{name}-branch` must also fit within the 63-char API limit.
    assert len(n) + len("-branch") <= core.LAKEBASE_BRANCH_MAX_LENGTH


@pytest.mark.parametrize("user, day, time, expected", [
    ("alice@example.com", "2026-05-06", "1234", "/Users/alice@example.com/fm-agent-0506-1234"),
    ("bob@x.com",         "2026-04-13", "0000", "/Users/bob@x.com/fm-agent-0413-0000"),
])
def test_default_mlflow_base_name(user, day, time, expected):
    # HHMM 付きで quickstart 再実行時の experiment 名衝突を回避
    n = core.compute_default_mlflow_base_name(user, today=day, hhmm=time)
    assert n == expected


@pytest.mark.parametrize("user, day, expected_len_max", [
    ("hiroshi.ouchiyama@databricks.com", "2026-05-06", 30),
    ("very.long.user.name.that.would.exceed@x.com", "2026-12-31", 30),
])
def test_default_app_name_within_30_chars(user, day, expected_len_max):
    n = core.compute_default_app_name(user, today=day)
    assert len(n) <= expected_len_max
    assert core.is_valid_app_name(n)


# ── validators ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "hiroshi", "my_catalog", "_underscore_first", "a" * 100,
])
def test_uc_name_valid(name):
    ok, _ = core.validate_uc_object_name(name)
    assert ok


@pytest.mark.parametrize("name, why", [
    ("",            "empty"),
    ("a" * 101,     "length"),
    ("my-catalog",  "hyphen forbidden"),
    ("my.catalog",  "period forbidden"),
    ("my catalog",  "space forbidden"),
    ("1catalog",    "leading digit"),
    ("cat/log",     "slash forbidden"),
])
def test_uc_name_invalid(name, why):
    ok, msg = core.validate_uc_object_name(name)
    assert not ok, f"Should be invalid ({why}): {name!r}"
    assert msg


@pytest.mark.parametrize("name", [
    "freshmart-warehouse", "wh-1", "WH_2025", "a" * 100,
])
def test_warehouse_name_valid(name):
    assert core.validate_sql_warehouse_name(name)[0]


@pytest.mark.parametrize("name", ["", "a" * 101, "wh space", "wh.dot", "-leading", "_leading"])
def test_warehouse_name_invalid(name):
    assert not core.validate_sql_warehouse_name(name)[0]


@pytest.mark.parametrize("name", ["fm-vs-x", "ep_1", "VsEndpoint", "a" * 100])
def test_vs_endpoint_name_valid(name):
    assert core.validate_vs_endpoint_name(name)[0]


@pytest.mark.parametrize("name", ["", "a" * 101, "ep space", "ep.dot", "ep/slash", "-leading"])
def test_vs_endpoint_name_invalid(name):
    assert not core.validate_vs_endpoint_name(name)[0]


@pytest.mark.parametrize("name", ["fm-lakebase-x", "abc", "a" * 56])
def test_lakebase_project_valid(name):
    assert core.is_valid_lakebase_project_name(name)


@pytest.mark.parametrize("name", [
    "", "a" * 57, "Foo", "-leading", "trailing-", "with_underscore", "1leading",
])
def test_lakebase_project_invalid(name):
    assert not core.is_valid_lakebase_project_name(name)


@pytest.mark.parametrize("name", ["fm-agent-x", "ab", "a" * 30])
def test_app_name_valid(name):
    assert core.is_valid_app_name(name)


@pytest.mark.parametrize("name", ["", "a", "a" * 31, "Foo", "-leading", "with_under"])
def test_app_name_invalid(name):
    assert not core.is_valid_app_name(name)
