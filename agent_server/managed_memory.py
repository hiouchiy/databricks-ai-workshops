"""Databricks Managed Memory (Unity Catalog memory-store) 用のクライアント。

Supervisor API 版エージェント（`agent_supervisor.py`）から使う 5 個の memory tool
の実体。LangGraph 版で使っている Lakebase ベースの `utils_memory.py` とは別実装で、
インフラ管理不要な **UC memory-store REST API** を直接叩く。

Beta 機能なので API 仕様は変わり得る。参考：
  https://docs.databricks.com/aws/en/agents/agent-memory/managed-memory

## 設計方針

- `scope` は「誰の記憶か」の分離キー。**trusted code が渡す**（model に選ばせない）。
  SP は全 scope を見られるため、scope 誤設定は情報漏洩に直結する。
- 5 個の tool 定義（Supervisor API に `type=function` として declare）を
  `MEMORY_TOOL_SCHEMAS` として提供。
- `execute_tool(name, args, scope)` で dispatcher。エージェントの loop 側から呼ぶ。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import DatabricksError

logger = logging.getLogger(__name__)

# UC の memory-store securable フル名（catalog.schema.name）を env から取得
MEMORY_STORE_ENV = "DATABRICKS_MEMORY_STORE"

# 5 個の memory tool 名（Supervisor から返ってきた function_call.name の判定に使う）
MEMORY_TOOL_NAMES = frozenset({
    "save_memory",
    "get_memory",
    "list_memories",
    "update_memory",
    "delete_memory",
})

_workspace_client: WorkspaceClient | None = None


def _get_client() -> WorkspaceClient:
    """Cached WorkspaceClient. Apps では SP、ローカルでは CLI プロファイルが使われる。
    per-user 分離は scope に依存するため、この client は「呼び出し可能な代表者」でしかない。"""
    global _workspace_client
    if _workspace_client is None:
        _workspace_client = WorkspaceClient()
    return _workspace_client


def _store_or_raise() -> str:
    store = os.getenv(MEMORY_STORE_ENV, "").strip()
    if not store:
        raise RuntimeError(
            f"{MEMORY_STORE_ENV} is not set. Set it to the full "
            "UC memory-store name (catalog.schema.name) or unset the "
            "memory feature."
        )
    return store


def _entries_path(suffix: str = "") -> str:
    return f"/api/2.1/unity-catalog/memory-stores/{_store_or_raise()}/entries{suffix}"


def is_enabled() -> bool:
    """Memory feature が有効化されているか（env var が set されているか）。"""
    return bool(os.getenv(MEMORY_STORE_ENV, "").strip())


# ── Shared REST core ────────────────────────────────────────────────────

def _save(scope: str, path: str, description: str, contents: str = "") -> str:
    try:
        _get_client().api_client.do(
            "POST",
            _entries_path(),
            query={"scope": scope},
            body={
                "path": path,
                "contents": contents,
                "description": description,
                "creation_reason": "CREATION_REASON_AGENT_INFERRED",
                "creation_source": "CREATION_SOURCE_ONLINE_AGENT",
            },
        )
    except DatabricksError as e:
        if getattr(e, "error_code", "") == "ALREADY_EXISTS":
            return f"A memory already exists at {path}; use update_memory to revise it."
        return f"Could not save {path}: {getattr(e, 'message', str(e))}"
    return f"Saved memory at {path}."


def _get(scope: str, path: str) -> str:
    try:
        entry = _get_client().api_client.do(
            "GET",
            _entries_path(":get"),
            query={"scope": scope, "path": path},
        )
    except DatabricksError as e:
        if getattr(e, "error_code", "") == "NOT_FOUND":
            return f"No memory at {path}."
        return f"Could not read {path}: {getattr(e, 'message', str(e))}"
    # 短いメモリは description が本体（contents は空）
    return entry.get("contents") or entry.get("description") or f"(empty memory at {path})"


def _list(scope: str) -> str:
    try:
        resp = _get_client().api_client.do(
            "GET",
            _entries_path(),
            query={"scope": scope},
        )
    except DatabricksError as e:
        return f"Could not list memories: {getattr(e, 'message', str(e))}"
    items = resp.get("entries", [])
    if not items:
        return "No memories yet."
    lines = [
        ("[has_contents] " if e.get("has_contents") else "")
        + f"- {e['path']}: {e.get('description', '')}"
        for e in items
    ]
    return f"{len(items)} memories total:\n" + "\n".join(lines)


def _update(
    scope: str,
    path: str,
    description: Optional[str] = None,
    str_replace: Optional[dict] = None,
    insert: Optional[dict] = None,
    replace_all: Optional[dict] = None,
) -> str:
    # 内容編集 op は最大 1 個
    ops = {k: v for k, v in (
        ("str_replace", str_replace),
        ("insert", insert),
        ("replace_all", replace_all),
    ) if v}
    if len(ops) > 1:
        return "Pass at most one contents edit (str_replace / insert / replace_all)."
    if not ops and description is None:
        return (
            "Provide a new description and/or one contents edit "
            "(str_replace / insert / replace_all)."
        )
    body: dict[str, Any] = {"scope": scope, "path": path, **ops}
    if description is not None:
        body["description"] = description
    try:
        _get_client().api_client.do("PATCH", _entries_path(), body=body)
    except DatabricksError as e:
        if getattr(e, "error_code", "") == "NOT_FOUND":
            return f"No memory at {path} to update — check list_memories or save it first."
        return f"Could not update {path}: {getattr(e, 'message', str(e))}"
    return f"Updated {path}."


def _delete(scope: str, path: str) -> str:
    try:
        _get_client().api_client.do(
            "DELETE",
            _entries_path(),
            query={"scope": scope, "path": path},
        )
    except DatabricksError as e:
        if getattr(e, "error_code", "") == "NOT_FOUND":
            return f"No memory at {path} (already gone)."
        return f"Could not delete {path}: {getattr(e, 'message', str(e))}"
    return f"Deleted {path}."


# ── Tool schemas (Supervisor API `type=function` として declare する形) ──

MEMORY_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "save_memory",
        "description": (
            "Create ONE durable memory — a stable preference, fact, decision, or ongoing "
            "project; not one-off chatter or secrets. Create-only (an existing path errors), "
            "so check list_memories first and use update_memory to revise a topic. "
            "path: SHORT, STABLE topic bucket (lowercase-hyphenated, starts /memories/, ends .md). "
            "Keep it broad and reusable so related facts share one path. "
            "description: one-line statement; for a brief fact this IS the memory "
            "(leave contents empty). contents: OPTIONAL; only when memory needs more than one line."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "e.g. /memories/preferences/diet.md"},
                "description": {"type": "string"},
                "contents": {"type": "string", "default": ""},
            },
            "required": ["path", "description"],
        },
    },
    {
        "type": "function",
        "name": "get_memory",
        "description": (
            "Read the FULL contents of ONE memory by its exact path (from list_memories). "
            "The only way to see what a memory says — always get_memory before stating a "
            "remembered fact; a description is just a label."
        ),
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "type": "function",
        "name": "list_memories",
        "description": (
            "List EVERY saved memory as (path, description) — the index; returns NO contents. "
            "Your first step for recall and before saving. An entry prefixed [has_contents] "
            "has a fuller body — get_memory(path) to read it. One call per turn."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "update_memory",
        "description": (
            "Revise an EXISTING memory in place (same path). Pass description to replace "
            "the one-line description, and/or EXACTLY ONE contents edit op: "
            "str_replace={old_str, new_str} (old_str must occur once) · "
            "insert={insert_text, insert_line?} · replace_all={contents}. "
            "get_memory first so a contents edit matches."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "description": {"type": "string"},
                "str_replace": {
                    "type": "object",
                    "properties": {
                        "old_str": {"type": "string"},
                        "new_str": {"type": "string"},
                    },
                },
                "insert": {
                    "type": "object",
                    "properties": {
                        "insert_text": {"type": "string"},
                        "insert_line": {"type": "integer"},
                    },
                },
                "replace_all": {
                    "type": "object",
                    "properties": {"contents": {"type": "string"}},
                },
            },
            "required": ["path"],
        },
    },
    {
        "type": "function",
        "name": "delete_memory",
        "description": (
            "Permanently remove ONE memory by its exact path. Use for stale/wrong/superseded "
            "entries or when the user asks to forget something. Don't delete to rewrite a "
            "valid fact — use update_memory."
        ),
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
]


# ── Dispatcher ─────────────────────────────────────────────────────────

def execute_tool(name: str, arguments_json: str, scope: str) -> str:
    """Supervisor が emit した function_call を実行する。

    Args:
        name: memory tool 名（MEMORY_TOOL_NAMES のいずれか）
        arguments_json: model が生成した JSON 文字列
        scope: trusted code が決めた scope（user id 等）

    Returns:
        tool result 文字列（Supervisor に function_call_output として返す）
    """
    if not scope:
        # 保険：呼び出し側で防いでいるはずだが二重ガード
        return "Error: no scope resolved for this request; memory operations are refused."
    try:
        args = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError as e:
        return f"Invalid arguments JSON for {name}: {e}"

    if name == "save_memory":
        return _save(
            scope,
            args["path"],
            args["description"],
            args.get("contents", ""),
        )
    if name == "get_memory":
        return _get(scope, args["path"])
    if name == "list_memories":
        return _list(scope)
    if name == "update_memory":
        return _update(
            scope,
            args["path"],
            description=args.get("description"),
            str_replace=args.get("str_replace"),
            insert=args.get("insert"),
            replace_all=args.get("replace_all"),
        )
    if name == "delete_memory":
        return _delete(scope, args["path"])
    return f"Unknown memory tool: {name}"


# ── System-prompt fragment ─────────────────────────────────────────────

MEMORY_INSTRUCTIONS = """You have durable, cross-session memory scoped to the current user. Use it deliberately, not by reflex.

Recall whenever the answer might draw on preferences, decisions, or workflows the user shared before; also list once before saving to find the right existing topic. Skip memory only when the answer truly doesn't depend on who's asking (general knowledge, math, coding). An entry prefixed [has_contents] has a body to get_memory; one without is fully captured by its description. Open with get_memory before stating specifics; never assert a fact that isn't stored.

Save only what will still matter in a future, unrelated conversation — a stable preference, fact, decision, or ongoing project the user actually stated. Don't save your own suggestions, passing chatter, secrets, or one-off labels.

- Each memory stands on its own out of context, under one broad, stable /memories/... topic per subject.
- Check the list first; update_memory an existing topic instead of duplicating.
- For broad questions, summarize from the list's descriptions.
- If info changes/contradicts, update or replace; don't keep both.
- delete_memory what's stale.
- Briefly tell the user whenever you save/update/delete.
"""
