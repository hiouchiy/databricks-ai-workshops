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

TOTAL_PAGES = 13


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
            # Prerequisites
            "prereqs_ok": False,
            # Execution
            "setup_log": [],
            "setup_failed_steps": [],
            "setup_complete": False,
            # Genie
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
            self._page_lakebase,        # 6 -> Step 7
            self._page_mlflow,          # 7 -> Step 8
            self._page_trace,           # 8 -> Step 9
            self._page_prompt_registry, # 9 -> Step 10
            self._page_summary,         # 10 -> Step 11
            self._page_execute,         # 11 -> Step 12
            self._page_complete,        # 12 -> Step 13
        ]

    def _update_nav(self):
        pg = self.current_page
        self._back_btn.configure(text=t("\u2190 \u623b\u308b", "\u2190 Back"))
        self._next_btn.configure(text=t("\u6b21\u3078 \u2192", "Next \u2192"))
        self._page_label.configure(
            text=f"Step {pg + 1} of {TOTAL_PAGES}"
        )

        # Back disabled on page 1, and on execute/complete pages
        if pg == 0 or pg >= 11:
            self._back_btn.configure(state="disabled")
        else:
            self._back_btn.configure(state="normal")

        # Next disabled on execute/complete pages
        if pg >= 11:
            self._next_btn.configure(state="disabled")
        else:
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
        elif pg == 4:
            if not self.data.get("warehouse_id", "").strip():
                self._show_error(t(
                    "\u30a6\u30a7\u30a2\u30cf\u30a6\u30b9\u3092\u9078\u629e\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
                    "Please select a warehouse."
                ))
                return False
        elif pg == 5:
            if not self.data.get("vs_endpoint", "").strip():
                # Allow empty with warning
                pass
        elif pg == 6:
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
        elif pg == 7:
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
        """Validate a Unity Catalog identifier (catalog/schema name).

        Rules:
        - Must not be empty
        - Max 255 characters
        - Can contain letters (including Unicode/Japanese), digits, underscores
        - Must start with a letter or underscore
        - No spaces, hyphens, dots, or special characters
        """
        import re
        if not name:
            return False, t("名前を入力してください", "Name is required")
        if len(name) > 255:
            return False, t("255文字以内で入力してください", "Must be 255 characters or fewer")
        if not re.match(r'^[a-zA-Z_\u3000-\u9fff\uf900-\ufaff]', name):
            return False, t("先頭は英字またはアンダースコアで始めてください", "Must start with a letter or underscore")
        if not re.match(r'^[a-zA-Z0-9_\u3000-\u9fff\uf900-\ufaff]+$', name):
            return False, t(
                "使用できない文字が含まれています（英数字・アンダースコアのみ）",
                "Contains invalid characters (only letters, digits, underscores allowed)"
            )
        return True, ""

    def _validate_lakebase_name(self, name: str) -> tuple[bool, str]:
        """Validate a Lakebase project/branch name.

        Rules:
        - Must not be empty
        - Can contain lowercase letters, digits, hyphens
        - Must start with a letter
        - No underscores, uppercase, spaces, or special characters
        """
        import re
        if not name:
            return False, t("名前を入力してください", "Name is required")
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

        if not profile_names:
            customtkinter.CTkLabel(
                frame,
                text=t(
                    "Databricks \u30d7\u30ed\u30d5\u30a1\u30a4\u30eb\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093\u3002\n\u5148\u306b `databricks auth login` \u3092\u5b9f\u884c\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
                    "No Databricks profiles found.\nPlease run `databricks auth login` first.",
                ),
                text_color="orange",
                wraplength=500,
            ).pack(pady=20)
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

    def _on_connect(self):
        profile = self._profile_var.get()
        self._auth_status.configure(
            text=t("\u691c\u8a3c\u4e2d...", "Validating..."), text_color="white"
        )
        self.update_idletasks()

        if not core.validate_profile(profile):
            self.data["auth_ok"] = False
            self._auth_status.configure(
                text=t(
                    f"\u2717 \u30d7\u30ed\u30d5\u30a1\u30a4\u30eb '{profile}' \u306e\u8a8d\u8a3c\u306b\u5931\u6557\u3002\n`databricks auth login --profile {profile}` \u3092\u5b9f\u884c\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
                    f"\u2717 Profile '{profile}' is not authenticated.\nRun `databricks auth login --profile {profile}`.",
                ),
                text_color="red",
            )
            return

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

        # Pre-fill defaults
        if not self.data["catalog"]:
            self.data["catalog"] = self.data["username"].split("@")[0].replace(".", "_")
        if not self.data["schema"]:
            self.data["schema"] = "retail_agent"
        if not self.data["mlflow_base_name"]:
            self.data["mlflow_base_name"] = f"/Users/{self.data['username']}/freshmart-agent"

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
            # Fetch catalogs via Unity Catalog REST API (no warehouse needed)
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

            env_val = core.get_env_value("CATALOG") or self.data.get("catalog", "")

            self._catalog_entry = customtkinter.CTkEntry(
                self._catalog_fields_frame, width=400,
                placeholder_text="e.g. my_catalog",
            )
            self._catalog_entry.pack(pady=(0, 5))
            if env_val:
                self._catalog_entry.insert(0, env_val)

            self._catalog_validation_label = customtkinter.CTkLabel(
                self._catalog_fields_frame, text="", wraplength=400,
            )
            self._catalog_validation_label.pack(anchor="w")

            self._catalog_entry.bind("<KeyRelease>", lambda _: self._on_catalog_entry_change())

            # Run initial validation if there's a pre-filled value
            if env_val:
                self._on_catalog_entry_change()

    def _on_catalog_dropdown_change(self, selection: str):
        self.data["catalog"] = selection

    def _on_catalog_entry_change(self):
        name = self._catalog_entry.get().strip()
        self.data["catalog"] = name
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

        env_val = core.get_env_value("SCHEMA") or self.data.get("schema", "")

        self._schema_entry = customtkinter.CTkEntry(
            frame, width=400, placeholder_text="e.g. retail_agent"
        )
        self._schema_entry.pack(pady=10, padx=40)
        if env_val:
            self._schema_entry.insert(0, env_val)

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
            text=t("SQL Warehouse \u306e\u9078\u629e", "Select SQL Warehouse"),
            font=customtkinter.CTkFont(size=22, weight="bold"),
        ).pack(pady=(20, 10))

        # Fetch warehouses
        try:
            result = core.run_command(
                ["databricks", "warehouses", "list", "-p", self.data["profile_name"], "-o", "json"],
                check=True,
            )
            self._warehouses = json.loads(result.stdout)
            self._warehouses.sort(
                key=lambda w: (0 if w.get("state") == "RUNNING" else 1, w.get("name", ""))
            )
        except Exception:
            self._warehouses = []

        if not self._warehouses:
            customtkinter.CTkLabel(
                frame,
                text=t(
                    "\u30a6\u30a7\u30a2\u30cf\u30a6\u30b9\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093\u3002",
                    "No SQL warehouses found.",
                ),
                text_color="orange",
            ).pack(pady=20)
            return

        labels = [
            f"{w.get('name', '?')} ({w.get('id', '?')}) [{w.get('state', '?')}]"
            for w in self._warehouses
        ]

        # Auto-select first RUNNING
        default_label = labels[0]
        for i, w in enumerate(self._warehouses):
            if w.get("state") == "RUNNING":
                default_label = labels[i]
                break

        self._wh_var = customtkinter.StringVar(value=default_label)
        customtkinter.CTkOptionMenu(
            frame, variable=self._wh_var, values=labels, width=500,
            command=self._on_wh_change,
        ).pack(pady=10, padx=40)

        # Set initial state
        self._on_wh_change(default_label)

    def _on_wh_change(self, selection: str):
        for w in self._warehouses:
            label = f"{w.get('name', '?')} ({w.get('id', '?')}) [{w.get('state', '?')}]"
            if label == selection:
                self.data["warehouse_id"] = w["id"]
                self.data["warehouse_name"] = w.get("name", "")
                break

    # ── Page 6: Vector Search Endpoint ──────────────────────────────────
    def _page_vs_endpoint(self, frame: customtkinter.CTkFrame):
        customtkinter.CTkLabel(
            frame,
            text=t("Vector Search \u30a8\u30f3\u30c9\u30dd\u30a4\u30f3\u30c8\u306e\u9078\u629e", "Select Vector Search Endpoint"),
            font=customtkinter.CTkFont(size=22, weight="bold"),
        ).pack(pady=(20, 10))

        # Fetch endpoints
        token = self.data.get("token", "")
        host = self.data.get("host", "")
        if token and host:
            data = core.api_get("/api/2.0/vector-search/endpoints", token, host)
            self._vs_endpoints = data.get("endpoints", [])
            state_order = {"ONLINE": 0, "PROVISIONING": 1}
            self._vs_endpoints.sort(
                key=lambda e: (
                    state_order.get(e.get("endpoint_status", {}).get("state", ""), 9),
                    e.get("name", ""),
                )
            )
        else:
            self._vs_endpoints = []

        if not self._vs_endpoints:
            customtkinter.CTkLabel(
                frame,
                text=t(
                    "Vector Search \u30a8\u30f3\u30c9\u30dd\u30a4\u30f3\u30c8\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093\u3002\n\u7a7a\u306e\u307e\u307e\u6b21\u3078\u9032\u3080\u3053\u3068\u3082\u3067\u304d\u307e\u3059\u3002",
                    "No Vector Search endpoints found.\nYou may proceed without one.",
                ),
                text_color="orange",
                wraplength=500,
            ).pack(pady=20)
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
            frame, variable=self._ep_var, values=labels, width=500,
            command=self._on_ep_change,
        ).pack(pady=10, padx=40)

        self._on_ep_change(default_label)

    def _on_ep_change(self, selection: str):
        for e in self._vs_endpoints:
            label = f"{e.get('name', '?')} [{e.get('endpoint_status', {}).get('state', '?')}]"
            if label == selection:
                self.data["vs_endpoint"] = e["name"]
                break

    # ── Page 7: Lakebase Setup ──────────────────────────────────────────
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
            self._lb_proj_entry = customtkinter.CTkEntry(
                self._lb_fields_frame, width=400,
                placeholder_text="e.g. freshmart-lakebase",
            )
            self._lb_proj_entry.pack(pady=(0, 5))
            if self.data.get("lakebase_project"):
                self._lb_proj_entry.insert(0, self.data["lakebase_project"])

            self._lb_proj_validation_label = customtkinter.CTkLabel(
                self._lb_fields_frame, text="", wraplength=400,
            )
            self._lb_proj_validation_label.pack(anchor="w")

            self._lb_proj_entry.bind("<KeyRelease>", lambda _: self._on_lb_proj_change())

            # Run initial validation if there's a pre-filled value
            if self.data.get("lakebase_project"):
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
            )
            self._lb_proj_entry.pack(pady=(0, 5))
            if self.data.get("lakebase_project"):
                self._lb_proj_entry.insert(0, self.data["lakebase_project"])

            self._lb_proj_validation_label = customtkinter.CTkLabel(
                self._lb_fields_frame, text="", wraplength=400,
            )
            self._lb_proj_validation_label.pack(anchor="w")

            self._lb_proj_entry.bind("<KeyRelease>", lambda _: self._on_lb_proj_change())

            # Run initial validation if there's a pre-filled value
            if self.data.get("lakebase_project"):
                self._on_lb_proj_change()

            customtkinter.CTkLabel(
                self._lb_fields_frame,
                text=t("ブランチ名:", "Branch name:"),
            ).pack(anchor="w", pady=(5, 2))
            self._lb_branch_entry = customtkinter.CTkEntry(
                self._lb_fields_frame, width=400,
            )
            self._lb_branch_entry.pack(pady=(0, 5))
            if self.data.get("lakebase_branch"):
                self._lb_branch_entry.insert(0, self.data["lakebase_branch"])
            self._lb_branch_entry.bind("<KeyRelease>", lambda _: self._sync_lb_branch())

    def _on_lb_proj_change(self):
        name = self._lb_proj_entry.get().strip()
        self.data["lakebase_project"] = name
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

    # ── Page 11: Summary ────────────────────────────────────────────────
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
                    # Auto-advance to complete page (index 12)
                    self.after(500, lambda: self.show_page(12))
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

        def advance(step_name: str):
            nonlocal step
            step += 1
            self._set_progress(step / total_steps)
            self._log(f"\u2713 {step_name}")
            s["setup_log"].append(f"\u2713 {step_name}")

        def fail(step_name: str, err: str):
            self._log(f"\u2717 {step_name}: {err}")
            s["setup_failed_steps"].append(step_name)
            s["setup_log"].append(f"\u2717 {step_name}: {err}")
            nonlocal step
            step += 1
            self._set_progress(step / total_steps)

        try:
            self._log(t("セットアップを開始します...", "Starting setup..."))
            self._log(f"  Profile: {profile}, Host: {host[:50]}...")
            self._log(f"  Catalog: {catalog}, Schema: {schema}")
            self._log("")

            # Step 1: Create catalog & schema
            self._log(t("カタログ・スキーマを作成中...", "Creating catalog & schema..."))
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
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
                with contextlib.redirect_stdout(buf):
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
                with contextlib.redirect_stdout(buf):
                    core.enable_cdf(token, host, warehouse_id, catalog, schema)
                output = buf.getvalue()
                if output.strip():
                    self._log(output.strip())
                advance(t("CDF \u6709\u52b9\u5316\u5b8c\u4e86", "CDF enabled"))
            except Exception as e:
                fail(t("CDF", "CDF"), str(e)[:200])

            # Step 4: Create Vector Search index
            vs_index = f"{catalog}.{schema}.policy_docs_index"
            if vs_endpoint:
                self._log(t("Vector Search \u30a4\u30f3\u30c7\u30c3\u30af\u30b9\u3092\u4f5c\u6210\u4e2d...", "Creating Vector Search index..."))
                try:
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        vs_index = core.create_vector_search_index(
                            token, host, catalog, schema, vs_endpoint)
                    output = buf.getvalue()
                    if output.strip():
                        self._log(output.strip())
                    s["vs_index"] = vs_index
                    advance(t(f"VS \u30a4\u30f3\u30c7\u30c3\u30af\u30b9: {vs_index}", f"VS index: {vs_index}"))
                except Exception as e:
                    s["vs_index"] = vs_index
                    fail(t("VS \u30a4\u30f3\u30c7\u30c3\u30af\u30b9", "VS index"), str(e)[:200])
            else:
                s["vs_index"] = vs_index
                self._log(t("\u26a0 VS \u30a8\u30f3\u30c9\u30dd\u30a4\u30f3\u30c8\u672a\u6307\u5b9a\uff08\u30a4\u30f3\u30c7\u30c3\u30af\u30b9\u306f\u624b\u52d5\u4f5c\u6210\u304c\u5fc5\u8981\uff09",
                           "\u26a0 VS endpoint not specified (manual index creation needed)"))
                step += 1
                self._set_progress(step / total_steps)

            # Step 5: Create Genie Space
            self._log(t("Genie Space \u3092\u4f5c\u6210\u4e2d...", "Creating Genie Space..."))
            try:
                tables = ["customers", "products", "stores", "transactions",
                          "transaction_items", "payment_history"]
                serialized = core._build_serialized_space(catalog, schema, tables)
                body = {
                    "title": "\u30d5\u30ec\u30c3\u30b7\u30e5\u30de\u30fc\u30c8 \u5c0f\u58f2\u30c7\u30fc\u30bf",
                    "description": "\u30d5\u30ec\u30c3\u30b7\u30e5\u30de\u30fc\u30c8\u306e\u5c0f\u58f2\u30c7\u30fc\u30bf\u306b\u5bfe\u3059\u308b\u81ea\u7136\u8a00\u8a9e\u30af\u30a8\u30ea\u3002",
                    "warehouse_id": warehouse_id,
                    "serialized_space": serialized,
                }
                result = core.api_post("/api/2.0/genie/spaces", token, host, body)
                genie_space_id = result.get("space_id", "")
                if genie_space_id:
                    s["genie_space_id"] = genie_space_id
                    advance(t(f"Genie Space \u4f5c\u6210\u5b8c\u4e86 (ID: {genie_space_id})", f"Genie Space created (ID: {genie_space_id})"))
                else:
                    err_msg = str(result.get("error", "unknown"))[:100]
                    fail(t("Genie Space", "Genie Space"), err_msg)
            except Exception as e:
                fail(t("Genie Space", "Genie Space"), str(e)[:200])

            # Step 6: Setup Lakebase
            lakebase_config = None
            if s.get("lakebase_required") and s.get("lakebase_project"):
                self._log(t("Lakebase \u3092\u8a2d\u5b9a\u4e2d...", "Setting up Lakebase..."))
                try:
                    lb_mode = s.get("lakebase_mode", "new")
                    if lb_mode == "new":
                        buf = io.StringIO()
                        # For GUI, we create the instance programmatically
                        w = core.get_workspace_client(profile)
                        if w:
                            from databricks.sdk.service.postgres import Branch, BranchSpec, Project, ProjectSpec
                            project_name = s["lakebase_project"]
                            project_op = w.postgres.create_project(
                                project=Project(spec=ProjectSpec(display_name=project_name)),
                                project_id=project_name,
                            )
                            project = project_op.wait()
                            project_short = project.name.removeprefix("projects/")

                            branch_id = f"{project_name}-branch"
                            branch_op = w.postgres.create_branch(
                                parent=project.name,
                                branch=Branch(spec=BranchSpec(no_expiry=True)),
                                branch_id=branch_id,
                            )
                            branch = branch_op.wait()
                            branch_name = (
                                branch.name.split("/branches/")[-1]
                                if "/branches/" in branch.name
                                else branch_id
                            )
                            s["lakebase_project"] = project_short
                            s["lakebase_branch"] = branch_name
                            self._log(t(f"  \u30d7\u30ed\u30b8\u30a7\u30af\u30c8\u4f5c\u6210\u5b8c\u4e86: {project_short} / \u30d6\u30e9\u30f3\u30c1: {branch_name}",
                                         f"  Created project: {project_short} / branch: {branch_name}"))

                    # Validate
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        branch_info = core.validate_lakebase_autoscaling(
                            profile, s["lakebase_project"], s.get("lakebase_branch", "")
                        )
                    output = buf.getvalue()
                    if output.strip():
                        self._log(output.strip())

                    if branch_info:
                        lakebase_config = {
                            "type": "autoscaling",
                            "project": s["lakebase_project"],
                            "branch": s.get("lakebase_branch", ""),
                            "database_id": branch_info.get("database_id", ""),
                        }
                        s["lakebase_config"] = lakebase_config
                        core.update_env_file("LAKEBASE_AUTOSCALING_PROJECT", lakebase_config["project"])
                        core.update_env_file("LAKEBASE_AUTOSCALING_BRANCH", lakebase_config["branch"])
                        pg_host = branch_info.get("host", "")
                        if pg_host:
                            core.update_env_file("PGHOST", pg_host)
                        core.update_env_file("PGUSER", username)
                        core.update_env_file("PGDATABASE", "databricks_postgres")
                        advance(t("Lakebase \u8a2d\u5b9a\u5b8c\u4e86", "Lakebase configured"))
                    else:
                        fail(t("Lakebase", "Lakebase"), t("\u691c\u8a3c\u306b\u5931\u6557", "Validation failed"))
                except Exception as e:
                    fail(t("Lakebase", "Lakebase"), str(e)[:200])
            else:
                step += 1
                self._set_progress(step / total_steps)

            # Step 7: Create MLflow experiments
            self._log(t("MLflow Experiments \u3092\u8a2d\u5b9a\u4e2d...", "Setting up MLflow Experiments..."))
            try:
                if s.get("mlflow_mode") == "new":
                    base = s.get("mlflow_base_name") or f"/Users/{username}/freshmart-agent"
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        m_name, m_id = core._create_single_experiment(profile, f"{base}-monitoring")
                        e_name, e_id = core._create_single_experiment(profile, f"{base}-evaluation")
                    output = buf.getvalue()
                    if output.strip():
                        self._log(output.strip())
                    s["monitoring_name"] = m_name
                    s["monitoring_id"] = m_id
                    s["eval_name"] = e_name
                    s["eval_id"] = e_id
                # else: IDs already stored from page 8
                advance(t(f"MLflow Experiments: {s['monitoring_id']} / {s['eval_id']}",
                           f"MLflow Experiments: {s['monitoring_id']} / {s['eval_id']}"))
            except Exception as e:
                fail(t("MLflow", "MLflow"), str(e)[:200])

            # Step 8: Run trace setup
            if s.get("trace_dest_mode") == "delta" and s.get("trace_dest_schema"):
                self._log(t("\u30c8\u30ec\u30fc\u30b9\u30c6\u30fc\u30d6\u30eb\u3092\u4f5c\u6210\u4e2d...", "Creating trace tables..."))
                try:
                    dest = s["trace_dest_schema"]
                    core.update_env_file("MLFLOW_TRACING_DESTINATION", dest)
                    core.update_env_file("MLFLOW_TRACING_SQL_WAREHOUSE_ID", warehouse_id)
                    core.append_env_to_app_yaml("MLFLOW_TRACING_DESTINATION", dest)
                    core.append_env_to_app_yaml("MLFLOW_TRACING_SQL_WAREHOUSE_ID", warehouse_id)
                    if "." in dest:
                        _cat, _sch = dest.split(".", 1)
                        buf = io.StringIO()
                        with contextlib.redirect_stdout(buf):
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

                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    core.update_databricks_yml_experiment(monitoring_id)
                    core.update_databricks_yml_resources(genie_space_id, vs_index_val)
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
                advance(t("Prompt Registry: スキップ", "Prompt Registry: Skipped"))

            # Step 11: Install dependencies
            self._log(t("\u4f9d\u5b58\u95a2\u4fc2\u3092\u30a4\u30f3\u30b9\u30c8\u30fc\u30eb\u4e2d...", "Installing dependencies..."))
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    core.install_dependencies()
                output = buf.getvalue()
                if output.strip():
                    self._log(output.strip())
                advance(t("\u4f9d\u5b58\u95a2\u4fc2\u30a4\u30f3\u30b9\u30c8\u30fc\u30eb\u5b8c\u4e86", "Dependencies installed"))
            except Exception as e:
                fail(t("\u4f9d\u5b58\u95a2\u4fc2", "Dependencies"), str(e)[:200])

        except Exception as e:
            import traceback
            self._log(f"\n✗ Fatal error: {e}")
            self._log(traceback.format_exc())
        finally:
            self._log(t("\nセットアップ完了！", "\nSetup complete!"))
            self._signal_done()

    # ── Page 13: Complete ───────────────────────────────────────────────
    def _page_complete(self, frame: customtkinter.CTkFrame):
        customtkinter.CTkLabel(
            frame,
            text=t("\u30bb\u30c3\u30c8\u30a2\u30c3\u30d7\u5b8c\u4e86\uff01", "Setup Complete!"),
            font=customtkinter.CTkFont(size=22, weight="bold"),
        ).pack(pady=(15, 5))

        # Show warnings about failed steps
        failed = self.data.get("setup_failed_steps", [])
        if failed:
            customtkinter.CTkLabel(
                frame,
                text=t(
                    f"\u26a0 {len(failed)} \u500b\u306e\u30b9\u30c6\u30c3\u30d7\u304c\u5931\u6557\u3057\u307e\u3057\u305f: {', '.join(failed)}",
                    f"\u26a0 {len(failed)} step(s) failed: {', '.join(failed)}",
                ),
                text_color="orange",
                wraplength=600,
            ).pack(pady=(0, 5))

        # Summary of created resources
        s = self.data
        summary_lines = [
            f"{t('\u30ab\u30bf\u30ed\u30b0', 'Catalog')}: {s.get('catalog', '')}",
            f"{t('\u30b9\u30ad\u30fc\u30de', 'Schema')}: {s.get('catalog', '')}.{s.get('schema', '')}",
            f"Vector Search: {s.get('vs_index', '')}",
            f"Genie Space ID: {s.get('genie_space_id', '')}",
            f"{t('\u30e2\u30cb\u30bf\u30ea\u30f3\u30b0 Exp', 'Monitoring Exp')}: {s.get('monitoring_id', '')}",
            f"{t('\u8a55\u4fa1 Exp', 'Evaluation Exp')}: {s.get('eval_id', '')}",
        ]
        lakebase_config = s.get("lakebase_config")
        if lakebase_config:
            summary_lines.append(
                f"Lakebase: {lakebase_config.get('project', '')} (branch: {lakebase_config.get('branch', '')})"
            )
        if s.get("trace_dest_mode") == "delta" and s.get("trace_dest_schema"):
            summary_lines.append(
                f"{t('\u30c8\u30ec\u30fc\u30b9\u9001\u4fe1\u5148', 'Trace Dest')}: {s['trace_dest_schema']}"
            )

        summary_text = "\n".join(summary_lines)

        customtkinter.CTkLabel(
            frame,
            text=t("\u4f5c\u6210\u3055\u308c\u305f\u30ea\u30bd\u30fc\u30b9", "Created Resources"),
            font=customtkinter.CTkFont(size=16, weight="bold"),
        ).pack(pady=(5, 2), anchor="w", padx=30)

        res_box = customtkinter.CTkTextbox(frame, width=600, height=130)
        res_box.pack(padx=30, pady=(0, 5))
        res_box.insert("0.0", summary_text)
        res_box.configure(state="disabled")

        # Team sharing info
        customtkinter.CTkLabel(
            frame,
            text=t("\u30c1\u30fc\u30e0\u5171\u6709\u60c5\u5831", "Team Sharing Info"),
            font=customtkinter.CTkFont(size=16, weight="bold"),
        ).pack(pady=(5, 2), anchor="w", padx=30)

        share_lines = [
            f"{t('\u30ab\u30bf\u30ed\u30b0\u540d', 'Catalog')}: {s.get('catalog', '')}",
            f"{t('\u30b9\u30ad\u30fc\u30de\u540d', 'Schema')}: {s.get('schema', '')}",
            f"{t('VS \u30a8\u30f3\u30c9\u30dd\u30a4\u30f3\u30c8', 'VS Endpoint')}: {s.get('vs_endpoint', '')}",
            f"Genie Space ID: {s.get('genie_space_id', '')}",
        ]
        if lakebase_config:
            share_lines.append(f"{t('Lakebase \u30d7\u30ed\u30b8\u30a7\u30af\u30c8', 'Lakebase project')}: {lakebase_config.get('project', '')}")
            share_lines.append(f"{t('Lakebase \u30d6\u30e9\u30f3\u30c1', 'Lakebase branch')}: {lakebase_config.get('branch', '')}")
        share_lines.append(f"{t('\u30e2\u30cb\u30bf\u30ea\u30f3\u30b0 Exp ID', 'Monitoring Exp ID')}: {s.get('monitoring_id', '')}")
        share_lines.append(f"{t('\u8a55\u4fa1 Exp ID', 'Evaluation Exp ID')}: {s.get('eval_id', '')}")

        self._share_text = "\n".join(share_lines)

        share_box = customtkinter.CTkTextbox(frame, width=600, height=100)
        share_box.pack(padx=30, pady=(0, 5))
        share_box.insert("0.0", self._share_text)
        share_box.configure(state="disabled")

        btn_frame = customtkinter.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(pady=5)

        customtkinter.CTkButton(
            btn_frame,
            text=t("\u30af\u30ea\u30c3\u30d7\u30dc\u30fc\u30c9\u306b\u30b3\u30d4\u30fc", "Copy to Clipboard"),
            width=180,
            command=self._copy_share_text,
        ).pack(side="left", padx=10)

        customtkinter.CTkButton(
            btn_frame,
            text=t("\u9589\u3058\u308b", "Close"),
            width=120,
            command=self.destroy,
        ).pack(side="left", padx=10)

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
