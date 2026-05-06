#!/usr/bin/env python3
"""
CustomTkinter desktop wizard for Databricks agent quickstart setup.

Usage:
    uv run quickstart-ui
"""

import contextlib
import io
import json
import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path

import customtkinter

from scripts import quickstart_core as core

# ── Appearance ──────────────────────────────────────────────────────────
customtkinter.set_appearance_mode("dark")
customtkinter.set_default_color_theme("blue")

TOTAL_PAGES = 16


# ── Helper: bilingual text ─────────────────────────────────────────────
def t(ja: str, en: str) -> str:
    return core.t(ja, en)


# ════════════════════════════════════════════════════════════════════════
#  QuickstartWizard
# ════════════════════════════════════════════════════════════════════════
class QuickstartWizard(customtkinter.CTk):
    def __init__(self):
        super().__init__()

        self.title("FreshMart AI Agent - Quickstart Setup")
        self.geometry("700x550")
        self.resizable(False, False)
        self._center_window(700, 550)

        # ── State ───────────────────────────────────────────────────────
        self.data: dict = {
            "lang": "ja",
            # Auth
            "profile_name": "",
            "host": "",
            "username": "",
            "token": "",
            "auth_ok": False,
            # Workspace
            "catalog": "",
            "schema": "",
            "warehouse_id": "",
            "warehouse_name": "",
            "vs_endpoint": "",
            # Lakebase
            "lakebase_mode": "new",
            "lakebase_project": "",
            "lakebase_branch": "",
            "lakebase_config": None,
            "lakebase_required": False,
            # MLflow
            "mlflow_mode": "new",
            "mlflow_base_name": "",
            "monitoring_name": "",
            "monitoring_id": "",
            "eval_name": "",
            "eval_id": "",
            # Trace
            "trace_dest_mode": "mlflow",
            "trace_dest_schema": "",
            "existing_trace_dest": "",
            # Prompt Registry
            "use_prompt_registry": "no",
            # LLM endpoint
            "llm_endpoint": "",
            # App name
            "app_name": "",
            # Prerequisites
            "prereqs_ok": False,
            # Execution
            "setup_log": [],
            "setup_failed_steps": [],
            "setup_complete": False,
            # Genie
            "genie_mode": "new",
            "genie_space_id": "",
            "vs_index": "",
        }

        self.current_page = 0  # 0-indexed internally; displayed as 1-indexed

        # ── Cached widget data ──────────────────────────────────────────
        self._warehouses: list[dict] = []
        self._vs_endpoints: list[dict] = []

        # ── Queue for execution thread ──────────────────────────────────
        self._exec_queue: queue.Queue = queue.Queue()
        self._exec_running = False

        # ── Content frame & bottom bar ──────────────────────────────────
        self._content_frame: customtkinter.CTkFrame | None = None

        self._bottom_bar = customtkinter.CTkFrame(self, height=50)
        self._bottom_bar.pack(side="bottom", fill="x", padx=10, pady=(0, 10))

        self._back_btn = customtkinter.CTkButton(
            self._bottom_bar, text="", width=100, command=self._go_back
        )
        self._back_btn.pack(side="left", padx=5)

        self._page_label = customtkinter.CTkLabel(self._bottom_bar, text="")
        self._page_label.pack(side="left", expand=True)

        self._next_btn = customtkinter.CTkButton(
            self._bottom_bar, text="", width=100, command=self._go_next
        )
        self._next_btn.pack(side="right", padx=5)

        # Show first page
        self.show_page(0)

        # Bring window to front
        self.lift()
        self.attributes("-topmost", True)
        self.after(500, lambda: self.attributes("-topmost", False))
        self.focus_force()

    # ── Window centering ────────────────────────────────────────────────
    def _center_window(self, w: int, h: int):
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── Page navigation ─────────────────────────────────────────────────
    def show_page(self, n: int):
        if self._content_frame is not None:
            self._content_frame.destroy()

        self.current_page = n
        self._content_frame = customtkinter.CTkFrame(self)
        self._content_frame.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        builder = self._page_builders()[n]
        builder(self._content_frame)

        self._update_nav()

    def _page_builders(self):
        return [
            self._page_language,        # 0 -> Step 1
            self._page_auth,            # 1 -> Step 2
            self._page_catalog,         # 2 -> Step 3
            self._page_schema,          # 3 -> Step 4
            self._page_warehouse,       # 4 -> Step 5
            self._page_vs_endpoint,     # 5 -> Step 6
            self._page_genie,           # 6 -> Step 7
            self._page_lakebase,        # 7 -> Step 8
            self._page_mlflow,          # 8 -> Step 9
            self._page_trace,           # 9 -> Step 10
            self._page_prompt_registry, # 10 -> Step 11
            self._page_llm_endpoint,    # 11 -> Step 12
            self._page_app_name,        # 12 -> Step 13
            self._page_summary,         # 13 -> Step 14
            self._page_execute,         # 14 -> Step 15
            self._page_complete,        # 15 -> Step 16
        ]

    def _update_nav(self):
        pg = self.current_page
        self._back_btn.configure(text=t("\u2190 \u623b\u308b", "\u2190 Back"))
        self._next_btn.configure(text=t("\u6b21\u3078 \u2192", "Next \u2192"))
        self._page_label.configure(
            text=f"Step {pg + 1} of {TOTAL_PAGES}"
        )

        # Hide bottom bar entirely on execute/complete pages — those pages own
        # their own buttons (Run / Complete / Rollback / Close).
        if pg >= 14:
            self._bottom_bar.pack_forget()
            return
        else:
            if not self._bottom_bar.winfo_ismapped():
                self._bottom_bar.pack(side="bottom", fill="x", padx=10, pady=(0, 10))

        if pg == 0:
            self._back_btn.configure(state="disabled")
        else:
            self._back_btn.configure(state="normal")
        self._next_btn.configure(state="normal")

    def _go_back(self):
        if self.current_page > 0:
            self.show_page(self.current_page - 1)

    def _go_next(self):
        if not self._validate_current_page():
            return
        if self.current_page < TOTAL_PAGES - 1:
            self.show_page(self.current_page + 1)

    # ── Validation ──────────────────────────────────────────────────────
    def _validate_current_page(self) -> bool:
        pg = self.current_page
        if pg == 1:
            if not self.data.get("auth_ok"):
                self._show_error(t(
                    "\u5148\u306b\u300c\u63a5\u7d9a\u300d\u3092\u30af\u30ea\u30c3\u30af\u3057\u3066\u8a8d\u8a3c\u3092\u5b8c\u4e86\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
                    "Please click 'Connect' to complete authentication first."
                ))
                return False
        elif pg == 2:
            catalog_name = self.data.get("catalog", "").strip()
            if not catalog_name:
                self._show_error(t(
                    "カタログ名を入力してください。",
                    "Please enter a catalog name."
                ))
                return False
            if self.data.get("_catalog_mode") == "new":
                valid, msg = self._validate_uc_name(catalog_name)
                if not valid:
                    self._show_error(msg)
                    return False
                # 同名既存チェック → ダイアログ
                if self._resource_exists("catalog", catalog_name):
                    if not self._confirm_use_existing("カタログ", "catalog", catalog_name):
                        return False  # ユーザーが「いいえ」を選択 → このページに留まる
                    self.data["_catalog_reused"] = True
        elif pg == 3:
            schema_name = self.data.get("schema", "").strip()
            if not schema_name:
                self._show_error(t(
                    "スキーマ名を入力してください。",
                    "Please enter a schema name."
                ))
                return False
            valid, msg = self._validate_uc_name(schema_name)
            if not valid:
                self._show_error(msg)
                return False
            # 同名既存チェック → ダイアログ（カタログが存在する場合のみ）
            if self._resource_exists("schema", schema_name):
                if not self._confirm_use_existing("スキーマ", "schema", schema_name):
                    return False
                self.data["_schema_reused"] = True
        elif pg == 4:
            # In "new" mode, warehouse_id is empty until run-time creation.
            # Capture the latest name from the entry field.
            if self.data.get("_warehouse_create_pending"):
                if hasattr(self, "_wh_new_name_entry"):
                    name = self._wh_new_name_entry.get().strip() or core.compute_default_warehouse_name(self.data.get("username", ""))
                    valid, msg = core.validate_sql_warehouse_name(name)
                    if not valid:
                        self._show_error(msg)
                        return False
                    self.data["warehouse_name"] = name
                    # 同名既存チェック
                    if self._resource_exists("warehouse", name):
                        if not self._confirm_use_existing("ウェアハウス", "warehouse", name):
                            return False
                        self.data["_warehouse_reused"] = True
            elif not self.data.get("warehouse_id", "").strip():
                self._show_error(t(
                    "\u30a6\u30a7\u30a2\u30cf\u30a6\u30b9\u3092\u9078\u629e\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
                    "Please select a warehouse."
                ))
                return False
        elif pg == 5:
            # In "new" mode, validate the user-entered VS endpoint name.
            if self.data.get("_ep_create_pending") and hasattr(self, "_ep_new_name_entry"):
                name = self._ep_new_name_entry.get().strip()
                if name:
                    valid, msg = core.validate_vs_endpoint_name(name)
                    if not valid:
                        self._show_error(msg)
                        return False
                    self.data["vs_endpoint"] = name
                    # 同名既存チェック
                    if self._resource_exists("vs_endpoint", name):
                        if not self._confirm_use_existing(
                            "Vector Search エンドポイント", "Vector Search endpoint", name,
                        ):
                            return False
                        self.data["_ep_reused"] = True
            if not self.data.get("vs_endpoint", "").strip():
                # Allow empty with warning
                pass
        elif pg == 6:
            # Genie Space
            mode = self.data.get("genie_mode", "new")
            if mode == "existing" and not self.data.get("genie_space_id", "").strip():
                self._show_error(t(
                    "Genie Space ID を入力してください。",
                    "Please enter a Genie Space ID."
                ))
                return False
        elif pg == 7:
            # Lakebase
            mode = self.data.get("lakebase_mode", "new")
            project_name = self.data.get("lakebase_project", "").strip()
            if mode == "new":
                if not project_name:
                    self._show_error(t(
                        "プロジェクト名を入力してください。",
                        "Please enter a project name."
                    ))
                    return False
                valid, msg = self._validate_lakebase_name(project_name)
                if not valid:
                    self._show_error(msg)
                    return False
                # 同名既存チェック → ダイアログ
                if self._resource_exists("lakebase", project_name):
                    if not self._confirm_use_existing(
                        "Lakebase プロジェクト", "Lakebase project", project_name,
                    ):
                        return False
                    self.data["_lakebase_reused"] = True
            else:
                if not project_name:
                    self._show_error(t(
                        "プロジェクト名を入力してください。",
                        "Please enter a project name."
                    ))
                    return False
                valid, msg = self._validate_lakebase_name(project_name)
                if not valid:
                    self._show_error(msg)
                    return False
                if not self.data.get("lakebase_branch", "").strip():
                    self._show_error(t(
                        "ブランチ名を入力してください。",
                        "Please enter a branch name."
                    ))
                    return False
        elif pg == 8:
            mode = self.data.get("mlflow_mode", "new")
            if mode == "new":
                if not self.data.get("mlflow_base_name", "").strip():
                    self._show_error(t(
                        "\u30d9\u30fc\u30b9\u540d\u3092\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
                        "Please enter a base name."
                    ))
                    return False
            else:
                if not self.data.get("monitoring_id", "").strip():
                    self._show_error(t(
                        "\u30e2\u30cb\u30bf\u30ea\u30f3\u30b0 Experiment ID \u3092\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
                        "Please enter a Monitoring Experiment ID."
                    ))
                    return False
                if not self.data.get("eval_id", "").strip():
                    self._show_error(t(
                        "\u8a55\u4fa1 Experiment ID \u3092\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
                        "Please enter an Evaluation Experiment ID."
                    ))
                    return False
        elif pg == 11:
            # LLM endpoint page
            if not self.data.get("_llm_models_available") and hasattr(self, "_llm_manual_entry"):
                self.data["llm_endpoint"] = self._llm_manual_entry.get().strip()
            if not self.data.get("llm_endpoint", "").strip():
                self._show_error(t(
                    "LLM \u30a8\u30f3\u30c9\u30dd\u30a4\u30f3\u30c8\u540d\u3092\u9078\u629e\u307e\u305f\u306f\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
                    "Please select or enter an LLM endpoint name."
                ))
                return False
        elif pg == 12:
            # App name page
            if hasattr(self, "_app_name_entry"):
                self.data["app_name"] = self._app_name_entry.get().strip()
            app_name = self.data.get("app_name", "").strip()
            if not app_name:
                self._show_error(t(
                    "Databricks App \u540d\u3092\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
                    "Please enter a Databricks App name.",
                ))
                return False
            if not core.is_valid_app_name(app_name):
                self._show_error(t(
                    f"\u7121\u52b9\u306a App \u540d: {app_name}\n\u5c0f\u6587\u5b57\u82f1\u6570\u5b57\u3068\u30cf\u30a4\u30d5\u30f3\u3001\u82f1\u5b57\u3067\u59cb\u307e\u308a\u82f1\u6570\u3067\u7d42\u308f\u308b\u300130\u6587\u5b57\u4ee5\u5185\u306b\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
                    f"Invalid app name: {app_name}\nUse lowercase alphanumeric+hyphen, start with letter, end with alphanumeric, ≤30 chars.",
                ))
                return False
            # 同名既存チェック → ダイアログ
            if self._resource_exists("app", app_name):
                if not self._confirm_use_existing(
                    "Databricks App", "Databricks App", app_name,
                ):
                    return False
                self.data["_app_reused"] = True
        return True

    def _show_error(self, msg: str):
        dialog = customtkinter.CTkToplevel(self)
        dialog.title(t("\u30a8\u30e9\u30fc", "Error"))
        dialog.geometry("400x150")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        # Center relative to main window
        self.update_idletasks()
        x = self.winfo_x() + (700 - 400) // 2
        y = self.winfo_y() + (550 - 150) // 2
        dialog.geometry(f"+{x}+{y}")

        customtkinter.CTkLabel(
            dialog, text=msg, wraplength=360
        ).pack(padx=20, pady=(20, 10))
        customtkinter.CTkButton(
            dialog, text="OK", width=80, command=dialog.destroy
        ).pack(pady=(0, 15))

    # ── Naming validators ─────────────────────────────────────────────
    def _validate_uc_name(self, name: str) -> tuple[bool, str]:
        """Delegate to core for consistent UC name rules across CLI/GUI."""
        return core.validate_uc_object_name(name)

    def _maxlen_vcmd(self, max_len: int):
        """Return a tkinter validatecommand tuple that prevents typing past max_len.

        Used as `validate="key", validatecommand=self._maxlen_vcmd(N)` on Entry widgets.
        Programmatic `.insert()` is NOT blocked by tk's validatecommand under validate="key"
        (it bypasses validation), so default-fill via insert() still works as long as the
        default itself is shorter than max_len.
        """
        def _check(new_value: str) -> bool:
            return len(new_value) <= max_len
        return (self.register(_check), "%P")

    # ── 既存リソース確認ダイアログ ────────────────────────────────────
    def _resource_exists(self, kind: str, name: str) -> bool:
        """指定名のリソースがワークスペースに既に存在するか同期的に確認する。

        kind: catalog / schema / warehouse / vs_endpoint / lakebase / app
        """
        token = self.data.get("token", "")
        host = self.data.get("host", "")
        if not token or not host:
            return False
        try:
            if kind == "catalog":
                r = core.api_get(f"/api/2.1/unity-catalog/catalogs/{name}", token, host)
                return isinstance(r, dict) and "error" not in r
            if kind == "schema":
                cat = self.data.get("catalog", "")
                if not cat:
                    return False
                r = core.api_get(f"/api/2.1/unity-catalog/schemas/{cat}.{name}", token, host)
                return isinstance(r, dict) and "error" not in r
            if kind == "warehouse":
                r = core.api_get("/api/2.0/sql/warehouses", token, host)
                if isinstance(r, dict) and "warehouses" in r:
                    return any(w.get("name") == name for w in r["warehouses"])
                return False
            if kind == "vs_endpoint":
                r = core.api_get(f"/api/2.0/vector-search/endpoints/{name}", token, host)
                return isinstance(r, dict) and "error" not in r and r.get("name") == name
            if kind == "lakebase":
                profile = self.data.get("profile", "")
                if not profile:
                    return False
                w = core.get_workspace_client(profile)
                if w is None:
                    return False
                try:
                    w.postgres.get_project(project_id=name)
                    return True
                except Exception:
                    return False
            if kind == "app":
                r = core.api_get(f"/api/2.0/apps/{name}", token, host)
                return isinstance(r, dict) and "error" not in r
        except Exception:
            return False
        return False

    def _confirm_use_existing(self, kind_label_ja: str, kind_label_en: str, name: str) -> bool:
        """同名リソースが既存の場合に「再利用するか／別名にするか」を尋ねるモーダルダイアログ。

        Returns:
            True  — ユーザーが「はい（既存を使う）」を選択 → 次へ進む
            False — ユーザーが「いいえ（別名で作成）」を選択 → 現在ページに留まる
        """
        dialog = customtkinter.CTkToplevel(self)
        dialog.title(t("既存リソースの確認", "Existing resource detected"))
        dialog.geometry("520x200")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        # 中央表示
        self.update_idletasks()
        x = self.winfo_x() + (700 - 520) // 2
        y = self.winfo_y() + (550 - 200) // 2
        dialog.geometry(f"+{x}+{y}")

        msg = t(
            f"同じ名前の{kind_label_ja}「{name}」が既に存在します。\n\n"
            "「はい」: 既存のリソースをそのまま使用して次へ進む\n"
            "「いいえ」: このページに戻って別の名前を入力する",
            f"A {kind_label_en} named '{name}' already exists.\n\n"
            "Yes: Reuse the existing resource and proceed\n"
            "No: Stay on this page and choose a different name",
        )
        customtkinter.CTkLabel(
            dialog, text=msg, wraplength=480, justify="left",
        ).pack(padx=20, pady=(20, 10))

        result = {"value": False}

        def _yes():
            result["value"] = True
            dialog.destroy()

        def _no():
            result["value"] = False
            dialog.destroy()

        btn_frame = customtkinter.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=(5, 15))
        customtkinter.CTkButton(
            btn_frame, text=t("はい（既存を使う）", "Yes (use existing)"),
            command=_yes, width=180,
        ).pack(side="left", padx=8)
        customtkinter.CTkButton(
            btn_frame, text=t("いいえ（別名にする）", "No (different name)"),
            command=_no, width=180, fg_color="gray",
        ).pack(side="left", padx=8)

        self.wait_window(dialog)
        return result["value"]

    def _validate_lakebase_name(self, name: str, kind: str = "project") -> tuple[bool, str]:
        """Validate a Lakebase project/branch name.

        Rules:
        - Must not be empty
        - Can contain lowercase letters, digits, hyphens
        - Must start with a letter
        - No underscores, uppercase, spaces, or special characters
        - Length limits:
          - project: 56 chars (so auto-branch `{project}-branch` fits in 63)
          - branch:  63 chars (Lakebase API limit)
        """
        import re
        if not name:
            return False, t("名前を入力してください", "Name is required")
        max_len = (
            core.LAKEBASE_PROJECT_MAX_LENGTH if kind == "project"
            else core.LAKEBASE_BRANCH_MAX_LENGTH
        )
        if len(name) > max_len:
            return False, t(
                f"{max_len} 文字以内にしてください（現在 {len(name)} 文字）",
                f"Must be ≤ {max_len} chars (currently {len(name)})",
            )
        if not re.match(r'^[a-z]', name):
            return False, t("先頭は英小文字で始めてください", "Must start with a lowercase letter")
        if not re.match(r'^[a-z0-9-]+$', name):
            return False, t(
                "英小文字・数字・ハイフンのみ使用できます",
                "Only lowercase letters, digits, and hyphens allowed"
            )
        return True, ""

    # ════════════════════════════════════════════════════════════════════
    #  PAGE BUILDERS
    # ════════════════════════════════════════════════════════════════════

    # ── Page 1: Language ────────────────────────────────────────────────
    def _page_language(self, frame: customtkinter.CTkFrame):
        customtkinter.CTkLabel(
            frame, text="Language / \u8a00\u8a9e\u9078\u629e",
            font=customtkinter.CTkFont(size=22, weight="bold"),
        ).pack(pady=(30, 20))

        customtkinter.CTkLabel(
            frame,
            text=t(
                "\u30bb\u30c3\u30c8\u30a2\u30c3\u30d7\u30a6\u30a3\u30b6\u30fc\u30c9\u3067\u4f7f\u7528\u3059\u308b\u8a00\u8a9e\u3092\u9078\u629e\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
                "Select the language for the setup wizard.",
            ),
            wraplength=500,
        ).pack(pady=(0, 20))

        self._lang_var = customtkinter.StringVar(value=self.data["lang"])

        customtkinter.CTkRadioButton(
            frame,
            text="\u65e5\u672c\u8a9e",
            variable=self._lang_var,
            value="ja",
            font=customtkinter.CTkFont(size=16),
            command=self._on_lang_change,
        ).pack(pady=10)

        customtkinter.CTkRadioButton(
            frame,
            text="English",
            variable=self._lang_var,
            value="en",
            font=customtkinter.CTkFont(size=16),
            command=self._on_lang_change,
        ).pack(pady=10)

    def _on_lang_change(self):
        lang = self._lang_var.get()
        self.data["lang"] = lang
        core.set_language(lang)
        # Rebuild current page to refresh labels
        self.show_page(self.current_page)

    # ── Page 2: Databricks Authentication ───────────────────────────────
    def _page_auth(self, frame: customtkinter.CTkFrame):
        customtkinter.CTkLabel(
            frame,
            text=t("Databricks 認証", "Databricks Authentication"),
            font=customtkinter.CTkFont(size=22, weight="bold"),
        ).pack(pady=(20, 5))

        # Prerequisites check (run once)
        if not self.data.get("prereqs_ok"):
            prereqs = core.check_prerequisites()
            missing = core.check_missing_prerequisites(prereqs)
            if missing:
                warn_text = t(
                    "⚠ 不足ツール: " + ", ".join(missing),
                    "⚠ Missing tools: " + ", ".join(missing),
                )
                customtkinter.CTkLabel(
                    frame, text=warn_text, text_color="orange", wraplength=550,
                ).pack(pady=(0, 5), padx=40)
            else:
                self.data["prereqs_ok"] = True

        profiles = core.get_databricks_profiles()
        profile_names = [p["name"] for p in profiles]

        # Force first-login UI even when profiles exist (for adding new workspace)
        if self.data.get("_force_first_login"):
            profile_names = []

        if not profile_names:
            # 初回ユーザー: OAuth ログインフロー
            customtkinter.CTkLabel(
                frame,
                text=t(
                    "Databricks プロファイルが見つかりません。\n初回ログインをセットアップします。",
                    "No Databricks profiles found.\nLet's set up your first login.",
                ),
                text_color="orange",
                wraplength=550,
            ).pack(pady=(10, 5))

            customtkinter.CTkLabel(
                frame,
                text=t("Databricks ワークスペース URL:",
                         "Databricks workspace URL:"),
            ).pack(pady=(5, 2), anchor="w", padx=40)

            self._host_entry = customtkinter.CTkEntry(
                frame, width=480,
                placeholder_text="https://your-workspace.cloud.databricks.com",
            )
            self._host_entry.pack(pady=(0, 5), padx=40)

            self._new_profile_entry_label = customtkinter.CTkLabel(
                frame, text=t("プロファイル名 [DEFAULT]:",
                                "Profile name [DEFAULT]:"),
            )
            self._new_profile_entry_label.pack(pady=(5, 2), anchor="w", padx=40)

            self._new_profile_entry = customtkinter.CTkEntry(
                frame, width=480, placeholder_text="DEFAULT",
            )
            self._new_profile_entry.pack(pady=(0, 10), padx=40)

            self._login_button = customtkinter.CTkButton(
                frame,
                text=t("ブラウザでログイン", "Log in via browser"),
                width=220,
                command=self._on_first_login,
            )
            self._login_button.pack(pady=5)

            self._auth_status = customtkinter.CTkLabel(
                frame, text=t(
                    "💡 ボタンを押すとブラウザが開き、Databricks にログインします。",
                    "💡 Clicking the button will open your browser to log in to Databricks.",
                ),
                text_color="gray",
                wraplength=540,
            )
            self._auth_status.pack(pady=5)
            return

        customtkinter.CTkLabel(
            frame, text=t("\u30d7\u30ed\u30d5\u30a1\u30a4\u30eb\u3092\u9078\u629e:", "Select profile:"),
        ).pack(pady=(5, 2), anchor="w", padx=40)

        self._profile_var = customtkinter.StringVar(
            value=self.data.get("profile_name") or (profile_names[0] if profile_names else "")
        )
        customtkinter.CTkOptionMenu(
            frame,
            variable=self._profile_var,
            values=profile_names,
            width=400,
        ).pack(pady=(0, 10), padx=40)

        customtkinter.CTkButton(
            frame,
            text=t("\u63a5\u7d9a", "Connect"),
            width=200,
            command=self._on_connect,
        ).pack(pady=10)

        # Allow logging into a different workspace (creates a new profile)
        def _switch_to_first_login():
            self.data["_force_first_login"] = True
            self.show_page(self.current_page)

        customtkinter.CTkButton(
            frame,
            text=t(
                "\u5225\u306e\u30ef\u30fc\u30af\u30b9\u30da\u30fc\u30b9\u306b\u30ed\u30b0\u30a4\u30f3\uff08\u65b0\u898f\u30d7\u30ed\u30d5\u30a1\u30a4\u30eb\u3092\u8ffd\u52a0\uff09",
                "Log in to a different workspace (add new profile)",
            ),
            width=320,
            fg_color="transparent",
            border_width=1,
            text_color=("gray10", "gray90"),
            command=_switch_to_first_login,
        ).pack(pady=(0, 10))

        self._auth_status = customtkinter.CTkLabel(frame, text="", wraplength=500)
        self._auth_status.pack(pady=5)

        # Show previously successful auth
        if self.data.get("auth_ok"):
            self._auth_status.configure(
                text=t(
                    f"\u2713 \u8a8d\u8a3cOK: {self.data['username']} @ {self.data['host']}",
                    f"\u2713 Authenticated: {self.data['username']} @ {self.data['host']}",
                ),
                text_color="green",
            )

    def _on_first_login(self):
        """First-time user: run `databricks auth login` with host."""
        host = self._host_entry.get().strip()
        profile = self._new_profile_entry.get().strip() or "DEFAULT"

        if not host:
            self._auth_status.configure(
                text=t("✗ ホスト URL を入力してください", "✗ Please enter a host URL"),
                text_color="red",
            )
            return
        if not host.startswith("http"):
            host = f"https://{host}"

        self._login_button.configure(
            state="disabled",
            text=t("ブラウザでログイン中...", "Logging in via browser..."),
        )
        self._auth_status.configure(
            text=t(
                "ブラウザが開きます。ログインが完了したらターミナルも確認してください。",
                "Your browser will open. Check the terminal too after you finish logging in.",
            ),
            text_color="yellow",
        )
        self.update_idletasks()

        def _run_login():
            try:
                result = subprocess.run(
                    ["databricks", "auth", "login",
                     "--profile", profile, "--host", host],
                    timeout=300,
                )
                self._login_result_queue.put(("done", result.returncode, profile))
            except Exception as e:
                self._login_result_queue.put(("error", str(e), profile))

        if not hasattr(self, "_login_result_queue"):
            import queue as _q
            self._login_result_queue = _q.Queue()
        import threading
        threading.Thread(target=_run_login, daemon=True).start()
        self.after(500, self._check_login_result)

    def _check_login_result(self):
        import queue as _q
        try:
            kind, *rest = self._login_result_queue.get_nowait()
            if kind == "done":
                rc, profile = rest
                if rc == 0:
                    self._auth_status.configure(
                        text=t(f"✓ ログイン成功。プロファイル '{profile}' を保存しました。検証中...",
                                 f"✓ Login succeeded. Profile '{profile}' saved. Validating..."),
                        text_color="green",
                    )
                    # 自動的に finalize: ホスト・ユーザー名・トークンを取得して
                    # auth_ok=True に設定。再度ユーザーが Connect を押す必要なし。
                    # 1 秒後にページ再描画して、認証 OK の状態を表示
                    self.data["_force_first_login"] = False
                    def _autofinalize():
                        # First refresh page to get the post-login UI (profile dropdown)
                        self.show_page(self.current_page)
                        # Now select the just-created profile and finalize
                        if hasattr(self, "_profile_var"):
                            self._profile_var.set(profile)
                        self._finalize_auth(profile)
                    self.after(1000, _autofinalize)
                else:
                    self._login_button.configure(
                        state="normal",
                        text=t("ブラウザでログイン", "Log in via browser"),
                    )
                    self._auth_status.configure(
                        text=t(f"✗ ログイン失敗 (exit {rc})",
                                 f"✗ Login failed (exit {rc})"),
                        text_color="red",
                    )
            else:  # error
                err_msg = rest[0]
                self._login_button.configure(
                    state="normal",
                    text=t("ブラウザでログイン", "Log in via browser"),
                )
                self._auth_status.configure(
                    text=t(f"✗ エラー: {err_msg[:200]}",
                             f"✗ Error: {err_msg[:200]}"),
                    text_color="red",
                )
        except _q.Empty:
            # まだ結果なし → 再度チェック
            self.after(500, self._check_login_result)

    def _on_connect(self):
        profile = self._profile_var.get()
        self._auth_status.configure(
            text=t("\u691c\u8a3c\u4e2d...", "Validating..."), text_color="white"
        )
        self.update_idletasks()

        if not core.validate_profile(profile):
            # \u30c8\u30fc\u30af\u30f3\u671f\u9650\u5207\u308c\u7b49\u3067\u691c\u8a3c\u5931\u6557 \u2192 \u81ea\u52d5\u7684\u306b\u518d\u30ed\u30b0\u30a4\u30f3\u3092\u5b9f\u884c
            # \uff08\u30e6\u30fc\u30b6\u30fc\u306b\u30bf\u30fc\u30df\u30ca\u30eb\u3067\u30b3\u30de\u30f3\u30c9\u3092\u6253\u305f\u305b\u306a\u3044\uff09
            self._start_relogin(profile)
            return

        self._finalize_auth(profile)

    def _start_relogin(self, profile: str):
        """\u65e2\u5b58\u30d7\u30ed\u30d5\u30a1\u30a4\u30eb\u306e\u30c8\u30fc\u30af\u30f3\u304c\u5207\u308c\u3066\u3044\u308b\u5834\u5408\u306b
        `databricks auth login --profile <profile>` \u3092\u81ea\u52d5\u3067\u5b9f\u884c\u3059\u308b\u3002"""
        self._auth_status.configure(
            text=t(
                f"\u30d7\u30ed\u30d5\u30a1\u30a4\u30eb '{profile}' \u306e\u30c8\u30fc\u30af\u30f3\u304c\u5207\u308c\u3066\u3044\u308b\u53ef\u80fd\u6027\u304c\u3042\u308a\u307e\u3059\u3002\n"
                "\u30d6\u30e9\u30a6\u30b6\u3092\u958b\u3044\u3066\u518d\u30ed\u30b0\u30a4\u30f3\u3057\u307e\u3059...",
                f"Profile '{profile}' token may be expired.\n"
                "Opening browser to re-authenticate...",
            ),
            text_color="yellow",
        )
        self.update_idletasks()

        if not hasattr(self, "_login_result_queue"):
            import queue as _q
            self._login_result_queue = _q.Queue()

        def _run_relogin():
            try:
                result = subprocess.run(
                    ["databricks", "auth", "login", "--profile", profile],
                    timeout=300,
                )
                self._login_result_queue.put(("relogin_done", result.returncode, profile))
            except Exception as e:
                self._login_result_queue.put(("relogin_error", str(e), profile))

        import threading
        threading.Thread(target=_run_relogin, daemon=True).start()
        self.after(500, self._check_relogin_result)

    def _check_relogin_result(self):
        import queue as _q
        try:
            kind, *rest = self._login_result_queue.get_nowait()
        except _q.Empty:
            self.after(500, self._check_relogin_result)
            return

        if kind == "relogin_done":
            rc, profile = rest
            if rc == 0 and core.validate_profile(profile):
                self._finalize_auth(profile)
            else:
                self.data["auth_ok"] = False
                msg_jp = (f"\u2717 \u518d\u30ed\u30b0\u30a4\u30f3\u306b\u5931\u6557\u3057\u307e\u3057\u305f (exit {rc})\u3002"
                          f"\u5225\u306e\u30d7\u30ed\u30d5\u30a1\u30a4\u30eb\u3092\u9078\u629e\u3059\u308b\u304b\u3001"
                          f"`databricks auth login --profile {profile}` \u3092\u30bf\u30fc\u30df\u30ca\u30eb\u3067\u5b9f\u884c\u3057\u3066\u304f\u3060\u3055\u3044\u3002")
                msg_en = (f"\u2717 Re-login failed (exit {rc}). "
                          f"Try another profile or run "
                          f"`databricks auth login --profile {profile}` in your terminal.")
                self._auth_status.configure(text=t(msg_jp, msg_en), text_color="red")
        elif kind == "relogin_error":
            err_msg = rest[0]
            self.data["auth_ok"] = False
            self._auth_status.configure(
                text=t(f"\u2717 \u518d\u30ed\u30b0\u30a4\u30f3\u4e2d\u306b\u30a8\u30e9\u30fc: {err_msg[:200]}",
                       f"\u2717 Error during re-login: {err_msg[:200]}"),
                text_color="red",
            )

    def _finalize_auth(self, profile: str):
        """\u691c\u8a3c\u6210\u529f\u5f8c\u306e\u5171\u901a\u51e6\u7406: data \u66f4\u65b0 + \u30c7\u30d5\u30a9\u30eb\u30c8\u5024\u30d7\u30ec\u30d5\u30a3\u30eb + \u30b9\u30c6\u30fc\u30bf\u30b9\u8868\u793a\u3002"""
        self.data["profile_name"] = profile
        self.data["host"] = core.get_databricks_host(profile)
        try:
            self.data["username"] = core.get_databricks_username(profile)
        except SystemExit:
            self._auth_status.configure(
                text=t("\u2717 \u30e6\u30fc\u30b6\u30fc\u540d\u306e\u53d6\u5f97\u306b\u5931\u6557", "\u2717 Failed to get username"),
                text_color="red",
            )
            return
        try:
            self.data["token"] = core.get_auth_token(profile)
        except Exception:
            self._auth_status.configure(
                text=t("\u2717 \u30c8\u30fc\u30af\u30f3\u306e\u53d6\u5f97\u306b\u5931\u6557", "\u2717 Failed to get token"),
                text_color="red",
            )
            return

        self.data["auth_ok"] = True
        self.data["lakebase_required"] = core.check_lakebase_required()

        # Pre-fill defaults — fm_handson_{user} catalog + ai_assistant_{user} schema
        if not self.data["catalog"]:
            self.data["catalog"] = core.compute_default_catalog_name(self.data.get("username", ""))
        if not self.data["schema"]:
            self.data["schema"] = core.compute_default_schema_name(self.data.get("username", ""))
        if not self.data["mlflow_base_name"]:
            self.data["mlflow_base_name"] = f"/Users/{self.data['username']}/fm-agent"

        self._auth_status.configure(
            text=t(
                f"\u2713 \u8a8d\u8a3cOK: {self.data['username']} @ {self.data['host']}",
                f"\u2713 Authenticated: {self.data['username']} @ {self.data['host']}",
            ),
            text_color="green",
        )

    # ── Page 3: Catalog ───────────────────────────────────────────────
    def _page_catalog(self, frame: customtkinter.CTkFrame):
        customtkinter.CTkLabel(
            frame,
            text=t("カタログ", "Catalog"),
            font=customtkinter.CTkFont(size=22, weight="bold"),
        ).pack(pady=(20, 10))

        # 既存カタログ一覧キャッシュ — ページ初回のみフェッチする
        if not hasattr(self, "_catalogs_cache"):
            self._catalogs_cache = None

        self._catalog_mode_var = customtkinter.StringVar(
            value=self.data.get("_catalog_mode", "existing")
        )

        customtkinter.CTkRadioButton(
            frame,
            text=t("既存のカタログから選択", "Select from existing"),
            variable=self._catalog_mode_var,
            value="existing",
            command=self._rebuild_catalog_fields,
        ).pack(pady=5, padx=40, anchor="w")

        customtkinter.CTkRadioButton(
            frame,
            text=t("新規作成", "Create new"),
            variable=self._catalog_mode_var,
            value="new",
            command=self._rebuild_catalog_fields,
        ).pack(pady=5, padx=40, anchor="w")

        self._catalog_fields_frame = customtkinter.CTkFrame(frame)
        self._catalog_fields_frame.pack(fill="x", padx=40, pady=10)

        self._rebuild_catalog_fields()

    def _rebuild_catalog_fields(self):
        for w in self._catalog_fields_frame.winfo_children():
            w.destroy()

        mode = self._catalog_mode_var.get()
        self.data["_catalog_mode"] = mode

        if mode == "existing":
            # Fetch catalogs via Unity Catalog REST API (no permission filter — too slow)
            # キャッシュがあれば再フェッチしない
            if self._catalogs_cache is not None:
                catalogs = self._catalogs_cache
            else:
                token = self.data.get("token", "")
                host = self.data.get("host", "")
                catalogs: list[str] = []
                if token and host:
                    try:
                        result = core.api_get("/api/2.1/unity-catalog/catalogs", token, host)
                        for cat in result.get("catalogs", []):
                            catalogs.append(cat.get("name", ""))
                        catalogs = [c for c in catalogs if c]
                        catalogs.sort()
                    except Exception:
                        pass
                self._catalogs_cache = catalogs

            if not catalogs:
                customtkinter.CTkLabel(
                    self._catalog_fields_frame,
                    text=t(
                        "カタログを取得できませんでした。\n認証設定を確認してください。",
                        "Could not fetch catalogs.\nPlease check authentication settings.",
                    ),
                    text_color="orange",
                    wraplength=400,
                ).pack(pady=10)
                return

            customtkinter.CTkLabel(
                self._catalog_fields_frame,
                text=t("カタログを選択:", "Select catalog:"),
            ).pack(anchor="w", pady=(5, 2))

            # Pre-select: current value, env value, or first
            env_val = core.get_env_value("CATALOG") or self.data.get("catalog", "")
            default = catalogs[0]
            if env_val in catalogs:
                default = env_val

            self._catalog_dropdown_var = customtkinter.StringVar(value=default)
            customtkinter.CTkOptionMenu(
                self._catalog_fields_frame,
                variable=self._catalog_dropdown_var,
                values=catalogs,
                width=400,
                command=self._on_catalog_dropdown_change,
            ).pack(pady=(0, 5))

            # Store initial selection
            self.data["catalog"] = default

        else:
            # New catalog
            customtkinter.CTkLabel(
                self._catalog_fields_frame,
                text=t("カタログ名:", "Catalog name:"),
            ).pack(anchor="w", pady=(5, 2))

            # デフォルト値の決定優先度（重要）:
            # 1. .env の CATALOG 値（再開時の継続性のため）
            # 2. 「新規」モードで前回ユーザーが手動編集した値（_catalog_new_typed）
            # 3. ユーザー名ベース自動生成（fm_handson_{user}）
            #
            # 注: self.data["catalog"] は「既存」モードでドロップダウン選択された値が
            # 入っているケースがあるため、ここでは使わない（モード切替時に既存リストの
            # 先頭が新規入力欄に出てしまうバグの原因だった）。
            env_val = (
                core.get_env_value("CATALOG")
                or self.data.get("_catalog_new_typed", "")
                or core.compute_default_catalog_name(self.data.get("username", ""))
            )

            self._catalog_entry = customtkinter.CTkEntry(
                self._catalog_fields_frame, width=400,
                validate="key",
                validatecommand=self._maxlen_vcmd(core.UC_NAME_MAX_LENGTH),
            )
            self._catalog_entry.pack(pady=(0, 5))
            self._catalog_entry.insert(0, env_val)
            self.data["catalog"] = env_val
            self.data["_catalog_new_typed"] = env_val

            self._catalog_validation_label = customtkinter.CTkLabel(
                self._catalog_fields_frame, text="", wraplength=400,
            )
            self._catalog_validation_label.pack(anchor="w")

            self._catalog_entry.bind("<KeyRelease>", lambda _: self._on_catalog_entry_change())

            # 即時バリデーション（pre-fill 済み）
            self._on_catalog_entry_change()

    def _on_catalog_dropdown_change(self, selection: str):
        self.data["catalog"] = selection

    def _on_catalog_entry_change(self):
        name = self._catalog_entry.get().strip()
        self.data["catalog"] = name
        # 「新規」モードで手動編集された値を保持（モード切替時に復元するため）
        self.data["_catalog_new_typed"] = name
        valid, msg = self._validate_uc_name(name)
        if valid:
            self._catalog_validation_label.configure(
                text=t("✓ 有効な名前です", "✓ Valid name"),
                text_color="green",
            )
        else:
            self._catalog_validation_label.configure(
                text=msg,
                text_color="red",
            )

    def _sync_catalog(self):
        self.data["catalog"] = self._catalog_entry.get().strip()

    # ── Page 4: Schema Name ─────────────────────────────────────────────
    def _page_schema(self, frame: customtkinter.CTkFrame):
        customtkinter.CTkLabel(
            frame,
            text=t("スキーマ名", "Schema Name"),
            font=customtkinter.CTkFont(size=22, weight="bold"),
        ).pack(pady=(20, 10))

        customtkinter.CTkLabel(
            frame,
            text=t(
                "データを格納するスキーマ名を入力してください。",
                "Enter the schema name where data will be stored.",
            ),
            wraplength=500,
        ).pack(pady=(0, 10))

        # デフォルト値: .env > 既存 self.data > `retail_agent_{user}`（複数ユーザー間の衝突回避）
        env_val = core.get_env_value("SCHEMA") or self.data.get("schema", "")
        if not env_val:
            env_val = core.compute_default_schema_name(self.data.get("username", ""))

        self._schema_entry = customtkinter.CTkEntry(
            frame, width=400,
            validate="key",
            validatecommand=self._maxlen_vcmd(core.UC_NAME_MAX_LENGTH),
        )
        self._schema_entry.pack(pady=10, padx=40)
        self._schema_entry.insert(0, env_val)
        self.data["schema"] = env_val

        self._schema_validation_label = customtkinter.CTkLabel(
            frame, text="", wraplength=400,
        )
        self._schema_validation_label.pack(padx=40, anchor="w")

        self._schema_entry.bind("<KeyRelease>", lambda _: self._on_schema_entry_change())

        # Run initial validation if there's a pre-filled value
        if env_val:
            self._on_schema_entry_change()

    def _on_schema_entry_change(self):
        name = self._schema_entry.get().strip()
        self.data["schema"] = name
        valid, msg = self._validate_uc_name(name)
        if valid:
            self._schema_validation_label.configure(
                text=t("✓ 有効な名前です", "✓ Valid name"),
                text_color="green",
            )
        else:
            self._schema_validation_label.configure(
                text=msg,
                text_color="red",
            )

    def _sync_schema(self):
        self.data["schema"] = self._schema_entry.get().strip()

    # ── Page 5: SQL Warehouse ───────────────────────────────────────────
    def _page_warehouse(self, frame: customtkinter.CTkFrame):
        customtkinter.CTkLabel(
            frame,
            text=t("SQL Warehouse の選択", "Select SQL Warehouse"),
            font=customtkinter.CTkFont(size=22, weight="bold"),
        ).pack(pady=(20, 10))

        # 既存ウェアハウス一覧キャッシュ — ページ初回表示でのみフェッチ。
        # モード切替ごとに再フェッチすると遅延 / ハングの原因になるため。
        if not hasattr(self, "_warehouses_cache"):
            self._warehouses_cache = None

        self._wh_mode_var = customtkinter.StringVar(
            value=self.data.get("_wh_mode", "existing")
        )
        customtkinter.CTkRadioButton(
            frame,
            text=t("既存のウェアハウスから選択（推奨）",
                   "Select from existing (recommended)"),
            variable=self._wh_mode_var,
            value="existing",
            command=self._rebuild_wh_fields,
        ).pack(pady=5, padx=40, anchor="w")
        customtkinter.CTkRadioButton(
            frame,
            text=t(
                "新規作成（Serverless Pro X-Small、自動停止 60 分。作成 1〜2 分）",
                "Create new (Serverless Pro X-Small, auto-stop 60min. Takes 1-2 min)",
            ),
            variable=self._wh_mode_var,
            value="new",
            command=self._rebuild_wh_fields,
        ).pack(pady=5, padx=40, anchor="w")

        self._wh_fields_frame = customtkinter.CTkFrame(frame)
        self._wh_fields_frame.pack(fill="x", padx=40, pady=10)
        self._rebuild_wh_fields()

    def _rebuild_wh_fields(self):
        for w in self._wh_fields_frame.winfo_children():
            w.destroy()
        mode = self._wh_mode_var.get()
        self.data["_wh_mode"] = mode
        if mode == "existing":
            self._render_wh_existing()
        else:
            self._render_wh_new()

    def _render_wh_existing(self):
        # キャッシュがあれば再フェッチしない（モード切替の度にハング防止）
        if self._warehouses_cache is not None:
            self._warehouses = self._warehouses_cache
        else:
            loading = customtkinter.CTkLabel(
                self._wh_fields_frame,
                text=t("使用権限のあるウェアハウスを検索中...",
                       "Checking which warehouses you can use..."),
                text_color="gray",
            )
            loading.pack(pady=5)
            self.update_idletasks()

            token = self.data.get("token", "")
            host = self.data.get("host", "")
            user = self.data.get("username", "")
            try:
                self._warehouses = core.filter_usable_warehouses(
                    self.data["profile_name"], token, host, user
                )
            except Exception:
                self._warehouses = []
            self._warehouses_cache = self._warehouses
            loading.destroy()

        if not self._warehouses:
            customtkinter.CTkLabel(
                self._wh_fields_frame,
                text=t(
                    "使用権限のあるウェアハウスが見つかりませんでした。\n「新規作成」を選択するか、管理者に CAN_USE 以上を依頼してください。",
                    "No warehouses found where you have CAN_USE permission.\nPlease choose 'Create new' or ask admin for CAN_USE+.",
                ),
                text_color="orange",
                wraplength=500,
                justify="left",
            ).pack(pady=10)
            return

        labels = [
            f"{w.get('name', '?')} ({w.get('id', '?')}) "
            f"[{w.get('state', '?')}] [{w.get('_user_permission', '')}]"
            for w in self._warehouses
        ]
        default_label = labels[0]
        for i, w in enumerate(self._warehouses):
            if w.get("state") == "RUNNING":
                default_label = labels[i]
                break
        self._wh_var = customtkinter.StringVar(value=default_label)
        customtkinter.CTkOptionMenu(
            self._wh_fields_frame,
            variable=self._wh_var, values=labels, width=500,
            command=self._on_wh_change,
        ).pack(pady=10, padx=10)
        self._on_wh_change(default_label)

    def _render_wh_new(self):
        customtkinter.CTkLabel(
            self._wh_fields_frame,
            text=t("新規ウェアハウス名:",
                   "New warehouse name:"),
        ).pack(anchor="w", pady=(5, 2))

        # デフォルト名の優先度:
        # 1. 「新規」モードで前回ユーザーが入力した値 (_warehouse_new_typed)
        # 2. ユーザー名 + 日付ベース (compute_default_warehouse_name)
        # 注: self.data["warehouse_name"] は「既存」モードで選んだ値が入っているため使わない。
        default_name = (
            self.data.get("_warehouse_new_typed")
            or core.compute_default_warehouse_name(self.data.get("username", ""))
        )
        self._wh_new_name_entry = customtkinter.CTkEntry(
            self._wh_fields_frame, width=400,
            validate="key",
            validatecommand=self._maxlen_vcmd(core.SQL_WAREHOUSE_NAME_MAX_LENGTH),
        )
        self._wh_new_name_entry.insert(0, default_name)
        # 即座に self.data に反映（次へ押したときに参照される）
        self.data["warehouse_name"] = default_name
        self.data["_warehouse_new_typed"] = default_name
        # 手動編集を捕捉
        self._wh_new_name_entry.bind(
            "<KeyRelease>", lambda _: self.data.update({
                "warehouse_name": self._wh_new_name_entry.get().strip(),
                "_warehouse_new_typed": self._wh_new_name_entry.get().strip(),
            })
        )
        self._wh_new_name_entry.pack(pady=(0, 10))

        customtkinter.CTkLabel(
            self._wh_fields_frame,
            text=t(
                "・ サイズ: X-Small（Serverless Pro）\n・ 自動停止: 60 分\n・ 作成所要: 1〜2 分（セットアップ実行時に作成）",
                "・ Size: X-Small (Serverless Pro)\n・ Auto-stop: 60 min\n・ Creation time: 1-2 min (created during setup execution)",
            ),
            text_color="gray",
            justify="left",
        ).pack(anchor="w", pady=5)

        self.data["warehouse_id"] = ""
        self.data["warehouse_name"] = default_name
        self.data["_warehouse_create_pending"] = True

    def _on_wh_change(self, selection: str):
        for w in self._warehouses:
            label = (
                f"{w.get('name', '?')} ({w.get('id', '?')}) "
                f"[{w.get('state', '?')}] [{w.get('_user_permission', '')}]"
            )
            if label == selection:
                self.data["warehouse_id"] = w["id"]
                self.data["warehouse_name"] = w.get("name", "")
                self.data["_warehouse_create_pending"] = False
                break

    # ── Page 6: Vector Search Endpoint ──────────────────────────────────
    def _page_vs_endpoint(self, frame: customtkinter.CTkFrame):
        customtkinter.CTkLabel(
            frame,
            text=t("Vector Search エンドポイントの選択", "Select Vector Search Endpoint"),
            font=customtkinter.CTkFont(size=22, weight="bold"),
        ).pack(pady=(20, 10))

        # 既存 VS エンドポイント一覧キャッシュ — ページ初回のみフェッチ
        if not hasattr(self, "_vs_endpoints_cache"):
            self._vs_endpoints_cache = None

        self._ep_mode_var = customtkinter.StringVar(
            value=self.data.get("_ep_mode", "existing")
        )
        customtkinter.CTkRadioButton(
            frame,
            text=t("既存のエンドポイントから選択（推奨）",
                   "Select from existing (recommended)"),
            variable=self._ep_mode_var,
            value="existing",
            command=self._rebuild_ep_fields,
        ).pack(pady=5, padx=40, anchor="w")
        customtkinter.CTkRadioButton(
            frame,
            text=t(
                "新規作成（タイプ STANDARD。作成完了まで 10〜15 分かかります）",
                "Create new (type STANDARD. Provisioning takes 10-15 min)",
            ),
            variable=self._ep_mode_var,
            value="new",
            command=self._rebuild_ep_fields,
        ).pack(pady=5, padx=40, anchor="w")

        self._ep_fields_frame = customtkinter.CTkFrame(frame)
        self._ep_fields_frame.pack(fill="x", padx=40, pady=10)
        self._rebuild_ep_fields()

    def _rebuild_ep_fields(self):
        for w in self._ep_fields_frame.winfo_children():
            w.destroy()
        mode = self._ep_mode_var.get()
        self.data["_ep_mode"] = mode
        if mode == "existing":
            self._render_ep_existing()
        else:
            self._render_ep_new()

    def _render_ep_existing(self):
        # キャッシュがあれば再フェッチしない（モード切替ハング防止）
        if self._vs_endpoints_cache is not None:
            self._vs_endpoints = self._vs_endpoints_cache
        else:
            token = self.data.get("token", "")
            host = self.data.get("host", "")
            self._vs_endpoints = []
            if token and host:
                data = core.api_get("/api/2.0/vector-search/endpoints", token, host)
                if isinstance(data, dict):
                    self._vs_endpoints = data.get("endpoints", [])
                state_order = {"ONLINE": 0, "PROVISIONING": 1}
                self._vs_endpoints.sort(
                    key=lambda e: (
                        state_order.get(e.get("endpoint_status", {}).get("state", ""), 9),
                        e.get("name", ""),
                    )
                )
            self._vs_endpoints_cache = self._vs_endpoints

        if not self._vs_endpoints:
            customtkinter.CTkLabel(
                self._ep_fields_frame,
                text=t(
                    "既存のエンドポイントが見つかりませんでした。\n「新規作成」を選択してください。",
                    "No existing endpoints found.\nPlease choose 'Create new'.",
                ),
                text_color="orange",
                wraplength=500,
                justify="left",
            ).pack(pady=10)
            return

        labels = [
            f"{e.get('name', '?')} [{e.get('endpoint_status', {}).get('state', '?')}]"
            for e in self._vs_endpoints
        ]
        default_label = labels[0]
        for i, e in enumerate(self._vs_endpoints):
            if e.get("endpoint_status", {}).get("state") == "ONLINE":
                default_label = labels[i]
                break
        self._ep_var = customtkinter.StringVar(value=default_label)
        customtkinter.CTkOptionMenu(
            self._ep_fields_frame,
            variable=self._ep_var, values=labels, width=500,
            command=self._on_ep_change,
        ).pack(pady=10, padx=10)
        self._on_ep_change(default_label)

    def _render_ep_new(self):
        customtkinter.CTkLabel(
            self._ep_fields_frame,
            text=t("新規エンドポイント名:", "New endpoint name:"),
        ).pack(anchor="w", pady=(5, 2))

        # デフォルト名の優先度:
        # 1. 「新規」モードで前回ユーザーが入力した値 (_ep_new_typed)
        # 2. ユーザー名 + 日付ベース (compute_default_vs_endpoint_name)
        # 注: self.data["vs_endpoint"] は「既存」モードで選んだ値が入っているため使わない。
        default_name = (
            self.data.get("_ep_new_typed")
            or core.compute_default_vs_endpoint_name(self.data.get("username", ""))
        )
        self._ep_new_name_entry = customtkinter.CTkEntry(
            self._ep_fields_frame, width=400,
            validate="key",
            validatecommand=self._maxlen_vcmd(core.VS_ENDPOINT_NAME_MAX_LENGTH),
        )
        self._ep_new_name_entry.insert(0, default_name)
        self._ep_new_name_entry.pack(pady=(0, 10))
        # 手動編集を捕捉
        self._ep_new_name_entry.bind(
            "<KeyRelease>", lambda _: self.data.update({
                "vs_endpoint": self._ep_new_name_entry.get().strip(),
                "_ep_new_typed": self._ep_new_name_entry.get().strip(),
            })
        )

        customtkinter.CTkLabel(
            self._ep_fields_frame,
            text=t(
                "・ タイプ: STANDARD\n・ 作成所要: 10〜15 分（コーヒーブレイクをどうぞ）\n・ セットアップ実行時に作成・待機します",
                "・ Type: STANDARD\n・ Provisioning: 10-15 min (coffee break time)\n・ Created and awaited during setup execution",
            ),
            text_color="gray",
            justify="left",
        ).pack(anchor="w", pady=5)

        self.data["vs_endpoint"] = default_name
        self.data["_ep_new_typed"] = default_name
        self.data["_ep_create_pending"] = True

    def _on_ep_change(self, selection: str):
        for e in self._vs_endpoints:
            label = f"{e.get('name', '?')} [{e.get('endpoint_status', {}).get('state', '?')}]"
            if label == selection:
                self.data["vs_endpoint"] = e["name"]
                self.data["_ep_create_pending"] = False
                break

    # ── Page 7: Genie Space ──────────────────────────────────────────────
    def _page_genie(self, frame: customtkinter.CTkFrame):
        customtkinter.CTkLabel(
            frame,
            text="Genie Space",
            font=customtkinter.CTkFont(size=22, weight="bold"),
        ).pack(pady=(20, 10))

        customtkinter.CTkLabel(
            frame,
            text=t(
                "Genie Space は構造化データに対して自然言語クエリを実行するためのツールです。",
                "Genie Space enables natural language queries against structured data.",
            ),
            wraplength=550,
        ).pack(pady=(0, 10), padx=40, anchor="w")

        self._genie_mode_var = customtkinter.StringVar(
            value=self.data.get("genie_mode", "new")
        )

        customtkinter.CTkRadioButton(
            frame,
            text=t("新規作成（API で自動作成）", "Create new (auto-create via API)"),
            variable=self._genie_mode_var,
            value="new",
            command=self._rebuild_genie_fields,
        ).pack(pady=5, padx=40, anchor="w")

        customtkinter.CTkRadioButton(
            frame,
            text=t("既存の Genie Space ID を入力", "Enter existing Genie Space ID"),
            variable=self._genie_mode_var,
            value="existing",
            command=self._rebuild_genie_fields,
        ).pack(pady=5, padx=40, anchor="w")

        self._genie_fields_frame = customtkinter.CTkFrame(frame)
        self._genie_fields_frame.pack(fill="x", padx=40, pady=10)

        self._rebuild_genie_fields()

    def _rebuild_genie_fields(self):
        for w in self._genie_fields_frame.winfo_children():
            w.destroy()

        mode = self._genie_mode_var.get()
        self.data["genie_mode"] = mode

        if mode == "new":
            customtkinter.CTkLabel(
                self._genie_fields_frame,
                text=t(
                    "※ セットアップ実行時に自動作成されます。",
                    "* Will be auto-created during setup execution.",
                ),
                text_color="gray",
            ).pack(anchor="w", pady=5)
        else:
            customtkinter.CTkLabel(
                self._genie_fields_frame,
                text=t("Genie Space ID:", "Genie Space ID:"),
            ).pack(anchor="w", pady=(5, 2))
            self._genie_id_entry = customtkinter.CTkEntry(
                self._genie_fields_frame, width=400,
                placeholder_text="e.g. 01ef...abcd",
            )
            self._genie_id_entry.pack(pady=(0, 5))
            if self.data.get("genie_space_id"):
                self._genie_id_entry.insert(0, self.data["genie_space_id"])
            self._genie_id_entry.bind("<KeyRelease>", lambda _: self._sync_genie_id())

    def _sync_genie_id(self):
        self.data["genie_space_id"] = self._genie_id_entry.get().strip()

    # ── Page 8: Lakebase Setup ──────────────────────────────────────────
    def _page_lakebase(self, frame: customtkinter.CTkFrame):
        customtkinter.CTkLabel(
            frame,
            text=t("Lakebase \u8a2d\u5b9a", "Lakebase Setup"),
            font=customtkinter.CTkFont(size=22, weight="bold"),
        ).pack(pady=(20, 10))

        if not self.data.get("lakebase_required"):
            customtkinter.CTkLabel(
                frame,
                text=t(
                    "\u3053\u306e\u30c6\u30f3\u30d7\u30ec\u30fc\u30c8\u3067\u306f Lakebase \u306f\u4e0d\u8981\u3067\u3059\u3002\u6b21\u3078\u9032\u3093\u3067\u304f\u3060\u3055\u3044\u3002",
                    "Lakebase is not required for this template. Please proceed.",
                ),
                wraplength=500,
            ).pack(pady=20)
            return

        self._lb_mode_var = customtkinter.StringVar(
            value=self.data.get("lakebase_mode", "new")
        )

        customtkinter.CTkRadioButton(
            frame,
            text=t("\u65b0\u898f\u4f5c\u6210", "Create new"),
            variable=self._lb_mode_var,
            value="new",
            command=self._rebuild_lakebase_fields,
        ).pack(pady=5, padx=40, anchor="w")

        customtkinter.CTkRadioButton(
            frame,
            text=t("\u65e2\u5b58\u3092\u4f7f\u7528", "Use existing"),
            variable=self._lb_mode_var,
            value="existing",
            command=self._rebuild_lakebase_fields,
        ).pack(pady=5, padx=40, anchor="w")

        self._lb_fields_frame = customtkinter.CTkFrame(frame)
        self._lb_fields_frame.pack(fill="x", padx=40, pady=10)

        self._rebuild_lakebase_fields()

    def _rebuild_lakebase_fields(self):
        for w in self._lb_fields_frame.winfo_children():
            w.destroy()

        mode = self._lb_mode_var.get()
        self.data["lakebase_mode"] = mode

        if mode == "new":
            customtkinter.CTkLabel(
                self._lb_fields_frame,
                text=t("プロジェクト名:", "Project name:"),
            ).pack(anchor="w", pady=(5, 2))

            # デフォルト名の優先度:
            # 1. 「新規」モードで前回ユーザーが入力した値 (_lb_new_typed)
            # 2. ユーザー名 + 日付ベース (compute_default_lakebase_project_name)
            # 注: self.data["lakebase_project"] は「既存」モードで入力された値が入って
            #     いる可能性があるため、ここでは使わない。
            username = self.data.get("username", "") or "user"
            default_proj = (
                self.data.get("_lb_new_typed")
                or core.compute_default_lakebase_project_name(username)
            )
            self.data["lakebase_project"] = default_proj
            self.data["_lb_new_typed"] = default_proj

            self._lb_proj_entry = customtkinter.CTkEntry(
                self._lb_fields_frame, width=400,
                validate="key",
                validatecommand=self._maxlen_vcmd(core.LAKEBASE_PROJECT_MAX_LENGTH),
            )
            self._lb_proj_entry.pack(pady=(0, 5))
            self._lb_proj_entry.insert(0, default_proj)

            self._lb_proj_validation_label = customtkinter.CTkLabel(
                self._lb_fields_frame, text="", wraplength=400,
            )
            self._lb_proj_validation_label.pack(anchor="w")

            self._lb_proj_entry.bind("<KeyRelease>", lambda _: self._on_lb_proj_change())

            # 初期値があるので即時バリデーション
            self._on_lb_proj_change()

            customtkinter.CTkLabel(
                self._lb_fields_frame,
                text=t(
                    "※ 実際の作成はセットアップ実行時 (Step 11) に行われます。",
                    "* Actual creation happens during setup execution (Step 11).",
                ),
                text_color="gray",
                wraplength=400,
            ).pack(anchor="w")
        else:
            customtkinter.CTkLabel(
                self._lb_fields_frame,
                text=t("プロジェクト名:", "Project name:"),
            ).pack(anchor="w", pady=(5, 2))
            self._lb_proj_entry = customtkinter.CTkEntry(
                self._lb_fields_frame, width=400,
                validate="key",
                validatecommand=self._maxlen_vcmd(core.LAKEBASE_PROJECT_MAX_LENGTH),
            )
            self._lb_proj_entry.pack(pady=(0, 5))
            # 「既存」モードの自分の typed slot のみから復元（モード間漏洩を避ける）
            existing_typed = self.data.get("_lb_existing_typed", "")
            if existing_typed:
                self._lb_proj_entry.insert(0, existing_typed)
                self.data["lakebase_project"] = existing_typed

            self._lb_proj_validation_label = customtkinter.CTkLabel(
                self._lb_fields_frame, text="", wraplength=400,
            )
            self._lb_proj_validation_label.pack(anchor="w")

            self._lb_proj_entry.bind("<KeyRelease>", lambda _: self._on_lb_proj_change())

            # Run initial validation if there's a pre-filled value
            if existing_typed:
                self._on_lb_proj_change()

            customtkinter.CTkLabel(
                self._lb_fields_frame,
                text=t("ブランチ名（空欄で個人ブランチ自動作成）:",
                         "Branch name (leave empty for auto-generated personal branch):"),
            ).pack(anchor="w", pady=(5, 2))

            # デフォルト値: {project}-{username-slug}
            username = self.data.get("username", "")
            user_slug = username.split("@")[0].replace(".", "-").lower() if username else "member"
            project = self.data.get("lakebase_project", "")
            default_branch = f"{project}-{user_slug}" if project else ""

            self._lb_branch_entry = customtkinter.CTkEntry(
                self._lb_fields_frame, width=400,
                placeholder_text=default_branch or "e.g. fresh-mart-alice",
                validate="key",
                validatecommand=self._maxlen_vcmd(core.LAKEBASE_BRANCH_MAX_LENGTH),
            )
            self._lb_branch_entry.pack(pady=(0, 5))
            existing = self.data.get("lakebase_branch") or default_branch
            if existing:
                self._lb_branch_entry.insert(0, existing)
                self.data["lakebase_branch"] = existing
            self._lb_branch_entry.bind("<KeyRelease>", lambda _: self._sync_lb_branch())

            customtkinter.CTkLabel(
                self._lb_fields_frame,
                text=t(
                    "💡 存在しないブランチ名なら新規作成、既存なら使用（要権限）",
                    "💡 Non-existing name → creates new branch; existing → uses it (requires permissions)"),
                text_color="gray",
                wraplength=400,
            ).pack(anchor="w", pady=(3, 0))

    def _on_lb_proj_change(self):
        name = self._lb_proj_entry.get().strip()
        self.data["lakebase_project"] = name
        # 現在のモードに応じて新規 / 既存の typed-value スロットを保持する
        mode = self.data.get("lakebase_mode", "new")
        if mode == "new":
            self.data["_lb_new_typed"] = name
        else:
            self.data["_lb_existing_typed"] = name
        valid, msg = self._validate_lakebase_name(name)
        if valid:
            self._lb_proj_validation_label.configure(
                text=t("✓ 有効な名前です", "✓ Valid name"),
                text_color="green",
            )
        else:
            self._lb_proj_validation_label.configure(
                text=msg,
                text_color="red",
            )

    def _sync_lb_project(self):
        self.data["lakebase_project"] = self._lb_proj_entry.get().strip()

    def _sync_lb_branch(self):
        self.data["lakebase_branch"] = self._lb_branch_entry.get().strip()

    # ── Page 8: MLflow Experiment ───────────────────────────────────────
    def _page_mlflow(self, frame: customtkinter.CTkFrame):
        customtkinter.CTkLabel(
            frame,
            text="MLflow Experiment",
            font=customtkinter.CTkFont(size=22, weight="bold"),
        ).pack(pady=(20, 10))

        self._mlflow_mode_var = customtkinter.StringVar(
            value=self.data.get("mlflow_mode", "new")
        )

        customtkinter.CTkRadioButton(
            frame,
            text=t("\u65b0\u898f\u4f5c\u6210", "Create new"),
            variable=self._mlflow_mode_var,
            value="new",
            command=self._rebuild_mlflow_fields,
        ).pack(pady=5, padx=40, anchor="w")

        customtkinter.CTkRadioButton(
            frame,
            text=t("\u65e2\u5b58 ID \u3092\u5165\u529b", "Enter existing IDs"),
            variable=self._mlflow_mode_var,
            value="existing",
            command=self._rebuild_mlflow_fields,
        ).pack(pady=5, padx=40, anchor="w")

        self._mlflow_fields_frame = customtkinter.CTkFrame(frame)
        self._mlflow_fields_frame.pack(fill="x", padx=40, pady=10)

        self._rebuild_mlflow_fields()

    def _rebuild_mlflow_fields(self):
        for w in self._mlflow_fields_frame.winfo_children():
            w.destroy()

        mode = self._mlflow_mode_var.get()
        self.data["mlflow_mode"] = mode

        if mode == "new":
            customtkinter.CTkLabel(
                self._mlflow_fields_frame,
                text=t("\u30d9\u30fc\u30b9\u540d:", "Base name:"),
            ).pack(anchor="w", pady=(5, 2))

            self._mlflow_base_entry = customtkinter.CTkEntry(
                self._mlflow_fields_frame, width=400,
                placeholder_text="e.g. /Users/you/freshmart-agent",
            )
            self._mlflow_base_entry.pack(pady=(0, 5))
            if self.data.get("mlflow_base_name"):
                self._mlflow_base_entry.insert(0, self.data["mlflow_base_name"])
            self._mlflow_base_entry.bind("<KeyRelease>", lambda _: self._sync_mlflow_base())

            customtkinter.CTkLabel(
                self._mlflow_fields_frame,
                text=t(
                    "{name}-monitoring \u3068 {name}-evaluation \u304c\u4f5c\u6210\u3055\u308c\u307e\u3059\u3002",
                    "{name}-monitoring and {name}-evaluation will be created.",
                ),
                text_color="gray",
                wraplength=400,
            ).pack(anchor="w")
        else:
            customtkinter.CTkLabel(
                self._mlflow_fields_frame,
                text=t("\u30e2\u30cb\u30bf\u30ea\u30f3\u30b0 Experiment ID:", "Monitoring Experiment ID:"),
            ).pack(anchor="w", pady=(5, 2))
            self._mon_id_entry = customtkinter.CTkEntry(
                self._mlflow_fields_frame, width=400,
            )
            self._mon_id_entry.pack(pady=(0, 5))
            if self.data.get("monitoring_id"):
                self._mon_id_entry.insert(0, self.data["monitoring_id"])
            self._mon_id_entry.bind("<KeyRelease>", lambda _: self._sync_mon_id())

            customtkinter.CTkLabel(
                self._mlflow_fields_frame,
                text=t("\u8a55\u4fa1 Experiment ID:", "Evaluation Experiment ID:"),
            ).pack(anchor="w", pady=(5, 2))
            self._eval_id_entry = customtkinter.CTkEntry(
                self._mlflow_fields_frame, width=400,
            )
            self._eval_id_entry.pack(pady=(0, 5))
            if self.data.get("eval_id"):
                self._eval_id_entry.insert(0, self.data["eval_id"])
            self._eval_id_entry.bind("<KeyRelease>", lambda _: self._sync_eval_id())

            # Button to detect existing trace destination
            customtkinter.CTkButton(
                self._mlflow_fields_frame,
                text=t("トレース設定を検出", "Detect trace settings"),
                width=200,
                command=self._detect_existing_trace,
            ).pack(pady=(10, 5))

            self._trace_detect_label = customtkinter.CTkLabel(
                self._mlflow_fields_frame, text="", wraplength=400,
            )
            self._trace_detect_label.pack()

    def _detect_existing_trace(self):
        """Check if existing experiment already has Delta Table tracing configured."""
        mon_id = self.data.get("monitoring_id", "").strip()
        if not mon_id:
            self._trace_detect_label.configure(
                text=t("モニタリング Experiment ID を先に入力してください",
                        "Enter Monitoring Experiment ID first"),
                text_color="orange",
            )
            return

        profile = self.data.get("profile_name", "")
        try:
            result = core.run_command(
                ["databricks", "experiments", "get-experiment", mon_id, "-p", profile, "-o", "json"],
                check=False,
            )
            if result.returncode == 0:
                import json as _json
                exp_data = _json.loads(result.stdout)
                tags = exp_data.get("experiment", exp_data).get("tags", [])
                for tag in tags:
                    if tag.get("key") == "mlflow.experiment.databricksTraceDestinationPath":
                        dest = tag.get("value", "")
                        self.data["existing_trace_dest"] = dest
                        self.data["trace_dest_mode"] = "delta"
                        self.data["trace_dest_schema"] = dest
                        self._trace_detect_label.configure(
                            text=t(f"✓ Delta Table トレース検出: {dest}",
                                    f"✓ Delta Table tracing detected: {dest}"),
                            text_color="green",
                        )
                        return
                self._trace_detect_label.configure(
                    text=t("トレース設定なし（MLflow Experiment デフォルト）",
                            "No trace config found (MLflow Experiment default)"),
                    text_color="gray",
                )
            else:
                self._trace_detect_label.configure(
                    text=t("Experiment が見つかりません。ID を確認してください。",
                            "Experiment not found. Please check the ID."),
                    text_color="orange",
                )
        except Exception as e:
            self._trace_detect_label.configure(text=str(e)[:100], text_color="red")

    def _sync_mlflow_base(self):
        self.data["mlflow_base_name"] = self._mlflow_base_entry.get().strip()

    def _sync_mon_id(self):
        self.data["monitoring_id"] = self._mon_id_entry.get().strip()

    def _sync_eval_id(self):
        self.data["eval_id"] = self._eval_id_entry.get().strip()

    # ── Page 9: Trace Destination ───────────────────────────────────────
    def _page_trace(self, frame: customtkinter.CTkFrame):
        customtkinter.CTkLabel(
            frame,
            text=t("\u30c8\u30ec\u30fc\u30b9\u9001\u4fe1\u5148", "Trace Destination"),
            font=customtkinter.CTkFont(size=22, weight="bold"),
        ).pack(pady=(20, 10))

        self._trace_mode_var = customtkinter.StringVar(
            value=self.data.get("trace_dest_mode", "mlflow")
        )

        customtkinter.CTkRadioButton(
            frame,
            text="MLflow Experiment (default)",
            variable=self._trace_mode_var,
            value="mlflow",
            command=self._rebuild_trace_fields,
        ).pack(pady=5, padx=40, anchor="w")

        customtkinter.CTkRadioButton(
            frame,
            text="Unity Catalog Delta Table",
            variable=self._trace_mode_var,
            value="delta",
            command=self._rebuild_trace_fields,
        ).pack(pady=5, padx=40, anchor="w")

        self._trace_fields_frame = customtkinter.CTkFrame(frame)
        self._trace_fields_frame.pack(fill="x", padx=40, pady=10)

        self._rebuild_trace_fields()

    def _rebuild_trace_fields(self):
        for w in self._trace_fields_frame.winfo_children():
            w.destroy()

        mode = self._trace_mode_var.get()
        self.data["trace_dest_mode"] = mode

        if mode == "delta":
            default_schema = f"{self.data.get('catalog', '')}.{self.data.get('schema', '')}"
            customtkinter.CTkLabel(
                self._trace_fields_frame,
                text=t("\u9001\u4fe1\u5148\u30b9\u30ad\u30fc\u30de:", "Destination schema:"),
            ).pack(anchor="w", pady=(5, 2))
            self._trace_schema_entry = customtkinter.CTkEntry(
                self._trace_fields_frame, width=400,
            )
            self._trace_schema_entry.pack(pady=(0, 5))
            val = self.data.get("trace_dest_schema") or default_schema
            if val:
                self._trace_schema_entry.insert(0, val)
                self.data["trace_dest_schema"] = val  # sync immediately
            self._trace_schema_entry.bind("<KeyRelease>", lambda _: self._sync_trace_schema())

    def _sync_trace_schema(self):
        self.data["trace_dest_schema"] = self._trace_schema_entry.get().strip()

    # ── Page 10: Prompt Registry ──────────────────────────────────────────
    def _page_prompt_registry(self, frame: customtkinter.CTkFrame):
        customtkinter.CTkLabel(
            frame,
            text="Prompt Registry",
            font=customtkinter.CTkFont(size=22, weight="bold"),
        ).pack(pady=(20, 10))

        customtkinter.CTkLabel(
            frame,
            text=t(
                "システムプロンプトの管理方法を選択してください。\n"
                "Prompt Registry を使用すると、バージョン管理・A/Bテスト・\n"
                "ロールバックが可能になります。",
                "Select how to manage system prompts.\n"
                "Prompt Registry enables version control, A/B testing,\n"
                "and rollback capabilities."
            ),
            wraplength=550,
            justify="left",
        ).pack(pady=(0, 15), padx=40, anchor="w")

        self._prompt_registry_var = customtkinter.StringVar(
            value=self.data.get("use_prompt_registry", "no")
        )

        customtkinter.CTkRadioButton(
            frame,
            text=t("使用しない（ハードコード版、設定不要）",
                    "Don't use (hardcoded, no setup needed)"),
            variable=self._prompt_registry_var,
            value="no",
            command=lambda: self.data.update({"use_prompt_registry": "no"}),
        ).pack(pady=5, padx=40, anchor="w")

        customtkinter.CTkRadioButton(
            frame,
            text=t("Unity Catalog Prompt Registry を使用",
                    "Use Unity Catalog Prompt Registry"),
            variable=self._prompt_registry_var,
            value="yes",
            command=lambda: self.data.update({"use_prompt_registry": "yes"}),
        ).pack(pady=5, padx=40, anchor="w")

    # ── Page 11: LLM Endpoint ───────────────────────────────────────────
    def _page_llm_endpoint(self, frame: customtkinter.CTkFrame):
        customtkinter.CTkLabel(
            frame,
            text=t("LLM エンドポイント", "LLM Endpoint"),
            font=customtkinter.CTkFont(size=22, weight="bold"),
        ).pack(pady=(20, 5))

        customtkinter.CTkLabel(
            frame,
            text=t(
                "エージェントが使用する Foundation Model API のチャットモデルを選択してください。\n"
                "推奨デフォルト: databricks-claude-sonnet-4-6",
                "Choose the Foundation Model API chat model the agent will use.\n"
                "Recommended default: databricks-claude-sonnet-4-6",
            ),
            wraplength=580,
            justify="left",
            text_color="gray",
        ).pack(pady=(0, 10), padx=40)

        # Fetch chat models
        loading = customtkinter.CTkLabel(
            frame,
            text=t("利用可能なチャット LLM エンドポイントを取得中...",
                   "Fetching available chat LLM endpoints..."),
            text_color="gray",
        )
        loading.pack(pady=5)
        self.update_idletasks()

        token = self.data.get("token", "")
        host = self.data.get("host", "")
        models: list[dict] = []
        if token and host:
            try:
                models = core.list_chat_models(token, host)
            except Exception:
                models = []

        loading.destroy()

        if not models:
            customtkinter.CTkLabel(
                frame,
                text=t(
                    "利用可能なチャット LLM エンドポイントが見つかりませんでした。\n"
                    "FM API がワークスペースで有効か確認してください。",
                    "No chat-task LLM endpoints found.\n"
                    "Please verify Foundation Model API is enabled.",
                ),
                text_color="orange",
                wraplength=520,
                justify="left",
            ).pack(pady=20)

            # Allow manual entry as a fallback
            customtkinter.CTkLabel(
                frame,
                text=t("エンドポイント名を手動入力:", "Or enter endpoint name manually:"),
            ).pack(pady=(5, 2))
            self._llm_manual_entry = customtkinter.CTkEntry(frame, width=400)
            self._llm_manual_entry.insert(
                0, self.data.get("llm_endpoint") or core.DEFAULT_LLM_ENDPOINT
            )
            self._llm_manual_entry.pack(pady=(0, 10))
            self.data["_llm_models_available"] = False
            return

        names = [m.get("name", "") for m in models if m.get("name")]
        self.data["_llm_models_available"] = True

        # Default selection logic
        recommended = core.DEFAULT_LLM_ENDPOINT
        previously = self.data.get("llm_endpoint", "")
        if previously and previously in names:
            default_value = previously
        elif recommended in names:
            default_value = recommended
        else:
            default_value = names[0]

        # Notice when recommended default is unavailable
        if recommended not in names:
            customtkinter.CTkLabel(
                frame,
                text=t(
                    f"⚠ 推奨デフォルト '{recommended}' はこのワークスペースにありません。"
                    " 別のモデルを選んでください。",
                    f"⚠ Recommended default '{recommended}' is not available here."
                    " Please pick another model.",
                ),
                text_color="orange",
                wraplength=560,
                justify="left",
            ).pack(pady=(0, 5), padx=40)

        # Make the dropdown labels show "★ recommended" when applicable
        labels = []
        for name in names:
            if name == recommended:
                labels.append(f"{name}  ★ (推奨デフォルト)")
            else:
                labels.append(name)
        # Map label → endpoint name
        self._llm_label_to_name = {lbl: name for lbl, name in zip(labels, names)}
        default_label = next(
            (lbl for lbl, n in zip(labels, names) if n == default_value),
            labels[0],
        )

        customtkinter.CTkLabel(
            frame,
            text=t("モデルを選択:", "Select a model:"),
        ).pack(pady=(5, 2))

        self._llm_var = customtkinter.StringVar(value=default_label)
        customtkinter.CTkOptionMenu(
            frame, variable=self._llm_var, values=labels, width=500,
            command=self._on_llm_change,
        ).pack(pady=(0, 10), padx=40)

        # Initialize data
        self._on_llm_change(default_label)

    def _on_llm_change(self, label: str):
        name = getattr(self, "_llm_label_to_name", {}).get(label, label)
        self.data["llm_endpoint"] = name

    # ── Page 12: App Name ───────────────────────────────────
    def _page_app_name(self, frame: customtkinter.CTkFrame):
        customtkinter.CTkLabel(
            frame,
            text=t("Databricks App 名", "Databricks App Name"),
            font=customtkinter.CTkFont(size=22, weight="bold"),
        ).pack(pady=(20, 5))

        customtkinter.CTkLabel(
            frame,
            text=t(
                "デプロイする Databricks App の名前を設定します。\n"
                "デフォルト: fm-agent-{username}-{MMDD}\n"
                "制約: 小文字英数字とハイフン、英字で始まり英数で終わる、30文字以内。",
                "Set the name of the Databricks App to deploy.\n"
                "Default: fm-agent-{username}-{MMDD}\n"
                "Constraints: lowercase alphanumeric+hyphen, start with letter, end with alphanumeric, ≤30 chars.",
            ),
            wraplength=580,
            justify="left",
            text_color="gray",
        ).pack(pady=(0, 10), padx=40)

        # Compute default
        username = self.data.get("username", "") or self.data.get("user_email", "") or "user"
        default_name = self.data.get("app_name") or core.compute_default_app_name(username)
        self.data.setdefault("app_name", default_name)

        customtkinter.CTkLabel(
            frame,
            text=t("App 名:", "App name:"),
        ).pack(pady=(5, 2))

        self._app_name_entry = customtkinter.CTkEntry(
            frame, width=500,
            validate="key",
            validatecommand=self._maxlen_vcmd(core.APP_NAME_MAX_LENGTH),
        )
        self._app_name_entry.insert(0, default_name)
        self._app_name_entry.pack(pady=(0, 10), padx=40)

        # Reset to default helper button
        def _reset_to_default():
            d = core.compute_default_app_name(username)
            self._app_name_entry.delete(0, "end")
            self._app_name_entry.insert(0, d)

        customtkinter.CTkButton(
            frame,
            text=t("デフォルトに戻す", "Reset to default"),
            command=_reset_to_default,
            width=180,
        ).pack(pady=(2, 10))


    # ── Page 13: Summary ────────────────────────────────────────────────
    def _page_summary(self, frame: customtkinter.CTkFrame):
        customtkinter.CTkLabel(
            frame,
            text=t("\u8a2d\u5b9a\u78ba\u8a8d", "Configuration Summary"),
            font=customtkinter.CTkFont(size=22, weight="bold"),
        ).pack(pady=(20, 10))

        textbox = customtkinter.CTkTextbox(frame, width=600, height=340)
        textbox.pack(padx=20, pady=5)

        lines = [
            f"{t('\u30d7\u30ed\u30d5\u30a1\u30a4\u30eb', 'Profile')}: {self.data.get('profile_name', '')}",
            f"{t('\u30ef\u30fc\u30af\u30b9\u30da\u30fc\u30b9', 'Workspace')}: {self.data.get('host', '')}",
            f"{t('\u30e6\u30fc\u30b6\u30fc', 'User')}: {self.data.get('username', '')}",
            f"{t('\u30ab\u30bf\u30ed\u30b0', 'Catalog')}: {self.data.get('catalog', '')}",
            f"{t('\u30b9\u30ad\u30fc\u30de', 'Schema')}: {self.data.get('schema', '')}",
            f"{t('\u30a6\u30a7\u30a2\u30cf\u30a6\u30b9', 'Warehouse')}: {self.data.get('warehouse_name', '')} ({self.data.get('warehouse_id', '')})",
            f"{t('VS \u30a8\u30f3\u30c9\u30dd\u30a4\u30f3\u30c8', 'VS Endpoint')}: {self.data.get('vs_endpoint', '') or t('\u306a\u3057', 'None')}",
        ]

        genie_mode_label = t("新規作成", "Create new") if self.data.get("genie_mode") == "new" else t("既存 ID", "Existing ID")
        genie_id = self.data.get("genie_space_id", "")
        lines.append(f"Genie Space: {genie_mode_label}" + (f" ({genie_id})" if genie_id else ""))

        if self.data.get("lakebase_required"):
            mode_label = t("\u65b0\u898f\u4f5c\u6210", "Create new") if self.data.get("lakebase_mode") == "new" else t("\u65e2\u5b58", "Existing")
            lines.append(f"Lakebase: {mode_label} - {self.data.get('lakebase_project', '')} / {self.data.get('lakebase_branch', '')}")

        if self.data.get("mlflow_mode") == "new":
            lines.append(f"MLflow: {t('\u65b0\u898f\u4f5c\u6210', 'Create new')} ({self.data.get('mlflow_base_name', '')})")
        else:
            lines.append(f"MLflow: {t('\u65e2\u5b58 ID', 'Existing IDs')} ({self.data.get('monitoring_id', '')} / {self.data.get('eval_id', '')})")

        if self.data.get("trace_dest_mode") == "delta":
            lines.append(f"{t('\u30c8\u30ec\u30fc\u30b9\u9001\u4fe1\u5148', 'Trace Dest')}: Delta Table ({self.data.get('trace_dest_schema', '')})")
        else:
            lines.append(f"{t('\u30c8\u30ec\u30fc\u30b9\u9001\u4fe1\u5148', 'Trace Dest')}: MLflow Experiment")

        if self.data.get("use_prompt_registry") == "yes":
            lines.append(f"Prompt Registry: {t('\u4f7f\u7528\u3059\u308b', 'Enabled')}")
        else:
            lines.append(f"Prompt Registry: {t('\u4f7f\u7528\u3057\u306a\u3044', 'Disabled')}")

        lines.append(f"LLM Endpoint: {self.data.get('llm_endpoint', '')}")
        lines.append(f"App Name: {self.data.get('app_name', '')}")

        textbox.insert("0.0", "\n".join(lines))
        textbox.configure(state="disabled")

    # ── Page 11: Execute ────────────────────────────────────────────────
    def _page_execute(self, frame: customtkinter.CTkFrame):
        customtkinter.CTkLabel(
            frame,
            text=t("\u30bb\u30c3\u30c8\u30a2\u30c3\u30d7\u5b9f\u884c\u4e2d...", "Running Setup..."),
            font=customtkinter.CTkFont(size=22, weight="bold"),
        ).pack(pady=(15, 5))

        self._exec_progress = customtkinter.CTkProgressBar(frame, width=600)
        self._exec_progress.pack(padx=20, pady=5)
        self._exec_progress.set(0)

        self._exec_textbox = customtkinter.CTkTextbox(frame, width=620, height=320)
        self._exec_textbox.pack(padx=20, pady=5)
        self._exec_textbox.configure(state="disabled")

        # Auto-start execution
        if not self._exec_running and not self.data.get("setup_complete"):
            self._exec_running = True
            self.data["setup_log"] = []
            self.data["setup_failed_steps"] = []
            thread = threading.Thread(target=self._run_setup, daemon=True)
            thread.start()
            self.after(100, self._check_progress)

    def _log(self, msg: str):
        """Post a message to the queue (called from background thread)."""
        self._exec_queue.put(("log", msg))

    def _set_progress(self, value: float):
        """Post progress update (0.0 - 1.0) to the queue."""
        self._exec_queue.put(("progress", value))

    def _signal_done(self):
        self._exec_queue.put(("done", None))

    def _check_progress(self):
        """Poll the queue from the main thread and update UI."""
        try:
            while True:
                kind, data = self._exec_queue.get_nowait()
                if kind == "log":
                    self._exec_textbox.configure(state="normal")
                    self._exec_textbox.insert("end", data + "\n")
                    self._exec_textbox.see("end")
                    self._exec_textbox.configure(state="disabled")
                elif kind == "progress":
                    self._exec_progress.set(data)
                elif kind == "done":
                    self._exec_running = False
                    self.data["setup_complete"] = True
                    # Auto-advance to complete page (index 15)
                    self.after(500, lambda: self.show_page(15))
                    return
        except queue.Empty:
            pass

        if self._exec_running:
            self.after(100, self._check_progress)

    def _run_setup(self):
        """Execute all setup steps in a background thread."""
        s = self.data
        token = s["token"]
        host = s["host"]
        profile = s["profile_name"]
        username = s["username"]
        catalog = s["catalog"]
        schema = s["schema"]
        warehouse_id = s["warehouse_id"]
        vs_endpoint = s["vs_endpoint"]
        total_steps = 11
        step = 0

        # ロールバック用: 「新規作成された」リソースを記録
        # （ユーザーが「既存」を選択したものは含めない）
        s["created_resources"] = {
            "catalog": None,         # set if user chose "new" mode for catalog
            "schema": None,          # workshop-specific schema name (always tracked)
            "warehouse_id": None,    # set if user chose "new" mode for warehouse
            "vs_endpoint": None,     # set if user chose "new" mode for VS endpoint
            "genie_space_id": None,
            "vs_index": None,
            "lakebase_branch": None,
            "lakebase_project": None,
            "monitoring_id": None,
            "eval_id": None,
        }

        # Track newly-created catalog/schema based on mode flag from the GUI
        if s.get("_catalog_mode") == "new":
            s["created_resources"]["catalog"] = catalog
        # Schema is always workshop-specific so we always track it for rollback
        s["created_resources"]["schema"] = f"{catalog}.{schema}"

        class _AbortSetup(Exception):
            pass

        def advance(step_name: str):
            nonlocal step
            step += 1
            self._set_progress(step / total_steps)
            self._log(f"\u2713 {step_name}")
            s["setup_log"].append(f"\u2713 {step_name}")

        def fail(step_name: str, err: str, fatal: bool = False):
            self._log(f"\u2717 {step_name}: {err}")
            s["setup_failed_steps"].append({"name": step_name, "error": err})
            s["setup_log"].append(f"\u2717 {step_name}: {err}")
            nonlocal step
            step += 1
            self._set_progress(step / total_steps)
            if fatal:
                self._log(t(
                    "\n⛔ 致命的なエラーのためセットアップを中断し、ロールバックを開始します...",
                    "\n⛔ Fatal error — aborting setup and rolling back...",
                ))
                raise _AbortSetup(step_name)

        try:
            self._log(t("セットアップを開始します...", "Starting setup..."))
            self._log(f"  Profile: {profile}, Host: {host[:50]}...")
            self._log(f"  Catalog: {catalog}, Schema: {schema}")
            self._log("")

            # Step 0: Create SQL warehouse if user opted to create new
            if s.get("_warehouse_create_pending"):
                wh_name = s.get("warehouse_name") or "freshmart-warehouse"
                self._log(t(
                    f"SQL ウェアハウス '{wh_name}' を新規作成中（1〜2 分）...",
                    f"Creating new SQL warehouse '{wh_name}' (1-2 min)..."
                ))
                wh_result = core.create_sql_warehouse(token, host, wh_name)
                if "error" in wh_result:
                    fail(
                        t("SQL ウェアハウス作成", "SQL warehouse creation"),
                        wh_result["error"][:200],
                        fatal=True,
                    )
                else:
                    new_wh_id = wh_result.get("id", "")
                    s["warehouse_id"] = new_wh_id
                    warehouse_id = new_wh_id
                    # 既存再利用（reused=True）の場合はロールバック対象外にする
                    if not wh_result.get("reused"):
                        s["created_resources"]["warehouse_id"] = new_wh_id
                        self._log(t(
                            f"  → ウェアハウス作成完了: {wh_name} ({new_wh_id})。起動を待機中...",
                            f"  → Created: {wh_name} ({new_wh_id}). Waiting for startup..."
                        ))
                        core.wait_for_warehouse_ready(profile, new_wh_id, timeout_sec=300)
                    else:
                        self._log(t(
                            f"  → 既存ウェアハウスを再利用: {wh_name} ({new_wh_id})",
                            f"  → Reusing existing warehouse: {wh_name} ({new_wh_id})"
                        ))
                    self._log("")

            # Step 1: Create catalog & schema
            self._log(t("カタログ・スキーマを作成中...", "Creating catalog & schema..."))
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    core.setup_env_file()
                    core.update_env_file("DATABRICKS_CONFIG_PROFILE", profile)
                    core.update_env_file("MLFLOW_TRACKING_URI", f'"databricks://{profile}"')
                    core.update_env_file("DATABRICKS_HOST", host)
                    core.create_catalog_schema(token, host, warehouse_id, catalog, schema)
                output = buf.getvalue()
                if output.strip():
                    self._log(output.strip())
                advance(t("\u30ab\u30bf\u30ed\u30b0\u30fb\u30b9\u30ad\u30fc\u30de\u4f5c\u6210\u5b8c\u4e86", "Catalog & schema created"))
            except Exception as e:
                fail(t("\u30ab\u30bf\u30ed\u30b0\u30fb\u30b9\u30ad\u30fc\u30de", "Catalog & schema"), str(e)[:200])

            # Step 2: Generate structured data
            self._log(t("\u69cb\u9020\u5316\u30c7\u30fc\u30bf\u3092\u751f\u6210\u4e2d\uff085\uff5e10\u5206\uff09...", "Generating structured data (5-10 min)..."))
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    core.generate_data(profile, warehouse_id, catalog, schema,
                                       token=token, host=host)
                output = buf.getvalue()
                if output.strip():
                    self._log(output.strip())
                advance(t("\u30c7\u30fc\u30bf\u751f\u6210\u5b8c\u4e86", "Data generated"))
            except Exception as e:
                fail(t("\u30c7\u30fc\u30bf\u751f\u6210", "Data generation"), str(e)[:200])

            # Step 3: Enable CDF
            self._log(t("Change Data Feed \u3092\u6709\u52b9\u5316\u4e2d...", "Enabling Change Data Feed..."))
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    core.enable_cdf(token, host, warehouse_id, catalog, schema)
                output = buf.getvalue()
                if output.strip():
                    self._log(output.strip())
                advance(t("CDF \u6709\u52b9\u5316\u5b8c\u4e86", "CDF enabled"))
            except Exception as e:
                fail(t("CDF", "CDF"), str(e)[:200])

            # Step 4 (pre): Create Vector Search endpoint if user opted to create new
            if s.get("_ep_create_pending") and vs_endpoint:
                self._log(t(
                    f"⏳ VS エンドポイント '{vs_endpoint}' を新規作成中（10〜15 分）...",
                    f"⏳ Creating new VS endpoint '{vs_endpoint}' (10-15 min)..."
                ))
                ep_result = core.create_vs_endpoint_new(token, host, vs_endpoint)
                if "error" in ep_result and "ALREADY_EXISTS" not in ep_result["error"]:
                    fail(
                        t("VS エンドポイント作成", "VS endpoint creation"),
                        ep_result["error"][:200],
                        fatal=True,
                    )
                else:
                    # 既存再利用ならロールバック対象外
                    if not ep_result.get("reused"):
                        s["created_resources"]["vs_endpoint"] = vs_endpoint
                    self._log(t(
                        "  Provisioning 中... ONLINE になるまで待機します（最大 25 分）",
                        "  Provisioning... waiting for ONLINE state (up to 25 min)"
                    ))
                    ok = core.wait_for_vs_endpoint_ready(
                        token, host, vs_endpoint, timeout_sec=1500
                    )
                    if ok:
                        self._log(t(f"  → ONLINE: {vs_endpoint}",
                                    f"  → ONLINE: {vs_endpoint}"))
                    else:
                        self._log(t(
                            f"  ⚠ タイムアウト（後続処理で再確認されます）: {vs_endpoint}",
                            f"  ⚠ Timeout (will re-check in subsequent steps): {vs_endpoint}"
                        ))

            # Step 4: Create Vector Search index
            vs_index = f"{catalog}.{schema}.policy_docs_index"
            if vs_endpoint:
                self._log(t("Vector Search \u30a4\u30f3\u30c7\u30c3\u30af\u30b9\u3092\u4f5c\u6210\u4e2d...", "Creating Vector Search index..."))
                # 既存かどうかを事前チェック（ロールバック対象外判定）
                _vs_name = f"{catalog}.{schema}.policy_docs_index"
                _existing_vs = core.api_get(
                    f"/api/2.0/vector-search/indexes/{_vs_name}", token, host)
                _vs_was_new = "error" in _existing_vs
                try:
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                        vs_index = core.create_vector_search_index(
                            token, host, catalog, schema, vs_endpoint)
                    output = buf.getvalue()
                    if output.strip():
                        self._log(output.strip())
                    s["vs_index"] = vs_index
                    # 既存だった場合はロールバック対象外
                    if _vs_was_new:
                        s["created_resources"]["vs_index"] = vs_index
                    advance(t(f"VS \u30a4\u30f3\u30c7\u30c3\u30af\u30b9: {vs_index}", f"VS index: {vs_index}"))
                except _AbortSetup:
                    raise
                except Exception as e:
                    s["vs_index"] = vs_index
                    fail(t("VS \u30a4\u30f3\u30c7\u30c3\u30af\u30b9", "VS index"), str(e)[:200], fatal=True)
            else:
                s["vs_index"] = vs_index
                self._log(t("\u26a0 VS \u30a8\u30f3\u30c9\u30dd\u30a4\u30f3\u30c8\u672a\u6307\u5b9a\uff08\u30a4\u30f3\u30c7\u30c3\u30af\u30b9\u306f\u624b\u52d5\u4f5c\u6210\u304c\u5fc5\u8981\uff09",
                           "\u26a0 VS endpoint not specified (manual index creation needed)"))
                step += 1
                self._set_progress(step / total_steps)

            # Step 5: Genie Space
            if s.get("genie_mode") == "existing" and s.get("genie_space_id"):
                # Existing Genie Space — verify it
                self._log(t("Genie Space を確認中...", "Verifying Genie Space..."))
                try:
                    result = core.api_get(
                        f"/api/2.0/genie/spaces/{s['genie_space_id']}", token, host)
                    if "error" not in result and result.get("space_id"):
                        title = result.get("title", "?")
                        advance(t(f"Genie Space 確認OK: {title} ({s['genie_space_id']})",
                                   f"Genie Space verified: {title} ({s['genie_space_id']})"))
                    else:
                        fail("Genie Space", t(
                            f"ID '{s['genie_space_id']}' が見つかりません",
                            f"ID '{s['genie_space_id']}' not found"))
                except Exception as e:
                    fail("Genie Space", str(e)[:200])
            else:
                # Create new Genie Space
                self._log(t("Genie Space を作成中...", "Creating Genie Space..."))
                try:
                    tables = ["customers", "products", "stores", "transactions",
                              "transaction_items", "payment_history"]
                    serialized = core._build_serialized_space(catalog, schema, tables)
                    body = {
                        "title": "フレッシュマート 小売データ",
                        "description": "フレッシュマートの小売データに対する自然言語クエリ。",
                        "warehouse_id": warehouse_id,
                        "serialized_space": serialized,
                    }
                    result = core.api_post("/api/2.0/genie/spaces", token, host, body)
                    genie_space_id = result.get("space_id", "")
                    if genie_space_id:
                        s["genie_space_id"] = genie_space_id
                        s["created_resources"]["genie_space_id"] = genie_space_id
                        advance(t(f"Genie Space 作成完了 (ID: {genie_space_id})",
                                   f"Genie Space created (ID: {genie_space_id})"))
                    else:
                        err_msg = str(result.get("error", "unknown"))[:100]
                        fail("Genie Space", err_msg)
                except Exception as e:
                    fail("Genie Space", str(e)[:200])

            # Step 6: Setup Lakebase
            lakebase_config = None
            if s.get("lakebase_required") and s.get("lakebase_project"):
                self._log(t("Lakebase を設定中...", "Setting up Lakebase..."))
                try:
                    lb_mode = s.get("lakebase_mode", "new")
                    project_name = s["lakebase_project"]
                    branch_name = s.get("lakebase_branch", "").strip()

                    # 入力ブランチが空ならデフォルト（個人ブランチ）を計算
                    user_slug = username.split("@")[0].replace(".", "-").lower()
                    default_branch = f"{project_name}-{user_slug}"
                    if not branch_name:
                        branch_name = default_branch

                    from databricks.sdk.service.postgres import (
                        Branch, BranchSpec, Project, ProjectSpec,
                    )
                    w = core.get_workspace_client(profile)

                    # プロジェクト存在確認
                    proj_check = core.api_get(
                        f"/api/2.0/postgres/projects/{project_name}", token, host,
                    )
                    project_exists = "error" not in proj_check

                    # ブランチ存在確認
                    branch_exists = False
                    if project_exists:
                        br_check = core.api_get(
                            f"/api/2.0/postgres/projects/{project_name}/branches/{branch_name}",
                            token, host,
                        )
                        branch_exists = "error" not in br_check

                    # 必要に応じて作成
                    if not project_exists and lb_mode == "new":
                        self._log(t(f"  プロジェクト {project_name} を作成中...",
                                     f"  Creating project {project_name}..."))
                        project_op = w.postgres.create_project(
                            project=Project(spec=ProjectSpec(display_name=project_name)),
                            project_id=project_name,
                        )
                        created_proj = project_op.wait()
                        # プロジェクト作成成功直後に追跡対象に登録
                        # （後続のブランチ作成で失敗しても確実にロールバックされるよう）
                        s["created_resources"]["lakebase_project"] = project_name
                        parent_name = created_proj.name
                        project_exists = True
                    elif project_exists:
                        parent_name = f"projects/{project_name}"
                    else:
                        fail("Lakebase", t(f"プロジェクト {project_name} が存在しません",
                                            f"Project {project_name} does not exist"))
                        raise RuntimeError("project missing")

                    if not branch_exists:
                        self._log(t(f"  ブランチ {branch_name} を作成中（production から fork）...",
                                     f"  Creating branch {branch_name} (forked from production)..."))
                        branch_op = w.postgres.create_branch(
                            parent=parent_name,
                            branch=Branch(spec=BranchSpec(no_expiry=True)),
                            branch_id=branch_name,
                        )
                        created_branch = branch_op.wait()
                        branch_name = (
                            created_branch.name.split("/branches/")[-1]
                            if "/branches/" in created_branch.name
                            else branch_name
                        )
                        # ブランチ作成成功直後に追跡対象に登録
                        s["created_resources"]["lakebase_branch"] = branch_name
                        self._log(t(f"  ブランチ作成完了: {branch_name}",
                                     f"  Branch created: {branch_name}"))

                    s["lakebase_project"] = project_name
                    s["lakebase_branch"] = branch_name

                    # branch_kind 検出
                    if branch_name == default_branch:
                        branch_kind = "personal"
                    elif branch_exists:
                        branch_kind = "entered-existing"
                    else:
                        branch_kind = "entered-new"

                    # Validate
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                        branch_info = core.validate_lakebase_autoscaling(
                            profile, project_name, branch_name
                        )
                    output = buf.getvalue()
                    if output.strip():
                        self._log(output.strip())

                    if branch_info:
                        lakebase_config = {
                            "type": "autoscaling",
                            "project": project_name,
                            "branch": branch_name,
                            "database_id": branch_info.get("database_id", ""),
                            "branch_kind": branch_kind,
                        }
                        s["lakebase_config"] = lakebase_config
                        core.update_env_file("LAKEBASE_AUTOSCALING_PROJECT", project_name)
                        core.update_env_file("LAKEBASE_AUTOSCALING_BRANCH", branch_name)
                        pg_host = branch_info.get("host", "")
                        if pg_host:
                            core.update_env_file("PGHOST", pg_host)
                        core.update_env_file("PGUSER", username)
                        core.update_env_file("PGDATABASE", "databricks_postgres")

                        kind_label = {
                            "personal": t("個人ブランチ（自動生成）", "personal branch (auto-generated)"),
                            "entered-existing": t("既存の共有ブランチ", "existing shared branch"),
                            "entered-new": t("新規作成したブランチ", "newly-created branch"),
                        }.get(branch_kind, "")
                        advance(t(f"Lakebase 設定完了 ({kind_label})",
                                   f"Lakebase configured ({kind_label})"))
                    else:
                        fail("Lakebase", t("検証に失敗", "Validation failed"), fatal=True)
                except _AbortSetup:
                    raise
                except Exception as e:
                    fail("Lakebase", str(e)[:200], fatal=True)
            else:
                step += 1
                self._set_progress(step / total_steps)

            # Step 7: Create MLflow experiments
            self._log(t("MLflow Experiments \u3092\u8a2d\u5b9a\u4e2d...", "Setting up MLflow Experiments..."))
            try:
                if s.get("mlflow_mode") == "new":
                    base = s.get("mlflow_base_name") or f"/Users/{username}/freshmart-agent"
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                        m_name, m_id = core._create_single_experiment(profile, f"{base}-monitoring")
                        e_name, e_id = core._create_single_experiment(profile, f"{base}-evaluation")
                    output = buf.getvalue()
                    if output.strip():
                        self._log(output.strip())
                    s["monitoring_name"] = m_name
                    s["monitoring_id"] = m_id
                    s["eval_name"] = e_name
                    s["eval_id"] = e_id
                    # ロールバック用に記録（新規作成時のみ）
                    s["created_resources"]["monitoring_id"] = m_id
                    s["created_resources"]["eval_id"] = e_id
                # else: IDs already stored from page 8
                advance(t(f"MLflow Experiments: {s['monitoring_id']} / {s['eval_id']}",
                           f"MLflow Experiments: {s['monitoring_id']} / {s['eval_id']}"))
            except Exception as e:
                fail(t("MLflow", "MLflow"), str(e)[:200])

            # Step 8: Run trace setup
            if s.get("trace_dest_mode") == "delta" and s.get("trace_dest_schema"):
                self._log(t("トレーステーブルを作成中...", "Creating trace tables..."))
                try:
                    dest = s["trace_dest_schema"]
                    core.update_env_file("MLFLOW_TRACING_DESTINATION", dest)
                    core.update_env_file("MLFLOW_TRACING_SQL_WAREHOUSE_ID", warehouse_id)
                    core.append_env_to_app_yaml("MLFLOW_TRACING_DESTINATION", dest)
                    core.append_env_to_app_yaml("MLFLOW_TRACING_SQL_WAREHOUSE_ID", warehouse_id)
                    if "." in dest:
                        _cat, _sch = dest.split(".", 1)
                        # Ensure trace schema exists (same as CUI)
                        verify = core.run_sql_statement(
                            f"DESCRIBE SCHEMA `{_cat}`.`{_sch}`", token, host, warehouse_id)
                        if verify.get("status", {}).get("state") not in ("SUCCEEDED", "CLOSED"):
                            self._log(t(f"  スキーマ {dest} を作成中...",
                                         f"  Creating schema {dest}..."))
                            core.run_sql_statement(
                                f"CREATE CATALOG IF NOT EXISTS `{_cat}`", token, host, warehouse_id)
                            core.run_sql_statement(
                                f"CREATE SCHEMA IF NOT EXISTS `{_cat}`.`{_sch}`", token, host, warehouse_id)
                        buf = io.StringIO()
                        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                            ok = core.run_trace_setup_on_databricks(
                                profile_name=profile,
                                username=username,
                                catalog=_cat,
                                schema=_sch,
                                warehouse_id=warehouse_id,
                                experiment_id=s["monitoring_id"],
                            )
                        output = buf.getvalue()
                        if output.strip():
                            self._log(output.strip())
                        if ok:
                            advance(t("\u30c8\u30ec\u30fc\u30b9\u30c6\u30fc\u30d6\u30eb\u4f5c\u6210\u5b8c\u4e86", "Trace tables created"))
                        else:
                            fail(t("\u30c8\u30ec\u30fc\u30b9\u30c6\u30fc\u30d6\u30eb", "Trace tables"), t("\u81ea\u52d5\u4f5c\u6210\u306b\u5931\u6557", "Auto-creation failed"))
                    else:
                        advance(t("\u30c8\u30ec\u30fc\u30b9\u8a2d\u5b9a\u4fdd\u5b58", "Trace config saved"))
                except Exception as e:
                    fail(t("\u30c8\u30ec\u30fc\u30b9", "Trace"), str(e)[:200])
            else:
                # Delta Table を使わない選択 → 前回のランで残った設定を削除
                core.update_env_file("MLFLOW_TRACING_DESTINATION", "")
                core.remove_env_from_app_yaml("MLFLOW_TRACING_DESTINATION")
                core.remove_env_from_app_yaml("MLFLOW_TRACING_SQL_WAREHOUSE_ID")
                step += 1
                self._set_progress(step / total_steps)

            # Step 9: Update config files
            self._log(t("\u8a2d\u5b9a\u30d5\u30a1\u30a4\u30eb\u3092\u66f4\u65b0\u4e2d...", "Updating config files..."))
            try:
                monitoring_id = s.get("monitoring_id", "")
                eval_id = s.get("eval_id", "")
                genie_space_id = s.get("genie_space_id", "")
                vs_index_val = s.get("vs_index", "")

                core.update_env_file("MLFLOW_EXPERIMENT_ID", monitoring_id)
                core.update_env_file("MLFLOW_EVAL_EXPERIMENT_ID", eval_id)
                core.update_env_file("GENIE_SPACE_ID", genie_space_id)
                core.update_env_file("VECTOR_SEARCH_INDEX", vs_index_val)
                # Persist LLM endpoint selection
                llm_endpoint = s.get("llm_endpoint", "") or core.DEFAULT_LLM_ENDPOINT
                core.update_env_file("LLM_ENDPOINT_NAME", llm_endpoint)
                core.append_env_to_app_yaml("LLM_ENDPOINT_NAME", llm_endpoint)
                # Persist Databricks App name
                app_name = s.get("app_name", "") or core.compute_default_app_name(
                    s.get("username", "user")
                )
                core.update_env_file("DATABRICKS_APP_NAME", app_name)

                buf = io.StringIO()
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    core.update_databricks_yml_experiment(monitoring_id)
                    core.update_databricks_yml_resources(genie_space_id, vs_index_val)
                    core.update_databricks_yml_app_name(app_name)
                    if lakebase_config:
                        core.update_databricks_yml_lakebase(lakebase_config)
                        core.update_app_yaml_lakebase(lakebase_config)

                # Update workshop_setup.py if it exists
                setup_notebook = Path("workshop_setup.py")
                if setup_notebook.exists():
                    content = setup_notebook.read_text()
                    replacements = {
                        '"<CATALOG>"': f'"{catalog}"',
                        '"<SCHEMA>"': f'"{schema}"',
                        '"<WAREHOUSE-ID>"': f'"{warehouse_id}"',
                        '"<MONITORING-EXPERIMENT-ID>"': f'"{monitoring_id}"',
                        '"<EVAL-EXPERIMENT-ID>"': f'"{eval_id}"',
                        '"<GENIE-SPACE-ID>"': f'"{genie_space_id}"',
                        '"<LAKEBASE-PROJECT>"': (
                            f'"{lakebase_config["project"]}"' if lakebase_config
                            else '"<LAKEBASE-PROJECT>"'
                        ),
                        '"<LAKEBASE-BRANCH>"': (
                            f'"{lakebase_config["branch"]}"' if lakebase_config
                            else '"<LAKEBASE-BRANCH>"'
                        ),
                    }
                    for old, new in replacements.items():
                        content = content.replace(old, new)
                    setup_notebook.write_text(content)

                output = buf.getvalue()
                if output.strip():
                    self._log(output.strip())
                advance(t("\u8a2d\u5b9a\u30d5\u30a1\u30a4\u30eb\u66f4\u65b0\u5b8c\u4e86", "Config files updated"))
            except Exception as e:
                fail(t("\u8a2d\u5b9a\u30d5\u30a1\u30a4\u30eb", "Config files"), str(e)[:200])

            # Step 10: Prompt Registry (optional)
            if self.data.get("use_prompt_registry") == "yes":
                self._log(t("Prompt Registry に登録中...", "Registering to Prompt Registry..."))
                try:
                    prompt_name = f"{self.data['catalog']}.{self.data['schema']}.freshmart_system_prompt"
                    result = subprocess.run(
                        ["uv", "run", "register-prompt", "--name", prompt_name],
                        capture_output=True, text=True,
                    )
                    if result.returncode == 0:
                        core.update_env_file("PROMPT_REGISTRY_NAME", prompt_name)
                        core.append_env_to_app_yaml("PROMPT_REGISTRY_NAME", prompt_name)
                        advance(f"Prompt Registry: {prompt_name}")
                    else:
                        fail("Prompt Registry", result.stderr[-200:] if result.stderr else "Unknown error")
                except Exception as e:
                    fail("Prompt Registry", str(e)[:200])
            else:
                # 前回のランで設定された PROMPT_REGISTRY_NAME を削除
                core.update_env_file("PROMPT_REGISTRY_NAME", "")
                core.remove_env_from_app_yaml("PROMPT_REGISTRY_NAME")
                advance(t("Prompt Registry: スキップ", "Prompt Registry: Skipped"))

            # Step 11: Install dependencies
            self._log(t("\u4f9d\u5b58\u95a2\u4fc2\u3092\u30a4\u30f3\u30b9\u30c8\u30fc\u30eb\u4e2d...", "Installing dependencies..."))
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    core.install_dependencies()
                output = buf.getvalue()
                if output.strip():
                    self._log(output.strip())
                advance(t("\u4f9d\u5b58\u95a2\u4fc2\u30a4\u30f3\u30b9\u30c8\u30fc\u30eb\u5b8c\u4e86", "Dependencies installed"))
            except Exception as e:
                fail(t("\u4f9d\u5b58\u95a2\u4fc2", "Dependencies"), str(e)[:200])

        except _AbortSetup as ae:
            s["aborted_at"] = str(ae)
            # 自動ロールバックは行わない。完了ページで「ロールバック」ボタンを
            # ユーザーが押したタイミングで実行する。
        except Exception as e:
            import traceback
            self._log(f"\n✗ Fatal error: {e}")
            self._log(traceback.format_exc())
        finally:
            if s.get("aborted_at"):
                self._log(t(
                    f"\n⛔ セットアップは「{s['aborted_at']}」で中断されました。",
                    f"\n⛔ Setup aborted at step: {s['aborted_at']}",
                ))
            else:
                self._log(t("\nセットアップ完了！", "\nSetup complete!"))
            self._signal_done()

    def _rollback(self, created: dict) -> None:
        """ユーザーが「新規作成」を選択したリソースを削除する。

        ルール: ユーザーが「既存」を選択して使ったリソースは削除しない。
                ユーザーが「新規作成」した、もしくは本セットアップで生成された
                ものだけを削除対象とする。
        """
        self._log(t("\n🔄 ロールバック開始...", "\n🔄 Rollback starting..."))
        profile = self.data.get("profile_name", "")
        token = self.data.get("token", "")
        host = self.data.get("host", "")
        warehouse_id = self.data.get("warehouse_id", "")

        # 1. Genie Space
        gs = created.get("genie_space_id")
        if gs:
            try:
                core.api_post(f"/api/2.0/genie/spaces/{gs}/delete", token, host, {}) \
                    if hasattr(core, "api_delete") is False else None
                # Try DELETE method via api_get fallback
                result = subprocess.run(
                    ["databricks", "api", "delete", f"/api/2.0/genie/spaces/{gs}",
                     "-p", profile],
                    capture_output=True, text=True,
                )
                if result.returncode == 0:
                    self._log(t(f"  ✓ Genie Space 削除: {gs}",
                                 f"  ✓ Genie Space deleted: {gs}"))
                else:
                    self._log(t(f"  ⚠ Genie Space 削除失敗: {result.stderr[:100]}",
                                 f"  ⚠ Genie Space delete failed: {result.stderr[:100]}"))
            except Exception as e:
                self._log(f"  ⚠ Genie Space delete error: {str(e)[:100]}")

        # 2. VS Index
        vs = created.get("vs_index")
        if vs:
            try:
                result = subprocess.run(
                    ["databricks", "api", "delete",
                     f"/api/2.0/vector-search/indexes/{vs}", "-p", profile],
                    capture_output=True, text=True,
                )
                if result.returncode == 0:
                    self._log(t(f"  ✓ VS インデックス削除: {vs}",
                                 f"  ✓ VS index deleted: {vs}"))
                else:
                    self._log(t(f"  ⚠ VS インデックス削除失敗: {result.stderr[:100]}",
                                 f"  ⚠ VS index delete failed: {result.stderr[:100]}"))
            except Exception as e:
                self._log(f"  ⚠ VS index delete error: {str(e)[:100]}")

        # 3a. Lakebase branch (only if newly created in this run)
        lb_project = created.get("lakebase_project")
        lb_branch = created.get("lakebase_branch")
        if lb_project and lb_branch:
            try:
                result = subprocess.run(
                    ["databricks", "api", "delete",
                     f"/api/2.0/postgres/projects/{lb_project}/branches/{lb_branch}",
                     "-p", profile],
                    capture_output=True, text=True,
                )
                if result.returncode == 0:
                    self._log(t(f"  ✓ Lakebase ブランチ削除: {lb_branch}",
                                 f"  ✓ Lakebase branch deleted: {lb_branch}"))
                else:
                    self._log(t(f"  ⚠ Lakebase ブランチ削除失敗: {result.stderr[:100]}",
                                 f"  ⚠ Lakebase branch delete failed: {result.stderr[:100]}"))
            except Exception as e:
                self._log(f"  ⚠ Lakebase branch delete error: {str(e)[:100]}")

        # 3b. Lakebase project (only if newly created in this run)
        if lb_project:
            try:
                result = subprocess.run(
                    ["databricks", "api", "delete",
                     f"/api/2.0/postgres/projects/{lb_project}",
                     "-p", profile],
                    capture_output=True, text=True,
                )
                if result.returncode == 0:
                    self._log(t(f"  ✓ Lakebase プロジェクト削除: {lb_project}",
                                 f"  ✓ Lakebase project deleted: {lb_project}"))
                else:
                    self._log(t(f"  ⚠ Lakebase プロジェクト削除失敗: {result.stderr[:100]}",
                                 f"  ⚠ Lakebase project delete failed: {result.stderr[:100]}"))
            except Exception as e:
                self._log(f"  ⚠ Lakebase project delete error: {str(e)[:100]}")

        # 4. MLflow Experiments
        for key in ("monitoring_id", "eval_id"):
            exp_id = created.get(key)
            if exp_id:
                try:
                    result = subprocess.run(
                        ["databricks", "experiments", "delete-experiment", exp_id,
                         "-p", profile],
                        capture_output=True, text=True,
                    )
                    if result.returncode == 0:
                        self._log(t(f"  ✓ MLflow Experiment 削除: {exp_id}",
                                     f"  ✓ MLflow Experiment deleted: {exp_id}"))
                    else:
                        self._log(t(f"  ⚠ MLflow Experiment 削除失敗: {exp_id}",
                                     f"  ⚠ MLflow Experiment delete failed: {exp_id}"))
                except Exception as e:
                    self._log(f"  ⚠ MLflow delete error: {str(e)[:100]}")

        # 5. Schema (always tracked when set; uses CASCADE to drop tables/indexes)
        new_schema = created.get("schema")
        new_catalog = created.get("catalog")
        if new_schema and warehouse_id and token and host:
            # Skip schema drop if catalog is also being dropped (CASCADE handles it)
            if not new_catalog:
                try:
                    core.run_sql_statement(
                        f"DROP SCHEMA IF EXISTS {new_schema} CASCADE",
                        token, host, warehouse_id,
                    )
                    self._log(t(f"  ✓ スキーマ削除: {new_schema}",
                                 f"  ✓ Schema dropped: {new_schema}"))
                except Exception as e:
                    self._log(f"  ⚠ Schema drop error: {str(e)[:100]}")

        # 6. Catalog (only if user chose "new" mode)
        if new_catalog and warehouse_id and token and host:
            try:
                core.run_sql_statement(
                    f"DROP CATALOG IF EXISTS `{new_catalog}` CASCADE",
                    token, host, warehouse_id,
                )
                self._log(t(f"  ✓ カタログ削除: {new_catalog}",
                             f"  ✓ Catalog dropped: {new_catalog}"))
            except Exception as e:
                self._log(f"  ⚠ Catalog drop error: {str(e)[:100]}")

        # 7. SQL Warehouse (only if user chose "new" mode)
        new_wh = created.get("warehouse_id")
        if new_wh:
            try:
                result = subprocess.run(
                    ["databricks", "warehouses", "delete", new_wh, "-p", profile],
                    capture_output=True, text=True,
                )
                if result.returncode == 0:
                    self._log(t(f"  ✓ SQL ウェアハウス削除: {new_wh}",
                                 f"  ✓ SQL warehouse deleted: {new_wh}"))
                else:
                    self._log(t(f"  ⚠ SQL ウェアハウス削除失敗: {result.stderr[:100]}",
                                 f"  ⚠ SQL warehouse delete failed: {result.stderr[:100]}"))
            except Exception as e:
                self._log(f"  ⚠ Warehouse delete error: {str(e)[:100]}")

        # 8. VS Endpoint (only if user chose "new" mode)
        new_ep = created.get("vs_endpoint")
        if new_ep:
            try:
                result = subprocess.run(
                    ["databricks", "api", "delete",
                     f"/api/2.0/vector-search/endpoints/{new_ep}", "-p", profile],
                    capture_output=True, text=True,
                )
                if result.returncode == 0:
                    self._log(t(f"  ✓ VS エンドポイント削除: {new_ep}",
                                 f"  ✓ VS endpoint deleted: {new_ep}"))
                else:
                    self._log(t(f"  ⚠ VS エンドポイント削除失敗: {result.stderr[:100]}",
                                 f"  ⚠ VS endpoint delete failed: {result.stderr[:100]}"))
            except Exception as e:
                self._log(f"  ⚠ VS endpoint delete error: {str(e)[:100]}")

        self._log(t(
            "\n✓ ロールバック完了。",
            "\n✓ Rollback complete.",
        ))

    # ── Page 13: Complete (state-machine: success / errors / rolling-back / rolled-back) ──
    def _page_complete(self, frame: customtkinter.CTkFrame):
        s = self.data
        state = s.get("complete_state")
        if state is None:
            failed = s.get("setup_failed_steps", [])
            aborted = bool(s.get("aborted_at"))
            state = "errors" if (failed or aborted) else "success"
            s["complete_state"] = state

        if state == "rolling_back":
            self._render_complete_rolling_back(frame)
        elif state == "rolled_back":
            self._render_complete_rolled_back(frame)
        elif state == "errors":
            self._render_complete_with_errors(frame)
        else:
            self._render_complete_success(frame)

    # ── Sub-renderers for the complete page states ───────────────────────

    def _render_complete_success(self, frame):
        s = self.data
        customtkinter.CTkLabel(
            frame,
            text=t("✓ セットアップ完了！", "✓ Setup Complete!"),
            font=customtkinter.CTkFont(size=24, weight="bold"),
            text_color="#2ECC71",
        ).pack(pady=(15, 5))

        self._render_resource_summary(frame)
        self._render_team_sharing_info(frame)

        # Big centered Complete button
        btn_frame = customtkinter.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(pady=(15, 10))

        customtkinter.CTkButton(
            btn_frame,
            text=t("クリップボードにコピー", "Copy to Clipboard"),
            width=200,
            command=self._copy_share_text,
        ).pack(side="left", padx=10)

        customtkinter.CTkButton(
            btn_frame,
            text=t("完了", "Complete"),
            width=200,
            height=40,
            font=customtkinter.CTkFont(size=15, weight="bold"),
            command=self.destroy,
        ).pack(side="left", padx=10)

        # 次のステップ: コピー可能なコマンドエントリで表示
        next_label = customtkinter.CTkLabel(
            frame,
            text=t("次のステップ — このコマンドをターミナルで実行:",
                   "Next step — run this in your terminal:"),
            font=customtkinter.CTkFont(size=13),
            text_color="#3B8ED0",
        )
        next_label.pack(pady=(10, 2))

        next_cmd_frame = customtkinter.CTkFrame(frame, fg_color="transparent")
        next_cmd_frame.pack(pady=(0, 10))

        next_cmd_entry = customtkinter.CTkEntry(
            next_cmd_frame,
            width=300,
            font=customtkinter.CTkFont(family="Menlo", size=14, weight="bold"),
        )
        next_cmd_entry.insert(0, "uv run start-app")
        next_cmd_entry.configure(state="readonly")
        next_cmd_entry.pack(side="left", padx=(0, 5))

        def _copy_next_cmd():
            self.clipboard_clear()
            self.clipboard_append("uv run start-app")
            copy_btn.configure(text=t("✓ コピー済み", "✓ Copied"))
            self.after(1500, lambda: copy_btn.configure(
                text=t("コピー", "Copy")
            ))

        copy_btn = customtkinter.CTkButton(
            next_cmd_frame,
            text=t("コピー", "Copy"),
            width=80,
            command=_copy_next_cmd,
        )
        copy_btn.pack(side="left")

    def _render_complete_with_errors(self, frame):
        s = self.data
        failed = s.get("setup_failed_steps", [])
        aborted = bool(s.get("aborted_at"))

        title = (t("⚠ セットアップが中断されました", "⚠ Setup was aborted")
                 if aborted else
                 t("⚠ セットアップ完了（一部失敗あり）",
                   "⚠ Setup Complete (with errors)"))
        customtkinter.CTkLabel(
            frame,
            text=title,
            font=customtkinter.CTkFont(size=22, weight="bold"),
            text_color="orange",
        ).pack(pady=(15, 5))

        # Failed-steps box
        if failed:
            customtkinter.CTkLabel(
                frame,
                text=t(f"失敗したステップ: {len(failed)} 個",
                       f"Failed steps: {len(failed)}"),
                text_color="orange",
            ).pack(pady=(0, 2))
            fail_box = customtkinter.CTkTextbox(frame, width=620, height=100, text_color="orange")
            fail_box.pack(padx=20, pady=(0, 5))
            for f in failed:
                if isinstance(f, dict):
                    fail_box.insert("end", f"✗ {f.get('name', '?')}: {f.get('error', '')}\n")
                else:
                    fail_box.insert("end", f"✗ {f}\n")
            fail_box.configure(state="disabled")

        if aborted:
            customtkinter.CTkLabel(
                frame,
                text=t(f"中断ポイント: {s.get('aborted_at', '')}",
                       f"Aborted at: {s.get('aborted_at', '')}"),
                text_color="orange",
            ).pack(pady=(0, 5))

        self._render_resource_summary(frame, compact=True)

        # Action buttons: Complete (accept partial) + Rollback
        btn_frame = customtkinter.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(pady=(15, 10))

        customtkinter.CTkButton(
            btn_frame,
            text=t("ロールバック\n(新規作成リソースを削除)",
                   "Rollback\n(delete newly created resources)"),
            width=240,
            height=50,
            fg_color="#E74C3C",
            hover_color="#C0392B",
            font=customtkinter.CTkFont(size=13, weight="bold"),
            command=self._on_rollback_click,
        ).pack(side="left", padx=10)

        customtkinter.CTkButton(
            btn_frame,
            text=t("完了\n(現状のままアプリを閉じる)",
                   "Complete\n(keep as-is and close)"),
            width=240,
            height=50,
            font=customtkinter.CTkFont(size=13),
            command=self.destroy,
        ).pack(side="left", padx=10)

    def _render_complete_rolling_back(self, frame):
        customtkinter.CTkLabel(
            frame,
            text=t("🔄 ロールバック実行中...",
                   "🔄 Rollback in progress..."),
            font=customtkinter.CTkFont(size=22, weight="bold"),
        ).pack(pady=(15, 10))

        self._rollback_textbox = customtkinter.CTkTextbox(frame, width=620, height=380)
        self._rollback_textbox.pack(padx=20, pady=5)
        self._rollback_textbox.configure(state="disabled")

        # Replay any rollback log lines collected so far
        for line in self.data.get("rollback_log", []):
            self._rollback_textbox.configure(state="normal")
            self._rollback_textbox.insert("end", line + "\n")
            self._rollback_textbox.configure(state="disabled")

        # Start the rollback in a thread if not already started
        if not self.data.get("_rollback_running"):
            self.data["_rollback_running"] = True
            self.data["rollback_log"] = []
            thread = threading.Thread(target=self._run_rollback_async, daemon=True)
            thread.start()
            self.after(100, self._check_rollback_progress)

    def _render_complete_rolled_back(self, frame):
        customtkinter.CTkLabel(
            frame,
            text=t("✓ ロールバック完了", "✓ Rollback Complete"),
            font=customtkinter.CTkFont(size=24, weight="bold"),
            text_color="#2ECC71",
        ).pack(pady=(15, 10))

        customtkinter.CTkLabel(
            frame,
            text=t(
                "本セットアップで新規作成されたリソースを削除しました。\nアプリを閉じて、最初からやり直せます。",
                "Newly created resources from this setup have been deleted.\nClose the app and start over.",
            ),
            wraplength=600,
            justify="left",
        ).pack(pady=(0, 10))

        log_box = customtkinter.CTkTextbox(frame, width=620, height=300)
        log_box.pack(padx=20, pady=5)
        for line in self.data.get("rollback_log", []):
            log_box.insert("end", line + "\n")
        log_box.configure(state="disabled")

        customtkinter.CTkButton(
            frame,
            text=t("閉じる", "Close"),
            width=200,
            height=40,
            font=customtkinter.CTkFont(size=15, weight="bold"),
            command=self.destroy,
        ).pack(pady=(15, 10))

    def _render_resource_summary(self, frame, compact: bool = False):
        s = self.data
        summary_lines = [
            f"{t('カタログ', 'Catalog')}: {s.get('catalog', '')}",
            f"{t('スキーマ', 'Schema')}: {s.get('catalog', '')}.{s.get('schema', '')}",
            f"Vector Search: {s.get('vs_index', '')}",
            f"Genie Space ID: {s.get('genie_space_id', '')}",
            f"{t('モニタリング Exp', 'Monitoring Exp')}: {s.get('monitoring_id', '')}",
            f"{t('評価 Exp', 'Evaluation Exp')}: {s.get('eval_id', '')}",
        ]
        lakebase_config = s.get("lakebase_config")
        if lakebase_config:
            bk = lakebase_config.get("branch_kind", "")
            bk_label = {
                "personal": t(" (個人ブランチ)", " (personal)"),
                "entered-existing": t(" (既存共有ブランチ)", " (existing shared)"),
                "entered-new": t(" (新規作成)", " (newly created)"),
            }.get(bk, "")
            summary_lines.append(
                f"Lakebase: {lakebase_config.get('project', '')} / {lakebase_config.get('branch', '')}{bk_label}"
            )
        if s.get("trace_dest_mode") == "delta" and s.get("trace_dest_schema"):
            summary_lines.append(
                f"{t('トレース送信先', 'Trace Dest')}: {s['trace_dest_schema']}"
            )

        height = 100 if compact else 130
        customtkinter.CTkLabel(
            frame,
            text=t("作成されたリソース", "Created Resources"),
            font=customtkinter.CTkFont(size=16, weight="bold"),
        ).pack(pady=(5, 2), anchor="w", padx=30)
        res_box = customtkinter.CTkTextbox(frame, width=600, height=height)
        res_box.pack(padx=30, pady=(0, 5))
        res_box.insert("0.0", "\n".join(summary_lines))
        res_box.configure(state="disabled")

        # 共有ブランチ警告
        if lakebase_config and lakebase_config.get("branch_kind") == "entered-existing":
            warn_text = t(
                "⚠ 既存の共有 Lakebase ブランチを使用中です。アクセスには代表者による grant-team-access が必要です。",
                "⚠ Using an existing shared Lakebase branch. Access requires grant-team-access from the team rep.",
            )
            customtkinter.CTkLabel(
                frame, text=warn_text, text_color="orange", wraplength=600, justify="left",
            ).pack(padx=30, pady=(0, 5), anchor="w")

    def _render_team_sharing_info(self, frame):
        s = self.data
        lakebase_config = s.get("lakebase_config")
        share_lines = [
            f"{t('カタログ名', 'Catalog')}: {s.get('catalog', '')}",
            f"{t('スキーマ名', 'Schema')}: {s.get('schema', '')}",
            f"{t('VS エンドポイント', 'VS Endpoint')}: {s.get('vs_endpoint', '')}",
            f"Genie Space ID: {s.get('genie_space_id', '')}",
        ]
        if lakebase_config:
            share_lines.append(f"{t('Lakebase プロジェクト', 'Lakebase project')}: {lakebase_config.get('project', '')}")
            share_lines.append(f"{t('Lakebase ブランチ', 'Lakebase branch')}: {lakebase_config.get('branch', '')}")
        share_lines.append(f"{t('モニタリング Exp ID', 'Monitoring Exp ID')}: {s.get('monitoring_id', '')}")
        share_lines.append(f"{t('評価 Exp ID', 'Evaluation Exp ID')}: {s.get('eval_id', '')}")

        self._share_text = "\n".join(share_lines)

        customtkinter.CTkLabel(
            frame,
            text=t("チーム共有情報", "Team Sharing Info"),
            font=customtkinter.CTkFont(size=16, weight="bold"),
        ).pack(pady=(5, 2), anchor="w", padx=30)
        share_box = customtkinter.CTkTextbox(frame, width=600, height=100)
        share_box.pack(padx=30, pady=(0, 5))
        share_box.insert("0.0", self._share_text)
        share_box.configure(state="disabled")

    # ── Rollback action handlers ────────────────────────────────────────

    def _on_rollback_click(self):
        # Switch to rolling-back state and re-render the page
        self.data["complete_state"] = "rolling_back"
        self.show_page(self.current_page)

    def _run_rollback_async(self):
        """Background thread: run rollback and post log lines via the queue."""
        try:
            self._rollback(self.data.get("created_resources", {}))
        except Exception as e:
            self._log(f"⚠ Rollback exception: {str(e)[:200]}")
        finally:
            self._exec_queue.put(("rollback_done", None))

    def _check_rollback_progress(self):
        """Drain the queue to update the rollback textbox; transition when done."""
        try:
            while True:
                kind, data = self._exec_queue.get_nowait()
                if kind == "log":
                    self.data.setdefault("rollback_log", []).append(data)
                    if hasattr(self, "_rollback_textbox"):
                        self._rollback_textbox.configure(state="normal")
                        self._rollback_textbox.insert("end", data + "\n")
                        self._rollback_textbox.see("end")
                        self._rollback_textbox.configure(state="disabled")
                elif kind == "rollback_done":
                    self.data["_rollback_running"] = False
                    self.data["complete_state"] = "rolled_back"
                    self.after(500, lambda: self.show_page(self.current_page))
                    return
        except queue.Empty:
            pass

        if self.data.get("_rollback_running"):
            self.after(100, self._check_rollback_progress)

    def _copy_share_text(self):
        self.clipboard_clear()
        self.clipboard_append(self._share_text)


# ════════════════════════════════════════════════════════════════════════
#  Entry point
# ════════════════════════════════════════════════════════════════════════
def main():
    app = QuickstartWizard()
    app.mainloop()


if __name__ == "__main__":
    main()
