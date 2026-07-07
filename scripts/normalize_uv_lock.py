#!/usr/bin/env python3
"""uv.lock の Databricks 内部 PyPI proxy URL を public PyPI URL に書き換える。

背景:
  社内 PyPI proxy (`pypi-proxy.dev.databricks.com`) は Databricks コーポレート
  ネットワーク経由でしか到達できない。`UV_INDEX_URL=...proxy...` を指定して
  ローカルで `uv lock` すると proxy URL が uv.lock に記録され、Databricks Apps
  ランタイムからは fetch できず deploy 失敗する（"operation timed out" /
  "Failed to download `<pkg>`"）。

  proxy は pypi.org / files.pythonhosted.org の透過ミラーで、パスと SHA-256
  hash はすべて一致するため、URL 部分だけ書き換えれば hash 検証はそのまま
  成立する。

使い方:
  uv add / uv lock / uv sync --upgrade を実行して uv.lock を更新した後、
  commit する前に必ずこれを実行する:

      uv run python scripts/normalize_uv_lock.py

  変換内容:
      https://pypi-proxy.dev.databricks.com/simple      → https://pypi.org/simple
      https://pypi-proxy.dev.databricks.com/packages/…  → https://files.pythonhosted.org/packages/…
"""
from __future__ import annotations

import sys
from pathlib import Path

LOCK_PATH = Path(__file__).resolve().parent.parent / "uv.lock"

REWRITES = [
    (
        "https://pypi-proxy.dev.databricks.com/packages/",
        "https://files.pythonhosted.org/packages/",
    ),
    (
        "https://pypi-proxy.dev.databricks.com/simple",
        "https://pypi.org/simple",
    ),
]


def main() -> int:
    if not LOCK_PATH.exists():
        print(f"uv.lock not found at {LOCK_PATH}", file=sys.stderr)
        return 1

    original = LOCK_PATH.read_text()
    rewritten = original
    total = 0
    for old, new in REWRITES:
        count = rewritten.count(old)
        if count:
            rewritten = rewritten.replace(old, new)
            print(f"  {count:>5} × {old} → {new}")
            total += count

    if total == 0:
        print("uv.lock は既に normalize 済み (proxy URL 検出なし)。")
        return 0

    LOCK_PATH.write_text(rewritten)
    print(f"\n{total} URL(s) を書き換えました。commit してください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
