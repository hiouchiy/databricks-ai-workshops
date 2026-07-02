#!/usr/bin/env python3
"""Shared business logic for quickstart (CUI and GUI)."""

import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path


# ── i18n ──────────────────────────────────────────────────────────────
LANG = "ja"  # default; overridden by set_language()


def set_language(lang: str):
    """Set the global language from outside (CUI or GUI)."""
    global LANG
    LANG = lang


def t(ja: str, en: str) -> str:
    """Return the string for the current language."""
    return ja if LANG == "ja" else en


# ── Display helpers ──────────────────────────────────────────────────


def print_header(text: str) -> None:
    """Print a section header."""
    print(f"\n{'=' * 67}")
    print(text)
    print("=" * 67)


def print_step(text: str) -> None:
    """Print a step indicator."""
    print(f"\n{text}")


def print_success(text: str) -> None:
    """Print a success message."""
    print(f"✓ {text}")


def print_error(text: str) -> None:
    """Print an error message."""
    print(f"✗ {text}", file=sys.stderr)


def print_troubleshooting_auth() -> None:
    print(t("\nトラブルシューティング:", "\nTroubleshooting tips:"))
    print(t("  • Databricks ワークスペースへのネットワーク接続を確認してください",
            "  • Ensure you have network connectivity to your Databricks workspace"))
    print(t("  • 'databricks auth login' を手動で実行して詳細エラーを確認してください",
            "  • Try running 'databricks auth login' manually to see detailed errors"))
    print(t("  • ワークスペース URL が正しいか確認してください",
            "  • Check that your workspace URL is correct"))
    print(t("  • ブラウザで OAuth を使用する場合、ポップアップがブロックされていないか確認してください",
            "  • If using a browser for OAuth, ensure popups are not blocked"))


def print_troubleshooting_api() -> None:
    print(t("\nトラブルシューティング:", "\nTroubleshooting tips:"))
    print(t("  • 認証トークンが期限切れの可能性があります。'databricks auth login' でリフレッシュしてください",
            "  • Your authentication token may have expired - try 'databricks auth login' to refresh"))
    print(t("  • 'databricks auth profiles' でプロファイルが有効か確認してください",
            "  • Verify your profile is valid with 'databricks auth profiles'"))
    print(t("  • Databricks ワークスペースへのネットワーク接続を確認してください",
            "  • Check network connectivity to your Databricks workspace"))


# ── Command helpers ──────────────────────────────────────────────────


def command_exists(cmd: str) -> bool:
    """Check if a command exists in PATH."""
    return shutil.which(cmd) is not None


def run_command(
    cmd: list[str],
    capture_output: bool = True,
    check: bool = True,
    env: dict = None,
    show_output: bool = False,
) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    merged_env = {**os.environ, **(env or {})}
    if show_output:
        return subprocess.run(cmd, check=check, env=merged_env)
    return subprocess.run(
        cmd, capture_output=capture_output, text=True, check=check, env=merged_env
    )


def get_command_output(cmd: list[str], env: dict = None) -> str:
    """Run a command and return its stdout."""
    result = run_command(cmd, env=env)
    return result.stdout.strip()


# ── Prerequisites ────────────────────────────────────────────────────


def check_prerequisites() -> dict[str, bool]:
    """Check which prerequisites are installed."""
    print_step(t("前提条件を確認中...", "Checking prerequisites..."))

    prereqs = {
        "uv": command_exists("uv"),
        "node": command_exists("node"),
        "npm": command_exists("npm"),
        "databricks": command_exists("databricks"),
    }

    for name, installed in prereqs.items():
        if installed:
            try:
                if name == "uv":
                    version = get_command_output(["uv", "--version"])
                elif name == "node":
                    version = get_command_output(["node", "--version"])
                elif name == "npm":
                    version = get_command_output(["npm", "--version"])
                elif name == "databricks":
                    version = get_command_output(["databricks", "--version"])
                print_success(t(f"{name} インストール済み: {version}",
                                f"{name} is installed: {version}"))
            except Exception:
                print_success(t(f"{name} インストール済み",
                                f"{name} is installed"))
        else:
            print(t(f"  {name} がインストールされていません",
                     f"  {name} is not installed"))

    return prereqs


def check_missing_prerequisites(prereqs: dict[str, bool]) -> list[str]:
    """Return list of missing prerequisites with install instructions."""
    missing = []

    if not prereqs["uv"]:
        missing.append(t("uv - インストール: curl -LsSf https://astral.sh/uv/install.sh | sh",
                          "uv - Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"))

    if not prereqs["node"] or not prereqs["npm"]:
        missing.append(t("Node.js 20 - インストール: nvm install 20 (または nodejs.org からダウンロード)",
                          "Node.js 20 - Install with: nvm install 20 (or download from nodejs.org)"))

    if not prereqs["databricks"]:
        if platform.system() == "Darwin":
            missing.append(t("Databricks CLI - インストール: brew install databricks/tap/databricks",
                              "Databricks CLI - Install with: brew install databricks/tap/databricks"))
        else:
            missing.append(t(
                "Databricks CLI - インストール: curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh",
                "Databricks CLI - Install with: curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh",
            ))

    if missing:
        missing.append(t(
            "注意: これらのインストールコマンドは Unix/macOS 用です。Windows の場合は各ツールの公式ドキュメントを参照してください。",
            "Note: These install commands are for Unix/macOS. For Windows, please visit the official documentation for each tool.",
        ))

    return missing


def check_node_version() -> str | None:
    """Check if the installed Node.js version meets Vite's requirements.

    Vite requires Node.js >=20.19, >=22.12, or >=23.
    Node 21.x is an odd-numbered release and not supported.

    Returns None if the version is OK, or an error string if not.
    """
    if not command_exists("node"):
        return None  # Missing node is handled by check_missing_prerequisites

    try:
        version_str = get_command_output(["node", "--version"])
    except Exception:
        return None

    match = re.match(r"v(\d+)\.(\d+)\.(\d+)", version_str)
    if not match:
        return None

    major, minor = int(match.group(1)), int(match.group(2))

    # Node 21.x is odd-numbered and not a Vite target
    if major == 21:
        return (
            f"Node.js {version_str} is not supported by Vite (odd-numbered release).\n"
            "  Please install Node.js 20.19+, 22.12+, or 23+.\n"
            "  Run: nvm install 22"
        )

    # Check supported version ranges
    if major == 20 and minor >= 19:
        return None
    if major == 22 and minor >= 12:
        return None
    if major >= 23:
        return None

    # Version is too old or unsupported
    if major == 20:
        return (
            f"Node.js {version_str} is too old for Vite (requires 20.19+).\n"
            f"  Your version: {version_str}\n"
            "  Run: nvm install 20  (to get latest 20.x)"
        )
    if major == 22:
        return (
            f"Node.js {version_str} is too old for Vite (requires 22.12+).\n"
            f"  Your version: {version_str}\n"
            "  Run: nvm install 22  (to get latest 22.x)"
        )

    if major < 20:
        return (
            f"Node.js {version_str} is too old for Vite (requires 20.19+).\n"
            f"  Your version: {version_str}\n"
            "  Run: nvm install 22"
        )

    return (
        f"Node.js {version_str} is not supported by Vite.\n"
        "  Vite requires Node.js 20.19+, 22.12+, or 23+.\n"
        "  Run: nvm install 22"
    )


# ── .env file management ────────────────────────────────────────────


def setup_env_file() -> None:
    """Copy .env.example to .env if it doesn't exist."""
    print_step(t("設定ファイルをセットアップ中...", "Setting up configuration files..."))

    env_local = Path(".env")
    env_example = Path(".env.example")

    if env_local.exists():
        print(t("  .env は既に存在します、コピーをスキップ...",
                 "  .env already exists, skipping copy..."))
    elif env_example.exists():
        shutil.copy(env_example, env_local)
        print_success(t(".env.example を .env にコピーしました",
                         "Copied .env.example to .env"))
    else:
        # Create a minimal .env
        env_local.write_text(
            "# Databricks configuration\n"
            "DATABRICKS_CONFIG_PROFILE=DEFAULT\n"
            "MLFLOW_EXPERIMENT_ID=\n"
            "MLFLOW_EVAL_EXPERIMENT_ID=\n"
            'MLFLOW_TRACKING_URI="databricks"\n'
            'MLFLOW_REGISTRY_URI="databricks-uc"\n'
        )
        print_success(t(".env を作成しました", "Created .env"))


def update_env_file(key: str, value: str) -> None:
    """Update or add a key-value pair in .env.

    Priority: if a commented-out line (``# KEY=...``) exists, replace it
    in-place so the value stays in its original position.  Any extra active
    or commented duplicates are removed.
    """
    env_file = Path(".env")

    if not env_file.exists():
        env_file.write_text(f"{key}={value}\n")
        return

    content = env_file.read_text()

    active_pattern = rf"^{re.escape(key)}=.*$"
    commented_pattern = rf"^#\s*{re.escape(key)}=.*$"

    has_active = re.search(active_pattern, content, re.MULTILINE)
    has_commented = re.search(commented_pattern, content, re.MULTILINE)

    if has_commented:
        # Replace at the commented line's position. Remove all active and
        # commented duplicates, then insert the value where the first
        # commented line was.
        insert_pos = has_commented.start()
        content = re.sub(commented_pattern + r"\n?", "", content, flags=re.MULTILINE)
        content = re.sub(active_pattern + r"\n?", "", content, flags=re.MULTILINE)
        content = content[:insert_pos] + f"{key}={value}\n" + content[insert_pos:]
    elif has_active:
        # No commented line — replace the active line in-place
        content = re.sub(active_pattern, f"{key}={value}", content, flags=re.MULTILINE)
    else:
        # Key doesn't exist at all — append
        if not content.endswith("\n"):
            content += "\n"
        content += f"{key}={value}\n"

    env_file.write_text(content)


def read_env_file() -> dict[str, str]:
    """Read all key-value pairs from .env into a dict."""
    env_file = Path(".env")
    if not env_file.exists():
        return {}
    result = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result


def get_env_value(key: str) -> str:
    """Get a value from .env file."""
    env_file = Path(".env")
    if not env_file.exists():
        return ""

    content = env_file.read_text()
    pattern = rf"^{re.escape(key)}=(.*)$"
    match = re.search(pattern, content, re.MULTILINE)
    if match:
        return match.group(1).strip().strip('"').strip("'")
    return ""


# ── Databricks auth ─────────────────────────────────────────────────


def get_databricks_profiles() -> list[dict]:
    """Get list of existing Databricks profiles."""
    try:
        result = run_command(["databricks", "auth", "profiles"], check=False)
        if result.returncode != 0 or not result.stdout.strip():
            return []

        lines = result.stdout.strip().split("\n")
        if len(lines) <= 1:  # Only header or empty
            return []

        # Parse the output - first line is header
        profiles = []
        for line in lines[1:]:
            if line.strip():
                # Profile name is the first column
                parts = line.split()
                if parts:
                    profiles.append(
                        {
                            "name": parts[0],
                            "line": line,
                        }
                    )

        return profiles
    except Exception:
        return []


def validate_profile(profile_name: str) -> bool:
    """Test if a Databricks profile is authenticated."""
    try:
        env = {"DATABRICKS_CONFIG_PROFILE": profile_name}
        result = run_command(
            ["databricks", "current-user", "me"],
            check=False,
            env=env,
        )
        return result.returncode == 0
    except Exception:
        return False


def authenticate_profile(profile_name: str, host: str = None) -> bool:
    """Authenticate a Databricks profile."""
    print(t(f"\nプロファイル '{profile_name}' を認証中...",
            f"\nAuthenticating profile '{profile_name}'..."))
    print(t("ブラウザで Databricks にログインするよう求められます。\n",
            "You will be prompted to log in to Databricks in your browser.\n"))

    cmd = ["databricks", "auth", "login", "--profile", profile_name]
    if host:
        cmd.extend(["--host", host])

    try:
        # Run interactively so user can see browser prompt
        result = subprocess.run(cmd)
        return result.returncode == 0
    except Exception as e:
        print_error(t(f"認証に失敗しました: {e}",
                       f"Authentication failed: {e}"))
        return False


def select_profile_interactive(profiles: list[dict]) -> str:
    """Let user select a profile interactively."""
    print(t("\n既存の Databricks プロファイル:\n",
            "\nFound existing Databricks profiles:\n"))

    # Print header and profiles
    for i, profile in enumerate(profiles, 1):
        print(f"  {i}) {profile['line']}")

    print()

    while True:
        choice = input(t("使用するプロファイルの番号を入力してください: ",
                          "Enter the number of the profile you want to use: ")).strip()
        if not choice:
            print_error(t("プロファイルの選択は必須です",
                           "Profile selection is required"))
            continue

        try:
            index = int(choice) - 1
            if 0 <= index < len(profiles):
                return profiles[index]["name"]
            else:
                print_error(t(f"1 から {len(profiles)} の番号を選択してください",
                               f"Please choose a number between 1 and {len(profiles)}"))
        except ValueError:
            print_error(t("有効な番号を入力してください",
                           "Please enter a valid number"))


def setup_databricks_auth(profile_arg: str = None, host_arg: str = None) -> str:
    """Set up Databricks authentication and return the profile name."""
    print_step(t("Databricks 認証をセットアップ中...",
                  "Setting up Databricks authentication..."))

    # If profile was specified via CLI, use it directly
    if profile_arg:
        profile_name = profile_arg
        print(t(f"指定されたプロファイルを使用: {profile_name}",
                 f"Using specified profile: {profile_name}"))
    else:
        # Check for existing profiles
        profiles = get_databricks_profiles()

        if profiles:
            profile_name = select_profile_interactive(profiles)
            print(t(f"\n選択されたプロファイル: {profile_name}",
                     f"\nSelected profile: {profile_name}"))
        else:
            # No profiles exist - need to create one
            profile_name = None

    # Validate or authenticate the profile
    if profile_name:
        if validate_profile(profile_name):
            print_success(t(f"プロファイル '{profile_name}' の検証に成功しました",
                             f"Successfully validated profile '{profile_name}'"))
        else:
            print(t(f"プロファイル '{profile_name}' は認証されていません。",
                     f"Profile '{profile_name}' is not authenticated."))
            if not authenticate_profile(profile_name):
                print_error(t(f"プロファイル '{profile_name}' の認証に失敗しました",
                               f"Failed to authenticate profile '{profile_name}'"))
                print_troubleshooting_auth()
                sys.exit(1)
            print_success(t(f"プロファイル '{profile_name}' の認証に成功しました",
                             f"Successfully authenticated profile '{profile_name}'"))
    else:
        # Create new profile
        print(t("既存のプロファイルが見つかりません。Databricks 認証をセットアップ中...",
                 "No existing profiles found. Setting up Databricks authentication..."))

        if host_arg:
            host = host_arg
            print(t(f"指定されたホストを使用: {host}",
                     f"Using specified host: {host}"))
        else:
            host = input(t(
                "\nDatabricks ホスト URL を入力してください\n(例: https://your-workspace.cloud.databricks.com): ",
                "\nPlease enter your Databricks host URL\n(e.g., https://your-workspace.cloud.databricks.com): ",
            )).strip()

            if not host:
                print_error(t("Databricks ホストは必須です",
                               "Databricks host is required"))
                sys.exit(1)

        profile_name = "DEFAULT"
        if not authenticate_profile(profile_name, host):
            print_error(t("Databricks 認証に失敗しました",
                           "Databricks authentication failed"))
            print_troubleshooting_auth()
            sys.exit(1)
        print_success(t("Databricks 認証に成功しました",
                         "Successfully authenticated with Databricks"))

    # Update .env with profile
    update_env_file("DATABRICKS_CONFIG_PROFILE", profile_name)
    update_env_file("MLFLOW_TRACKING_URI", f'"databricks://{profile_name}"')
    print_success(t(f"Databricks プロファイル '{profile_name}' を .env に保存しました",
                     f"Databricks profile '{profile_name}' saved to .env"))

    return profile_name


def get_databricks_host(profile_name: str) -> str:
    """Get the Databricks workspace host URL from the profile."""
    try:
        result = run_command(
            ["databricks", "auth", "env", "--profile", profile_name, "--output", "json"],
            check=False,
        )
        if result.returncode == 0:
            env_data = json.loads(result.stdout)
            env_vars = env_data.get("env", {})
            host = env_vars.get("DATABRICKS_HOST", "")
            return host.rstrip("/")
    except Exception:
        pass
    return ""


def get_databricks_username(profile_name: str) -> str:
    """Get the current Databricks username."""
    try:
        result = run_command(
            ["databricks", "-p", profile_name, "current-user", "me", "--output", "json"]
        )
        user_data = json.loads(result.stdout)
        return user_data.get("userName", "")
    except Exception as e:
        print_error(t(f"Databricks ユーザー名の取得に失敗しました: {e}",
                       f"Failed to get Databricks username: {e}"))
        print_troubleshooting_api()
        sys.exit(1)


# ── MLflow experiments ───────────────────────────────────────────────


def _create_single_experiment(profile_name: str, base_name: str) -> tuple[str, str]:
    """Create a single MLflow experiment and return (name, id)."""
    try:
        result = run_command(
            [
                "databricks",
                "-p",
                profile_name,
                "experiments",
                "create-experiment",
                base_name,
                "--output",
                "json",
            ],
            check=False,
        )

        if result.returncode == 0:
            experiment_id = json.loads(result.stdout).get("experiment_id", "")
            print_success(t(f"Experiment '{base_name}' を作成しました (ID: {experiment_id})",
                             f"Created experiment '{base_name}' with ID: {experiment_id}"))
            return base_name, experiment_id

        # Name already exists, try with random suffix
        print(t(f"Experiment '{base_name}' は既に存在します。ランダムサフィックスで作成中...",
                 f"Experiment '{base_name}' already exists, creating with random suffix..."))
        random_suffix = secrets.token_hex(4)
        new_name = f"{base_name}-{random_suffix}"

        result = run_command(
            [
                "databricks",
                "-p",
                profile_name,
                "experiments",
                "create-experiment",
                new_name,
                "--output",
                "json",
            ]
        )
        experiment_id = json.loads(result.stdout).get("experiment_id", "")
        print_success(t(f"Experiment '{new_name}' を作成しました (ID: {experiment_id})",
                         f"Created experiment '{new_name}' with ID: {experiment_id}"))
        return new_name, experiment_id

    except Exception as e:
        print_error(t(f"MLflow Experiment '{base_name}' の作成に失敗しました: {e}",
                       f"Failed to create MLflow experiment '{base_name}': {e}"))
        print_troubleshooting_api()
        sys.exit(1)


def _verify_experiment(profile_name: str, exp_id: str) -> tuple[str, str]:
    """既存の Experiment ID を検証し、(name, id) を返す。見つからなければ ("", "")。"""
    result = run_command(
        ["databricks", "experiments", "get-experiment", exp_id, "-p", profile_name, "-o", "json"],
        check=False,
    )
    if result.returncode == 0:
        data = json.loads(result.stdout)
        exp = data.get("experiment", data)
        return exp.get("name", "?"), exp_id
    return "", ""


def create_mlflow_experiment(
    profile_name: str, username: str
) -> tuple[str, str, str, str]:
    """Create or reuse MLflow experiments. Returns
    (monitoring_name, monitoring_id, eval_name, eval_id)."""
    print_step(t("MLflow Experiment の設定", "MLflow Experiment setup"))
    print()
    print(t("  1) 新規作成（デフォルト）", "  1) Create new (default)"))
    print(t("  2) 既存の Experiment ID を入力（チームメンバー向け）",
            "  2) Enter existing Experiment ID (for team members)"))

    choice = input(t("\n  選択 [1]: ", "\n  Select [1]: ")).strip() or "1"

    if choice == "2":
        # 既存 ID の入力
        monitoring_name, monitoring_id = "", ""
        eval_name, eval_id = "", ""

        while not monitoring_id:
            mid = input(t("  モニタリング Experiment ID: ",
                           "  Monitoring Experiment ID: ")).strip()
            if not mid:
                print(t("  ID を入力してください。", "  Please enter an ID."))
                continue
            name, eid = _verify_experiment(profile_name, mid)
            if name:
                monitoring_name, monitoring_id = name, eid
                print_success(t(f"モニタリング Experiment 確認OK: {name} ({eid})",
                                 f"Monitoring Experiment verified: {name} ({eid})"))
            else:
                print_error(t(f"Experiment ID '{mid}' が見つかりません。もう一度入力してください。",
                               f"Experiment ID '{mid}' not found. Please try again."))

        while not eval_id:
            eid_input = input(t("  評価 Experiment ID: ",
                                 "  Evaluation Experiment ID: ")).strip()
            if not eid_input:
                print(t("  ID を入力してください。", "  Please enter an ID."))
                continue
            name, eid = _verify_experiment(profile_name, eid_input)
            if name:
                eval_name, eval_id = name, eid
                print_success(t(f"評価 Experiment 確認OK: {name} ({eid})",
                                 f"Evaluation Experiment verified: {name} ({eid})"))
            else:
                print_error(t(f"Experiment ID '{eid_input}' が見つかりません。もう一度入力してください。",
                               f"Experiment ID '{eid_input}' not found. Please try again."))

        return monitoring_name, monitoring_id, eval_name, eval_id

    # 新規作成
    print_step(t("MLflow Experiment を新規作成中...",
                  "Creating new MLflow Experiments..."))

    monitoring_name, monitoring_id = _create_single_experiment(
        profile_name, f"/Users/{username}/freshmart-agent-monitoring"
    )
    eval_name, eval_id = _create_single_experiment(
        profile_name, f"/Users/{username}/freshmart-agent-evaluation"
    )

    return monitoring_name, monitoring_id, eval_name, eval_id


# ── Lakebase ─────────────────────────────────────────────────────────


def check_lakebase_required() -> bool:
    """Check if databricks.yml has Lakebase autoscaling configuration."""
    databricks_yml = Path("databricks.yml")
    if not databricks_yml.exists():
        return False

    content = databricks_yml.read_text()
    return (
        "LAKEBASE_AUTOSCALING_PROJECT" in content
        or "LAKEBASE_AUTOSCALING_BRANCH" in content
    )


def get_workspace_client(profile_name: str):
    """Create a WorkspaceClient with the given profile."""
    try:
        from databricks.sdk import WorkspaceClient

        return WorkspaceClient(profile=profile_name)
    except Exception:
        return None


def list_lakebase_projects(profile_name: str) -> list[str]:
    """ワークスペースで参照できる Lakebase オートスケーリングプロジェクトIDの一覧を返す。

    GUI の「既存を使用」モードでドロップダウンを構築するために使う。
    SDK を呼べない／API エラー時は空リスト。
    """
    w = get_workspace_client(profile_name)
    if w is None:
        return []
    try:
        ids: list[str] = []
        for proj in w.postgres.list_projects():
            # Project.name は "projects/{id}" 形式。短縮 ID を取り出す。
            full = getattr(proj, "name", "") or ""
            short = full.removeprefix("projects/") if full.startswith("projects/") else full
            if short:
                ids.append(short)
        ids.sort()
        return ids
    except Exception:
        return []


def create_lakebase_instance(profile_name: str, default_name: str | None = None) -> dict:
    """Create a new Lakebase autoscaling instance (project + branch).

    Args:
        profile_name: Databricks CLI profile.
        default_name: 対話プロンプトで Enter を押したときに使われるデフォルト値。
            未指定なら入力必須。

    Returns:
        Dict with {"type": "autoscaling", "project": str, "branch": str}
    """
    w = get_workspace_client(profile_name)
    if not w:
        print_error(t("Databricks に接続できません。CLI プロファイルを確認してください。",
                       "Could not connect to Databricks. Check your CLI profile."))
        sys.exit(1)

    from databricks.sdk.service.postgres import Branch, BranchSpec, Project, ProjectSpec

    while True:
        if default_name:
            prompt = t(
                f"新しい Lakebase オートスケーリングプロジェクト名 [Enter で {default_name}]: ",
                f"Enter a name for the new Lakebase autoscaling project [Enter for {default_name}]: ",
            )
        else:
            prompt = t(
                "新しい Lakebase オートスケーリングプロジェクト名を入力: ",
                "Enter a name for the new Lakebase autoscaling project: ",
            )
        name = (input(prompt).strip() or default_name or "")
        if not name:
            print(t("  名前を入力してください。", "  Please enter a name."))
            continue

        # 公式制約: project_id は 1〜63 文字、英小文字 + 数字 + ハイフン、英字始まり。
        # branch_id = `{project}-branch` も 63 文字以内に収めるため、project は 56 文字までに制限。
        if len(name) > LAKEBASE_PROJECT_MAX_LENGTH:
            print_error(t(
                f"プロジェクト名は {LAKEBASE_PROJECT_MAX_LENGTH} 文字以内にしてください（現在 {len(name)} 文字）。",
                f"Project name must be ≤ {LAKEBASE_PROJECT_MAX_LENGTH} chars (currently {len(name)}).",
            ))
            continue
        if not re.match(r'^[a-z][a-z0-9-]*[a-z0-9]$', name):
            print_error(t(
                "プロジェクト名は英小文字・数字・ハイフンのみ使用できます。先頭は英小文字、末尾は英数字にしてください。",
                "Project name can only contain lowercase letters, digits, and hyphens. Must start with a lowercase letter and end with an alphanumeric.",
            ))
            continue

        # 既存プロジェクトをまず確認 — 同名があれば再利用
        try:
            existing = w.postgres.get_project(project_id=name)
            project_short = (
                existing.name.removeprefix("projects/")
                if existing.name else name
            )
            print_success(t(
                f"  既存の Lakebase プロジェクト '{project_short}' を再利用します",
                f"  Reusing existing Lakebase project '{project_short}'",
            ))
            # 既存プロジェクトの default branch も再利用 or 作成
            branch_id = f"{name}-branch"
            try:
                existing_branch = w.postgres.get_branch(name=f"projects/{name}/branches/{branch_id}")
                branch_name = (
                    existing_branch.name.split("/branches/")[-1]
                    if "/branches/" in existing_branch.name else branch_id
                )
                print_success(t(
                    f"  既存のブランチ '{branch_name}' を再利用します",
                    f"  Reusing existing branch '{branch_name}'",
                ))
            except Exception:
                # branch がなければ作成
                branch_op = w.postgres.create_branch(
                    parent=existing.name,
                    branch=Branch(spec=BranchSpec(no_expiry=True)),
                    branch_id=branch_id,
                )
                created_branch = branch_op.wait()
                branch_name = (
                    created_branch.name.split("/branches/")[-1]
                    if "/branches/" in created_branch.name else branch_id
                )
                print_success(t(f"ブランチ作成完了: {branch_name}",
                                 f"Created branch: {branch_name}"))
            return {"type": "autoscaling", "project": project_short, "branch": branch_name, "reused": True}
        except Exception:
            # 存在しない場合は新規作成へ進む
            pass

        print(t(f"\nLakebase オートスケーリングプロジェクト '{name}' を作成中...",
                 f"\nCreating Lakebase autoscaling project '{name}'..."))
        try:
            project_op = w.postgres.create_project(
                project=Project(spec=ProjectSpec(display_name=name)),
                project_id=name,
            )
            project = project_op.wait()
            project_short = project.name.removeprefix("projects/")
            print_success(t(f"プロジェクト作成完了: {project_short}",
                             f"Created project: {project_short}"))

            # Create a default branch
            branch_id = f"{name}-branch"
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
            print_success(t(f"ブランチ作成完了: {branch_name} (id: {branch.uid})",
                             f"Created branch: {branch_name} (id: {branch.uid})"))

            return {"type": "autoscaling", "project": project_short, "branch": branch_name}
        except Exception as e:
            err_msg = str(e)
            # 競合（並行作成等）で "already exists" が返ってきた場合は、
            # ループを再開すれば次の繰り返しで get_project が成功して再利用される。
            if "already exists" in err_msg.lower():
                print(t(
                    f"  プロジェクト '{name}' は既に存在しています。再利用します...",
                    f"  Project '{name}' already exists. Reusing...",
                ))
                continue
            print_error(t(f"作成に失敗しました: {err_msg[:200]}",
                           f"Creation failed: {err_msg[:200]}"))
            print(t("  名前を変えてもう一度試してください。",
                     "  Please try again with a different name."))
            continue


def select_lakebase_interactive(profile_name: str) -> dict:
    """Interactive Lakebase setup.

    Flow:
    1. New or existing?
    2. New -> Create autoscaling project + branch
    3. Existing -> Enter project + branch names
       - ブランチ名を空 Enter でユーザー個別ブランチ（{project}-{username}）を自動作成
       - 入力した名前が既存なら使用、存在しなければ新規作成

    Returns:
        Dict with {"type": "autoscaling", "project": str, "branch": str,
                   "branch_kind": "personal" | "entered-new" | "entered-existing"}
    """
    print(t("\nLakebase セットアップ", "\nLakebase Setup"))
    print(t("  1) 新しい Lakebase インスタンスを作成",
            "  1) Create a new Lakebase instance"))
    print(t("  2) 既存の Lakebase インスタンスを使用",
            "  2) Use an existing Lakebase instance"))
    print()

    while True:
        choice = input(t("選択してください (1 または 2): ",
                          "Enter your choice (1 or 2): ")).strip()
        if choice in ("1", "2"):
            break
        print_error(t("1 または 2 を入力してください",
                       "Please enter 1 or 2"))

    if choice == "1":
        username = get_databricks_username(profile_name)
        default_proj = compute_default_lakebase_project_name(username)
        return create_lakebase_instance(profile_name, default_name=default_proj)

    # Existing autoscaling instance - ask for project and branch
    project = input(t("\nオートスケーリングプロジェクト名を入力: ",
                       "\nEnter the autoscaling project name: ")).strip()
    if not project:
        print_error(t("プロジェクト名は必須です",
                       "Project name is required"))
        sys.exit(1)

    # ユーザー名ベースの個人ブランチ名を計算
    username = get_databricks_username(profile_name)
    user_slug = username.split("@")[0].replace(".", "-").lower()
    default_branch = f"{project}-{user_slug}"

    print(t(
        f"\n💡 Lakebase の特徴である高速ブランチングを活用します。",
        f"\n💡 Leveraging Lakebase's fast branching feature."))
    print(t(
        f"   デフォルトでメンバー個別のブランチ（{default_branch}）を作成します。",
        f"   Default: creates a personal branch ({default_branch})."))
    print(t(
        f"   既存ブランチを使いたい場合は、その名前を入力してください。",
        f"   To use an existing branch, enter its name."))

    branch = input(t(
        f"\nブランチ名 [{default_branch}]: ",
        f"\nBranch name [{default_branch}]: ")).strip() or default_branch

    # ブランチ存在確認
    result = run_command(
        ["databricks", "api", "get",
         f"/api/2.0/postgres/projects/{project}/branches/{branch}",
         "-p", profile_name, "-o", "json"],
        check=False,
    )
    branch_exists = (result.returncode == 0)

    if branch_exists:
        kind = "personal" if branch == default_branch else "entered-existing"
        print_success(t(f"既存ブランチを使用: {branch}",
                         f"Using existing branch: {branch}"))
        if kind == "entered-existing":
            print(t(
                "  ⚠ このブランチは他のユーザーが所有している可能性があります。",
                "  ⚠ This branch may be owned by another user."))
            print(t(
                "  代表者が `grant-team-access` であなたに権限を付与済みか確認してください。",
                "  Ensure the representative has run `grant-team-access` for you."))
    else:
        # 存在しないブランチ → 新規作成
        kind = "personal" if branch == default_branch else "entered-new"
        print(t(f"ブランチ {branch} を新規作成中（production から fork）...",
                 f"Creating branch {branch} (forked from production)..."))
        try:
            w = get_workspace_client(profile_name)
            from databricks.sdk.service.postgres import Branch, BranchSpec
            branch_op = w.postgres.create_branch(
                parent=f"projects/{project}",
                branch=Branch(spec=BranchSpec(no_expiry=True)),
                branch_id=branch,
            )
            created = branch_op.wait()
            branch = created.name.split("/branches/")[-1] if "/branches/" in created.name else branch
            print_success(t(f"ブランチ作成完了: {branch}",
                             f"Branch created: {branch}"))
        except Exception as e:
            print_error(t(f"ブランチ作成失敗: {str(e)[:200]}",
                           f"Branch creation failed: {str(e)[:200]}"))
            sys.exit(1)

    return {
        "type": "autoscaling",
        "project": project,
        "branch": branch,
        "branch_kind": kind,
    }


def validate_lakebase_autoscaling(profile_name: str, project: str, branch: str) -> dict | None:
    """Validate that the Lakebase autoscaling project and branch exist.

    Uses the postgres API (/api/2.0/postgres/) to verify the project and branch,
    then fetches the endpoint host for PGHOST.

    Returns a dict with {"host": str} on success (host may be empty if endpoint
    not found), or None on failure.
    """
    print(t(f"Lakebase オートスケーリング プロジェクト '{project}'、ブランチ '{branch}' を検証中...",
             f"Validating Lakebase autoscaling project '{project}', branch '{branch}'..."))

    # Validate project exists
    result = run_command(
        [
            "databricks",
            "-p",
            profile_name,
            "api",
            "get",
            f"/api/2.0/postgres/projects/{project}",
            "--output",
            "json",
        ],
        check=False,
    )

    if result.returncode != 0:
        error_msg = result.stderr.lower() if result.stderr else ""
        if "not found" in error_msg or "404" in error_msg:
            print_error(t(
                f"Lakebase オートスケーリングプロジェクト '{project}' が見つかりません。プロジェクト名を確認してください。",
                f"Lakebase autoscaling project '{project}' not found. Please check the project name.",
            ))
        elif "permission" in error_msg or "forbidden" in error_msg or "unauthorized" in error_msg:
            print_error(t(f"Lakebase プロジェクト '{project}' へのアクセス権がありません",
                           f"No permission to access Lakebase project '{project}'"))
        else:
            print_error(t(
                f"Lakebase プロジェクトの検証に失敗: {result.stderr.strip() if result.stderr else '不明なエラー'}",
                f"Failed to validate Lakebase project: {result.stderr.strip() if result.stderr else 'Unknown error'}",
            ))
        return None

    # Validate branch exists within the project
    result = run_command(
        [
            "databricks",
            "-p",
            profile_name,
            "api",
            "get",
            f"/api/2.0/postgres/projects/{project}/branches/{branch}",
            "--output",
            "json",
        ],
        check=False,
    )

    if result.returncode != 0:
        error_msg = result.stderr.lower() if result.stderr else ""
        if "not found" in error_msg or "404" in error_msg:
            print(t(f"  ブランチ '{branch}' がプロジェクト '{project}' に存在しません。",
                     f"  Branch '{branch}' does not exist in project '{project}'."))
            create_branch = input(t("  新規作成しますか？ (Y/n): ",
                                     "  Create it now? (Y/n): ")).strip().lower()
            if create_branch != "n":
                print(t(f"  ブランチ '{branch}' を作成中...",
                         f"  Creating branch '{branch}'..."))
                try:
                    w = get_workspace_client(profile_name)
                    from databricks.sdk.service.postgres import Branch, BranchSpec
                    branch_op = w.postgres.create_branch(
                        parent=f"projects/{project}",
                        branch=Branch(spec=BranchSpec(no_expiry=True)),
                        branch_id=branch,
                    )
                    created = branch_op.wait()
                    branch = (
                        created.name.split("/branches/")[-1]
                        if "/branches/" in created.name
                        else branch
                    )
                    print_success(t(f"ブランチ作成完了: {branch}",
                                     f"Branch created: {branch}"))
                except Exception as e:
                    print_error(t(f"ブランチ作成に失敗: {str(e)[:200]}",
                                   f"Branch creation failed: {str(e)[:200]}"))
                    return None
            else:
                print_error(t("ブランチ名を確認してください。",
                               "Please verify the branch name."))
                return None
        elif "permission" in error_msg or "forbidden" in error_msg or "unauthorized" in error_msg:
            print_error(t(f"Lakebase ブランチ '{branch}' へのアクセス権がありません",
                           f"No permission to access Lakebase branch '{branch}'"))
            return None
        else:
            print_error(t(
                f"Lakebase ブランチの検証に失敗: {result.stderr.strip() if result.stderr else '不明なエラー'}",
                f"Failed to validate Lakebase branch: {result.stderr.strip() if result.stderr else 'Unknown error'}",
            ))
            return None
    else:
        print_success(t(f"Lakebase オートスケーリング プロジェクト '{project}'、ブランチ '{branch}' の検証OK",
                         f"Lakebase autoscaling project '{project}', branch '{branch}' validated"))

    # Fetch endpoint host for PGHOST
    pg_host = ""
    result = run_command(
        [
            "databricks",
            "-p",
            profile_name,
            "api",
            "get",
            f"/api/2.0/postgres/projects/{project}/branches/{branch}/endpoints",
            "--output",
            "json",
        ],
        check=False,
    )
    if result.returncode == 0 and result.stdout:
        try:
            endpoints_data = json.loads(result.stdout)
            endpoints = endpoints_data.get("endpoints", [])
            if endpoints:
                host = (
                    endpoints[0].get("status", {}).get("hosts", {}).get("host", "")
                )
                if host:
                    pg_host = host
        except (json.JSONDecodeError, IndexError, KeyError):
            pass

    # Fetch database ID for the postgres resource binding in databricks.yml
    # The resource path uses the Lakebase database_id (e.g. "db-xxxx-yyyyyy"),
    # NOT the PostgreSQL database name ("databricks_postgres").
    database_id = ""
    result = run_command(
        [
            "databricks",
            "-p",
            profile_name,
            "api",
            "get",
            f"/api/2.0/postgres/projects/{project}/branches/{branch}/databases",
            "--output",
            "json",
        ],
        check=False,
    )
    if result.returncode == 0 and result.stdout:
        try:
            db_data = json.loads(result.stdout)
            databases = db_data.get("databases", [])
            if databases:
                database_id = databases[0].get("status", {}).get("database_id", "")
        except (json.JSONDecodeError, IndexError, KeyError):
            pass

    if not database_id:
        print_error(t("Lakebase ブランチから database ID を取得できませんでした。databricks.yml の postgres リソースを手動で修正する必要があるかもしれません。",
                       "Could not fetch database ID from Lakebase branch. The postgres resource in databricks.yml may need manual correction."))

    return {"host": pg_host, "database_id": database_id}


def setup_lakebase(
    profile_name: str,
    username: str,
    autoscaling_project: str = None,
    autoscaling_branch: str = None,
) -> dict:
    """Set up Lakebase instance for memory features.

    Returns:
        Dict with {"type": "autoscaling", "project": str, "branch": str, "database_id": str}
    """
    print_step(t("Lakebase インスタンスをセットアップ中...",
                  "Setting up Lakebase instance for memory..."))

    # If --lakebase-autoscaling-project and --lakebase-autoscaling-branch were provided
    if autoscaling_project and autoscaling_branch:
        print(t(f"オートスケーリング Lakebase を使用: project={autoscaling_project}, branch={autoscaling_branch}",
                 f"Using autoscaling Lakebase: project={autoscaling_project}, branch={autoscaling_branch}"))
        branch_info = validate_lakebase_autoscaling(profile_name, autoscaling_project, autoscaling_branch)
        if not branch_info:
            sys.exit(1)
        update_env_file("LAKEBASE_AUTOSCALING_PROJECT", autoscaling_project)
        update_env_file("LAKEBASE_AUTOSCALING_BRANCH", autoscaling_branch)

        # Set up PostgreSQL connection environment variables
        pg_host = branch_info.get("host", "")
        if pg_host:
            update_env_file("PGHOST", pg_host)
            print_success(f"PGHOST set to '{pg_host}'")
        else:
            print_error(t("Lakebase ブランチからエンドポイントホストを取得できませんでした (PGHOST 未設定)",
                           "Could not get endpoint host from Lakebase branch (PGHOST not set)"))

        update_env_file("PGUSER", username)
        print_success(f"PGUSER set to '{username}'")

        update_env_file("PGDATABASE", "databricks_postgres")
        print_success("PGDATABASE set to 'databricks_postgres'")

        print_success(t(
            f"Lakebase オートスケーリング設定を .env に保存 (project: {autoscaling_project}, branch: {autoscaling_branch})",
            f"Lakebase autoscaling config saved to .env (project: {autoscaling_project}, branch: {autoscaling_branch})",
        ))
        return {
            "type": "autoscaling",
            "project": autoscaling_project,
            "branch": autoscaling_branch,
            "database_id": branch_info.get("database_id", ""),
        }

    # Interactive selection
    selection = select_lakebase_interactive(profile_name)

    project = selection["project"]
    branch = selection["branch"]
    branch_info = validate_lakebase_autoscaling(profile_name, project, branch)
    if not branch_info:
        sys.exit(1)
    update_env_file("LAKEBASE_AUTOSCALING_PROJECT", project)
    update_env_file("LAKEBASE_AUTOSCALING_BRANCH", branch)

    # Set up PostgreSQL connection environment variables
    pg_host = branch_info.get("host", "")
    if pg_host:
        update_env_file("PGHOST", pg_host)
        print_success(f"PGHOST set to '{pg_host}'")
    else:
        print_error(t("Lakebase ブランチからエンドポイントホストを取得できませんでした (PGHOST 未設定)",
                       "Could not get endpoint host from Lakebase branch (PGHOST not set)"))

    update_env_file("PGUSER", username)
    print_success(f"PGUSER set to '{username}'")

    update_env_file("PGDATABASE", "databricks_postgres")
    print_success("PGDATABASE set to 'databricks_postgres'")

    print_success(t(
        f"Lakebase オートスケーリング設定を .env に保存 (project: {project}, branch: {branch})",
        f"Lakebase autoscaling config saved to .env (project: {project}, branch: {branch})",
    ))
    selection["database_id"] = branch_info.get("database_id", "")

    return selection


# ── YAML / config updates ───────────────────────────────────────────


def _replace_lakebase_env_vars(content: str, lakebase_config: dict) -> str:
    """Remove all Lakebase env var lines and insert only the relevant ones.

    Handles both active and commented-out LAKEBASE_ env vars, plus their
    associated comment lines (e.g. "# Autoscaling Lakebase config").
    """
    lines = content.splitlines()
    result = []
    insert_idx = None
    skip_next_value = False

    for line in lines:
        if skip_next_value:
            skip_next_value = False
            if re.match(r"\s*(?:#\s*)?(?:value|value_from)\s*:", line):
                continue
            # Not a value line — fall through to normal processing

        stripped = line.strip()

        # Match lakebase section comments
        bare = stripped.lstrip("#").strip().lower()
        if bare in (
            "autoscaling lakebase config",
            "use for provisioned lakebase resource",
            "provisioned lakebase config",
        ):
            if insert_idx is None:
                insert_idx = len(result)
            continue

        # Match LAKEBASE_ env var lines (active or commented)
        if re.search(r"- name: LAKEBASE_", stripped):
            if insert_idx is None:
                insert_idx = len(result)
            skip_next_value = True
            continue

        result.append(line)

    if insert_idx is None:
        return content

    # Detect indent from surrounding `- name:` env var lines
    indent = "          "
    for line in result:
        m = re.match(r"^(\s+)- name: ", line)
        if m:
            indent = m.group(1)
            break

    # Build replacement block with autoscaling env vars
    new_lines = [
        f"{indent}- name: LAKEBASE_AUTOSCALING_PROJECT",
        f'{indent}  value: "{lakebase_config["project"]}"',
        f"{indent}- name: LAKEBASE_AUTOSCALING_BRANCH",
        f'{indent}  value: "{lakebase_config["branch"]}"',
    ]

    final = result[:insert_idx] + new_lines + result[insert_idx:]
    return "\n".join(final) + "\n"


def _replace_lakebase_resource(content: str, lakebase_config: dict) -> str:
    """Update the Lakebase resource section in databricks.yml.

    Uses 'postgres' resource with project/branch paths for autoscaling.
    Removes any old provisioned 'database' resource blocks and associated comments.
    """
    # Comment patterns to strip (case-insensitive, prefix-matched after removing '#')
    LAKEBASE_COMMENT_PREFIXES = [
        "autoscaling postgres resource",
        "see: .claude/skills/add-tools/examples/lakebase-autoscaling",
        "use for provisioned lakebase resource",
        "provisioned lakebase config",
        "lakebase:",  # matches "Lakebase: ..." comments (including Japanese)
    ]

    def is_lakebase_comment(bare_text: str) -> bool:
        return any(bare_text.startswith(p) for p in LAKEBASE_COMMENT_PREFIXES)

    def _detect_indent(result_lines: list[str]) -> str | None:
        for prev in reversed(result_lines):
            m = re.match(r"^(\s+)- name:", prev)
            if m:
                return m.group(1)
        return None

    def _skip_block_uncommented(lines: list[str], i: int) -> int:
        """Skip subsequent lines of an uncommented resource block."""
        i += 1
        while i < len(lines):
            next_stripped = lines[i].strip()
            if next_stripped and not next_stripped.startswith("-") and not next_stripped.startswith("#"):
                i += 1
            else:
                break
        return i

    def _skip_block_commented(lines: list[str], i: int, keywords: set[str]) -> int:
        """Skip subsequent commented lines of a resource block matching any keyword."""
        i += 1
        while i < len(lines):
            next_stripped = lines[i].strip()
            if next_stripped.startswith("#") and any(kw in next_stripped for kw in keywords):
                i += 1
            else:
                break
        return i

    def _build_postgres_block(indent: str, project: str, branch: str, database_id: str) -> list[str]:
        return [
            f'{indent}- name: "postgres"',
            f"{indent}  postgres:",
            f'{indent}    branch: "projects/{project}/branches/{branch}"',
            f'{indent}    database: "projects/{project}/branches/{branch}/databases/{database_id}"',
            f"{indent}    permission: \"CAN_CONNECT_AND_CREATE\"",
        ]

    lines = content.splitlines()
    result = []
    i = 0
    emitted_lakebase_resource = False
    resource_indent = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        bare = stripped.lstrip("#").strip().lower()

        # Skip lakebase-related comment lines (env section and resources section)
        if stripped.startswith("#") and is_lakebase_comment(bare):
            i += 1
            continue

        # --- postgres resource (autoscaling) ---

        # Uncommented postgres resource
        if re.match(r"\s*- name:\s*['\"]?postgres['\"]?", stripped):
            if resource_indent is None:
                m = re.match(r"^(\s+)- name:", line)
                if m:
                    resource_indent = m.group(1)
            i = _skip_block_uncommented(lines, i)
            if not emitted_lakebase_resource:
                indent = resource_indent or "        "
                result.extend(_build_postgres_block(
                    indent, lakebase_config["project"], lakebase_config["branch"],
                    lakebase_config.get("database_id", "")))
                emitted_lakebase_resource = True
            continue

        # Commented-out postgres resource
        if re.match(r"\s*#\s*- name:\s*['\"]?postgres['\"]?", stripped):
            if resource_indent is None:
                resource_indent = _detect_indent(result)
            i = _skip_block_commented(
                lines, i, {"postgres:", "branch:", "database:", "permission:"})
            if not emitted_lakebase_resource:
                indent = resource_indent or "        "
                result.extend(_build_postgres_block(
                    indent, lakebase_config["project"], lakebase_config["branch"],
                    lakebase_config.get("database_id", "")))
                emitted_lakebase_resource = True
            continue

        # --- database resource (old provisioned) — remove entirely ---

        # Commented-out database resource
        if re.match(r"\s*#\s*- name:\s*['\"]?database['\"]?", stripped):
            if resource_indent is None:
                resource_indent = _detect_indent(result)
            i = _skip_block_commented(
                lines, i, {"database:", "instance_name:", "database_name:", "permission:"})
            continue

        # Uncommented database resource (from a previous provisioned run)
        if re.match(r"\s*- name:\s*['\"]?database['\"]?", stripped):
            if resource_indent is None:
                m = re.match(r"^(\s+)- name:", line)
                if m:
                    resource_indent = m.group(1)
            i = _skip_block_uncommented(lines, i)
            continue

        result.append(line)
        i += 1

    # If we didn't emit a lakebase resource yet (e.g. fresh YAML),
    # append after the last resource entry
    if not emitted_lakebase_resource:
        insert_idx = None
        for idx in range(len(result) - 1, -1, -1):
            if re.match(r"\s+- name:", result[idx]):
                insert_idx = idx + 1
                while insert_idx < len(result):
                    next_stripped = result[insert_idx].strip()
                    if next_stripped and not next_stripped.startswith("-") and not next_stripped.startswith("#"):
                        insert_idx += 1
                    else:
                        break
                if resource_indent is None:
                    m = re.match(r"^(\s+)- name:", result[idx])
                    if m:
                        resource_indent = m.group(1)
                break

        if insert_idx is not None:
            indent = resource_indent or "        "
            new_lines = _build_postgres_block(
                indent, lakebase_config["project"], lakebase_config["branch"],
                lakebase_config.get("database_id", ""))
            result = result[:insert_idx] + new_lines + result[insert_idx:]

    return "\n".join(result) + "\n"


def update_databricks_yml_lakebase(lakebase_config: dict) -> None:
    """Update databricks.yml: keep only the relevant Lakebase env vars and resources."""
    yml_path = Path("databricks.yml")
    if not yml_path.exists():
        return

    content = yml_path.read_text()
    updated = _replace_lakebase_env_vars(content, lakebase_config)
    updated = _replace_lakebase_resource(updated, lakebase_config)
    if updated != content:
        yml_path.write_text(updated)
        print_success(t("databricks.yml を Lakebase 設定で更新しました",
                         "Updated databricks.yml with Lakebase config"))


def update_app_yaml_lakebase(lakebase_config: dict) -> None:
    """Update app.yaml: keep only the relevant Lakebase env vars, remove the others."""
    app_yaml_path = Path("app.yaml")
    if not app_yaml_path.exists():
        return

    content = app_yaml_path.read_text()
    updated = _replace_lakebase_env_vars(content, lakebase_config)
    if updated != content:
        app_yaml_path.write_text(updated)
        print_success(t("app.yaml を Lakebase 設定で更新しました",
                         "Updated app.yaml with Lakebase config"))


def append_env_to_app_yaml(name: str, value: str) -> None:
    """app.yaml の env セクションに環境変数を追加する。既に存在する場合は値を更新。"""
    app_yaml_path = Path("app.yaml")
    if not app_yaml_path.exists():
        return

    content = app_yaml_path.read_text()

    # 既に存在する場合は値を更新
    pattern = rf'(- name: {re.escape(name)}\n\s+value: )"[^"]*"'
    if re.search(pattern, content):
        content = re.sub(pattern, rf'\1"{value}"', content)
        app_yaml_path.write_text(content)
        return

    # 存在しない場合は末尾に追加
    content = content.rstrip() + f'\n  - name: {name}\n    value: "{value}"\n'
    app_yaml_path.write_text(content)


def remove_env_from_app_yaml(name: str) -> None:
    """app.yaml の env セクションから指定された環境変数の定義を削除する。"""
    app_yaml_path = Path("app.yaml")
    if not app_yaml_path.exists():
        return

    content = app_yaml_path.read_text()
    # - name: KEY\n    value: "..." のペア（+ 後続改行）を削除
    pattern = rf'\s*- name: {re.escape(name)}\n\s+(?:value|valueFrom):[^\n]*\n?'
    new_content = re.sub(pattern, "\n", content, flags=re.MULTILINE)
    # 連続改行を整理
    new_content = re.sub(r"\n{3,}", "\n\n", new_content)
    if new_content != content:
        app_yaml_path.write_text(new_content)


def update_databricks_yml_experiment(experiment_id: str) -> None:
    """Update databricks.yml to set the experiment ID in the app resource."""
    yml_path = Path("databricks.yml")
    if not yml_path.exists():
        return

    content = yml_path.read_text()

    # Set the experiment_id in the app's experiment resource
    content = re.sub(
        r'(experiment_id: )"[^"]*"',
        f'\\1"{experiment_id}"',
        content,
    )

    yml_path.write_text(content)
    print_success(t("databricks.yml を Experiment ID で更新しました",
                     "Updated databricks.yml with experiment ID"))


def update_databricks_yml_resources(genie_space_id: str, vs_index: str) -> None:
    """Update databricks.yml: Genie Space ID and Vector Search index full name."""
    yml_path = Path("databricks.yml")
    if not yml_path.exists():
        return

    content = yml_path.read_text()

    # Genie Space ID
    content = re.sub(
        r'(space_id: )"[^"]*"',
        f'\\1"{genie_space_id}"',
        content,
    )

    # Vector Search index securable_full_name
    content = re.sub(
        r'(securable_full_name: )"[^"]*"',
        f'\\1"{vs_index}"',
        content,
    )

    yml_path.write_text(content)
    print_success(t("databricks.yml を Genie Space ID と VS インデックスで更新しました",
                     "Updated databricks.yml with Genie Space ID and VS index"))


# ── App name helpers ─────────────────────────────────────────────────

# Databricks App 名の制約（実測 — terraform apply のエラーメッセージで確認）：
#   - 小文字英数字とハイフンのみ
#   - 英字で始まり、英数で終わる
#   - 2〜30 文字
APP_NAME_PREFIX = "fm-agent"  # 短縮（旧: "freshmart-agent"。30 字上限に余裕を持たせるため）
APP_NAME_MIN_LENGTH = 2
APP_NAME_MAX_LENGTH = 30


def sanitize_app_name_part(value: str, prefer_first_segment: bool = True) -> str:
    """ユーザー名やemailをApp名に使える形に正規化する。

    Databricks App 名は 30 文字制限があるため、デフォルトではメールアドレスの
    `@` 以前の **最初のセグメント** （ドット区切りの先頭）のみ使う。
    例:
      'hiroshi.ouchiyama@databricks.com' -> 'hiroshi'   (prefer_first_segment=True、デフォルト)
      'hiroshi.ouchiyama@databricks.com' -> 'hiroshi-ouchiyama'  (prefer_first_segment=False)
      'Tanaka_Taro+x@example.co.jp'      -> 'tanaka'
      'a@b.com'                          -> 'a'
    """
    local = value.split("@", 1)[0].lower()
    if prefer_first_segment:
        # ドット区切りの先頭セグメントのみ採用（典型的な姓名 email を短縮）
        local = local.split(".", 1)[0]
    s = re.sub(r"[^a-z0-9]+", "-", local)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def compute_default_app_name(username: str, today: str | None = None) -> str:
    """`fm-agent-{user}-{MMDD}` を生成。Databricks App 名の 30 文字制限を守る。

    today: YYYY-MM-DD 形式の文字列（省略時は本日）。テスト用に注入可能。
    """
    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")
    mmdd = today.replace("-", "")[4:8]  # YYYY-MM-DD -> MMDD
    user_part = sanitize_app_name_part(username) or "user"

    suffix = f"-{mmdd}"
    base = f"{APP_NAME_PREFIX}-"
    budget = APP_NAME_MAX_LENGTH - len(base) - len(suffix)
    # ドット区切り先頭セグメントを採用しても 30 文字を超えるユーザー名は最後にハード切り詰め
    if len(user_part) > budget:
        user_part = user_part[:budget].rstrip("-")
    return f"{base}{user_part}{suffix}"


def is_valid_app_name(name: str) -> bool:
    """Databricks App 名のバリデーション。"""
    if not name or not (APP_NAME_MIN_LENGTH <= len(name) <= APP_NAME_MAX_LENGTH):
        return False
    return bool(re.match(r"^[a-z][a-z0-9-]*[a-z0-9]$", name))


# ── Lakebase project / branch 名 ──
# 公式制約（Lakebase Autoscaling）: 1〜63 文字、英小文字 + 数字 + ハイフン、英字始まり。
#   出典: docs.databricks.com/.../oltp/projects/limitations
# プロジェクト名は 56 文字に制限する。"new" モードでは branch_id が `{project}-branch`（+7）で
# 自動生成されるため、project ≤ 56 にしておけば branch も 63 以内に収まる。
LAKEBASE_PROJECT_PREFIX = "fm-lakebase"  # 短縮（旧: "freshmart-lakebase"）
LAKEBASE_PROJECT_MAX_LENGTH = 56  # branch="{project}-branch" でも 63 以内に収まる
LAKEBASE_BRANCH_MAX_LENGTH = 63   # API の絶対上限


def compute_default_lakebase_project_name(username: str, today: str | None = None) -> str:
    """`freshmart-lakebase-{user}-{MMDD}` を生成。`{project}-branch` も 63 文字に収まるよう制約。"""
    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")
    mmdd = today.replace("-", "")[4:8]
    user_part = sanitize_app_name_part(username) or "user"
    suffix = f"-{mmdd}"
    base = f"{LAKEBASE_PROJECT_PREFIX}-"
    budget = LAKEBASE_PROJECT_MAX_LENGTH - len(base) - len(suffix)
    if len(user_part) > budget:
        user_part = user_part[:budget].rstrip("-")
    return f"{base}{user_part}{suffix}"


def is_valid_lakebase_project_name(name: str) -> bool:
    """Lakebase プロジェクト名のバリデーション（branch="{project}-branch" 自動生成も考慮）。"""
    if not name or len(name) > LAKEBASE_PROJECT_MAX_LENGTH:
        return False
    return bool(re.match(r"^[a-z][a-z0-9-]*[a-z0-9]$", name))


def is_valid_lakebase_branch_name(name: str) -> bool:
    """Lakebase ブランチ名のバリデーション。"""
    if not name or len(name) > LAKEBASE_BRANCH_MAX_LENGTH:
        return False
    return bool(re.match(r"^[a-z][a-z0-9-]*[a-z0-9]$", name))


# ── Unity Catalog: Catalog / Schema 名 ──
# 公式仕様（docs.databricks.com/.../sql/language-manual/sql-ref-names）：
#   - 全 UC オブジェクト名は最大 255 文字
#   - 禁則文字: `.`、空白、`/`、ASCII 制御文字（0x00-0x1F）、DEL（0x7F）
#   - lowercase で保存される
# ワークショップでは SQL クエリでバッククォート不要にするため、より厳しく
# 「英数字 + アンダースコア」のみ許可し、上限を 100 文字に制限する（実用範囲）。
UC_NAME_MAX_LENGTH = 100


def validate_uc_object_name(name: str, kind: str = "catalog/schema") -> tuple[bool, str]:
    """Unity Catalog オブジェクト名（catalog / schema）のバリデーション。

    Returns:
        (is_valid, error_message). is_valid=True なら error_message は空文字。
    """
    if not name:
        return False, t(f"{kind} 名を入力してください", f"{kind} name is required")
    if len(name) > UC_NAME_MAX_LENGTH:
        return False, t(
            f"{kind} 名は {UC_NAME_MAX_LENGTH} 文字以内にしてください（現在 {len(name)} 文字）",
            f"{kind} name must be ≤ {UC_NAME_MAX_LENGTH} chars (currently {len(name)})",
        )
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
        return False, t(
            f"{kind} 名は英字またはアンダースコアで始まり、英数字・アンダースコアのみ使用できます",
            f"{kind} name must start with letter/underscore and contain only alphanumeric/underscore",
        )
    return True, ""


# ── SQL Warehouse 名 ──
# 公式に厳密な上限値は文書化されていないが、Databricks UI / API は実質的に
# 100 文字程度を上限にしている。空白を含む名前は OK だが、
# ワークショップでは扱いやすさのため英数字 + アンダースコア + ハイフンに制限。
SQL_WAREHOUSE_NAME_MAX_LENGTH = 100


def validate_sql_warehouse_name(name: str) -> tuple[bool, str]:
    if not name:
        return False, t("ウェアハウス名を入力してください", "Warehouse name is required")
    if len(name) > SQL_WAREHOUSE_NAME_MAX_LENGTH:
        return False, t(
            f"ウェアハウス名は {SQL_WAREHOUSE_NAME_MAX_LENGTH} 文字以内にしてください（現在 {len(name)} 文字）",
            f"Warehouse name must be ≤ {SQL_WAREHOUSE_NAME_MAX_LENGTH} chars (currently {len(name)})",
        )
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]*$", name):
        return False, t(
            "ウェアハウス名は英数字で始まり、英数字・アンダースコア・ハイフンのみ使用できます",
            "Warehouse name must start with alphanumeric and contain only alphanumeric/underscore/hyphen",
        )
    return True, ""


# ── Vector Search Endpoint 名 ──
# 公式に厳密な上限値は文書化されていないが、Vector Search Index 名と同様に
# 英数字 + アンダースコアのパターンが推奨される。長さは 100 文字を上限とする。
VS_ENDPOINT_NAME_MAX_LENGTH = 100


def validate_vs_endpoint_name(name: str) -> tuple[bool, str]:
    if not name:
        return False, t("エンドポイント名を入力してください", "Endpoint name is required")
    if len(name) > VS_ENDPOINT_NAME_MAX_LENGTH:
        return False, t(
            f"エンドポイント名は {VS_ENDPOINT_NAME_MAX_LENGTH} 文字以内にしてください（現在 {len(name)} 文字）",
            f"Endpoint name must be ≤ {VS_ENDPOINT_NAME_MAX_LENGTH} chars (currently {len(name)})",
        )
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]*$", name):
        return False, t(
            "エンドポイント名は英数字で始まり、英数字・アンダースコア・ハイフンのみ使用できます",
            "Endpoint name must start with alphanumeric and contain only alphanumeric/underscore/hyphen",
        )
    return True, ""


# ── デフォルト値生成ヘルパー ──
# ユーザーが「次へ」ボタンだけで進められるように、各新規リソースのデフォルト名を
# ユーザーIDベースで自動生成する。Catalog/Schema は階層構造で一意性が確保されるため
# 日付は付けない。Warehouse / VS endpoint / Lakebase / App は workspace-level の
# フラットな名前空間なので {user}-{MMDD} で一意化する。

def sanitize_uc_name_part(value: str) -> str:
    """email / username を UC 識別子（catalog/schema 名）に正規化する。
    英数字 + アンダースコアのみ、英字/アンダースコア始まり。

    例:
        'hiroshi.ouchiyama@databricks.com' -> 'hiroshi_ouchiyama'
        'Tanaka.Taro@example.com'          -> 'tanaka_taro'
    """
    s = value.split("@", 1)[0].lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if s and s[0].isdigit():
        s = "u_" + s  # 英字始まりにする
    return s


def compute_default_catalog_name(username: str) -> str:
    """`fm_handson_{user}` 形式の UC 識別子。フレッシュマートハンズオンであることが
    名前から分かるようにすることで、ワークショップ後のクリーンアップを容易にする。
    """
    base = "fm_handson_"
    user_part = sanitize_uc_name_part(username) or "user"
    budget = UC_NAME_MAX_LENGTH - len(base)
    if len(user_part) > budget:
        user_part = user_part[:budget].rstrip("_")
    return f"{base}{user_part}"


def compute_default_schema_name(username: str | None = None, today: str | None = None) -> str:
    """`ai_assistant_{user}` 形式。同一カタログを複数ユーザーで共有する場合の
    名前衝突を避けるため、ユーザーIDを suffix として付ける。日付は付けない
    （同じユーザーが再実行しても同じスキーマを再利用したいため）。
    username 未指定なら `ai_assistant`。
    """
    base = "ai_assistant"
    if not username:
        return base
    user_part = sanitize_uc_name_part(username)
    if not user_part:
        return base
    base_with_sep = f"{base}_"
    budget = UC_NAME_MAX_LENGTH - len(base_with_sep)
    if len(user_part) > budget:
        user_part = user_part[:budget].rstrip("_")
    return f"{base_with_sep}{user_part}"


def compute_default_warehouse_name(username: str, today: str | None = None) -> str:
    """`fm-wh-{user}-{MMDD}` 形式。"""
    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")
    mmdd = today.replace("-", "")[4:8]
    user_part = sanitize_app_name_part(username) or "user"
    suffix = f"-{mmdd}"
    base = "fm-wh-"
    budget = SQL_WAREHOUSE_NAME_MAX_LENGTH - len(base) - len(suffix)
    if len(user_part) > budget:
        user_part = user_part[:budget].rstrip("-")
    return f"{base}{user_part}{suffix}"


def compute_default_vs_endpoint_name(username: str, today: str | None = None) -> str:
    """`fm-vs-{user}-{MMDD}` 形式。"""
    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")
    mmdd = today.replace("-", "")[4:8]
    user_part = sanitize_app_name_part(username) or "user"
    suffix = f"-{mmdd}"
    base = "fm-vs-"
    budget = VS_ENDPOINT_NAME_MAX_LENGTH - len(base) - len(suffix)
    if len(user_part) > budget:
        user_part = user_part[:budget].rstrip("-")
    return f"{base}{user_part}{suffix}"


def update_databricks_yml_app_name(app_name: str) -> None:
    """databricks.yml の resources.apps.*.name を更新（dev/prod 両方）。

    対象は `freshmart-agent...` で始まる app 名のみ（quote 有無どちらも）。
    他のリソースの name キー（例: `name: "experiment"`）は変更しない。
    """
    yml_path = Path("databricks.yml")
    if not yml_path.exists():
        return

    content = yml_path.read_text()
    # 旧 (freshmart-agent...) と新 (fm-agent...) 両方のパターンを置換対象にする。
    # quote ありバージョン
    new_content = re.sub(
        r'(\bname:\s*)"(?:freshmart-agent|fm-agent)[A-Za-z0-9._-]*"',
        f'\\1"{app_name}"',
        content,
    )
    # quote なしバージョン（行末まで）
    new_content = re.sub(
        r'(\bname:\s*)(?:freshmart-agent|fm-agent)[A-Za-z0-9._-]*(\s*$)',
        f'\\1{app_name}\\2',
        new_content,
        flags=re.MULTILINE,
    )
    yml_path.write_text(new_content)
    print_success(t(f"databricks.yml を App 名で更新しました: {app_name}",
                     f"Updated databricks.yml with app name: {app_name}"))


def select_app_name_interactive(
    username: str, default: str | None = None
) -> str:
    """CLI: app 名を対話的に選択。"""
    if default is None:
        default = compute_default_app_name(username)

    print(t(f"\n  Databricks App 名（デフォルト: {default}）",
             f"\n  Databricks App name (default: {default})"))
    print(t("  制約: 小文字英数字とハイフン、英字で始まり英数で終わる、30文字以内",
             "  Constraints: lowercase alphanumeric+hyphen, start with letter, end with alphanumeric, ≤30 chars"))
    while True:
        s = input(t(f"  App 名を入力 [Enter で {default}]: ",
                     f"  Enter app name [Enter for {default}]: ")).strip()
        chosen = s or default
        if is_valid_app_name(chosen):
            return chosen
        print_error(t(f"無効な App 名: {chosen}。制約を満たしていません。",
                       f"Invalid app name: {chosen}. Does not meet constraints."))


# ── REST API helpers ─────────────────────────────────────────────────


def get_auth_token(profile_name: str) -> str:
    """Get bearer token from Databricks CLI."""
    result = run_command(
        ["databricks", "auth", "token", "-p", profile_name, "-o", "json"],
        check=True,
    )
    return json.loads(result.stdout)["access_token"]


def run_sql_statement(
    statement: str, token: str, host: str, warehouse_id: str, silent: bool = False
) -> dict:
    """Execute SQL via REST API.

    silent=True: suppress error logging. Use this when a SQL failure is an
    expected/intentional probe (e.g., DESCRIBE TABLE to test existence).
    """
    import urllib.request
    import urllib.error
    payload = json.dumps({
        "warehouse_id": warehouse_id,
        "statement": statement,
        "wait_timeout": "50s",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{host}/api/2.0/sql/statements",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        state = data.get("status", {}).get("state", "UNKNOWN")
        if state == "FAILED" and not silent:
            err = data.get("status", {}).get("error", {}).get("message", "Unknown error")
            print_error(f"SQL failed: {err}")
        return data
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        if not silent:
            print_error(f"SQL execution error: HTTP {e.code}: {body[:300]}")
        return {"status": {"state": "FAILED"}}
    except Exception as e:
        if not silent:
            print_error(f"SQL execution error: {e}")
        return {"status": {"state": "FAILED"}}


def api_get(path: str, token: str, host: str) -> dict:
    """GET request to Databricks REST API."""
    import urllib.request
    req = urllib.request.Request(
        f"{host}{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def api_post(path: str, token: str, host: str, body: dict) -> dict:
    """POST request to Databricks REST API."""
    import urllib.request
    import urllib.error
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{host}{path}",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8")
        return {"error": f"HTTP {e.code}: {body_text[:500]}"}
    except Exception as e:
        return {"error": str(e)}


# ── Trace setup ──────────────────────────────────────────────────────


def run_trace_setup_on_databricks(
    profile_name: str,
    username: str,
    catalog: str,
    schema: str,
    warehouse_id: str,
    experiment_id: str,
) -> bool:
    """Run set_experiment_trace_location on Databricks via one-time serverless job.

    Uploads a temporary notebook, submits a serverless run, waits for completion,
    and cleans up. Returns True on success.
    """
    import base64
    import time

    token = get_auth_token(profile_name)
    host = read_env_file().get("DATABRICKS_HOST", "")
    if not host:
        result = run_command(
            ["databricks", "auth", "env", "-p", profile_name, "-o", "json"],
            check=False,
        )
        if result.returncode == 0:
            host = json.loads(result.stdout).get("DATABRICKS_HOST", "")
    host = host.rstrip("/")
    if not host:
        return False

    # 1. Generate notebook content
    # UCSchemaLocation は廃止 → UnityCatalog に移行
    # table_prefix に "mlflow_experiment_trace" を指定することで、
    # 従来の UCSchemaLocation が作成していたテーブル名と互換性を保つ：
    #   mlflow_experiment_trace_otel_spans
    #   mlflow_experiment_trace_otel_logs
    # これにより MLflow ランタイムがこれらのテーブルに書き込める。
    notebook_content = f"""# Databricks notebook source
# MAGIC %pip install --upgrade mlflow>=3.10.0

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import os
os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = "{warehouse_id}"

import mlflow
mlflow.set_tracking_uri("databricks")

# 新旧 API 両対応: 新しい UnityCatalog を試し、なければ UCSchemaLocation にフォールバック
try:
    from mlflow.entities.trace_location import UnityCatalog
    experiment = mlflow.set_experiment(experiment_id="{experiment_id}")
    exp_name = experiment.name
    mlflow.set_experiment(
        experiment_name=exp_name,
        trace_location=UnityCatalog(
            catalog_name="{catalog}",
            schema_name="{schema}",
            table_prefix="mlflow_experiment_trace",
        ),
    )
    print("Trace location set successfully (UnityCatalog API).")
except ImportError:
    # 古い MLflow: UCSchemaLocation フォールバック
    from mlflow.entities import UCSchemaLocation
    mlflow.tracing.set_experiment_trace_location(
        location=UCSchemaLocation(catalog_name="{catalog}", schema_name="{schema}"),
        experiment_id="{experiment_id}",
    )
    print("Trace location set successfully (legacy UCSchemaLocation API).")
"""

    # 2. Upload temporary notebook
    notebook_path = f"/Workspace/Users/{username}/.tmp_trace_setup_{int(time.time())}"
    encoded = base64.b64encode(notebook_content.encode("utf-8")).decode("utf-8")
    upload_result = api_post("/api/2.0/workspace/import", token, host, {
        "path": notebook_path,
        "content": encoded,
        "format": "SOURCE",
        "language": "PYTHON",
        "overwrite": True,
    })
    if "error" in upload_result:
        print_error(t(f"ノートブックのアップロードに失敗: {upload_result['error'][:200]}",
                       f"Failed to upload notebook: {upload_result['error'][:200]}"))
        return False

    # 3. Submit one-time serverless run
    # Serverless 環境 client version の選択:
    #   - "1" (2024-03) は Free Edition 等の新しいワークスペースで未サポート
    #     ("Workspace doesn't support Client-1 channel for REPL" エラー)
    #   - "2" (2024-11) は広く互換性があり、3 年サポート (2027 年まで)
    submit_result = api_post("/api/2.0/jobs/runs/submit", token, host, {
        "run_name": "quickstart_trace_setup",
        "tasks": [{
            "task_key": "trace_setup",
            "notebook_task": {"notebook_path": notebook_path},
            "environment_key": "default",
        }],
        "environments": [{
            "environment_key": "default",
            "spec": {
                "client": "2",
                "dependencies": ["mlflow"],
            },
        }],
    })
    if "error" in submit_result:
        print_error(t(f"ジョブの送信に失敗: {submit_result['error'][:200]}",
                       f"Failed to submit run: {submit_result['error'][:200]}"))
        # Clean up notebook
        api_post("/api/2.0/workspace/delete", token, host, {"path": notebook_path})
        return False

    run_id = submit_result.get("run_id")
    if not run_id:
        print_error(t("run_id が取得できませんでした", "Could not get run_id"))
        api_post("/api/2.0/workspace/delete", token, host, {"path": notebook_path})
        return False

    # 4. Poll for completion
    print(t("  サーバーレス環境でトレーステーブルを作成中...",
             "  Creating trace tables on serverless..."), end="", flush=True)
    max_wait = 300  # 5 minutes
    start = time.time()
    final_state = "UNKNOWN"
    run_data = {}
    while time.time() - start < max_wait:
        import urllib.request
        req = urllib.request.Request(
            f"{host}/api/2.0/jobs/runs/get?run_id={run_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                run_data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            time.sleep(5)
            continue

        state = run_data.get("state", {})
        life_cycle = state.get("life_cycle_state", "")
        result_state = state.get("result_state", "")

        if life_cycle in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
            final_state = result_state or life_cycle
            break

        print(".", end="", flush=True)
        time.sleep(10)

    print()  # newline after dots

    # 5. Clean up temporary notebook
    api_post("/api/2.0/workspace/delete", token, host, {"path": notebook_path})

    if final_state == "SUCCESS":
        return True
    else:
        state_msg = run_data.get("state", {}).get("state_message", "")
        # Pull task-level error from run output for a more informative message
        task_error = ""
        try:
            tasks = run_data.get("tasks", [])
            if tasks:
                task_run_id = tasks[0].get("run_id")
                if task_run_id:
                    out = api_get(
                        f"/api/2.0/jobs/runs/get-output?run_id={task_run_id}", token, host
                    )
                    task_error = (out.get("error") or "") if isinstance(out, dict) else ""
        except Exception:
            pass
        combined = task_error or state_msg

        # Recognise the "default storage catalog" limitation (Free Edition / shared
        # default storage) and surface a specific, actionable message.
        if (
            "default storage" in combined.lower()
            or "Unsupported table kind" in combined
            or "tables created in default storage" in combined.lower()
        ):
            print_error(t(
                "トレーステーブルの自動作成に失敗しました。\n"
                "  原因: このカタログのストレージはワークスペース既定の共有ストレージで、\n"
                "        MLflow トレースの Delta Table 出力先としてサポートされていません\n"
                "        （Databricks 側の制約。Free Edition および外部ロケーション未設定の\n"
                "         ワークスペースで発生します）。\n"
                "  対処: 1) 外部ロケーションが設定されたカタログを使う\n"
                "        2) もしくはトレース送信先を MLflow Experiment（既定）にする",
                "Trace table auto-creation failed.\n"
                "  Reason: This catalog uses workspace default storage, which is\n"
                "          not supported as MLflow trace Delta Table destination\n"
                "          (Databricks platform constraint; affects Free Edition\n"
                "          and workspaces without external locations configured).\n"
                "  Fix:    1) Use a catalog backed by an external location, or\n"
                "          2) Set trace destination to MLflow Experiment (default)",
            ))
        else:
            print_error(t(
                f"トレーステーブル自動作成に失敗 (state={final_state}): {combined[:300]}",
                f"Trace table auto-creation failed (state={final_state}): {combined[:300]}"
            ))
        return False


# ── Interactive selectors ────────────────────────────────────────────


def select_vs_endpoint_interactive(token: str, host: str, username: str = "") -> str:
    """List Vector Search endpoints, or offer to create a new one.

    Args:
        username: Databricks email or username; used to compute the default name
            for newly-created endpoints (`fm-vs-{user}-{MMDD}`).

    Returns the endpoint name (existing or newly created).
    """
    print_step(t("Vector Search エンドポイントの選択...", "Selecting Vector Search endpoint..."))
    ep_data = api_get("/api/2.0/vector-search/endpoints", token, host)
    endpoints = ep_data.get("endpoints", []) if isinstance(ep_data, dict) else []

    # Sort: ONLINE first, then by name
    state_order = {"ONLINE": 0, "PROVISIONING": 1}
    endpoints.sort(key=lambda e: (state_order.get(e.get("endpoint_status", {}).get("state", ""), 9),
                                   e.get("name", "")))

    print()
    print(t("  オプション:", "  Options:"))
    print(t("    [N] 新規作成（タイプ STANDARD。作成完了まで 10〜15 分かかります）",
            "    [N] Create new (type STANDARD. Provisioning takes 10-15 min)"))
    if endpoints:
        print(t("    既存のエンドポイントから番号で選択:",
                "    Or pick an existing endpoint by number:"))
        for i, ep in enumerate(endpoints, 1):
            name = ep.get("name", "?")
            state = ep.get("endpoint_status", {}).get("state", "UNKNOWN")
            marker = " [ONLINE]" if state == "ONLINE" else f" [{state}]"
            print(f"      {i}. {name}{marker}")
    else:
        print(t("    （既存のエンドポイントは見つかりませんでした）",
                "    (No existing endpoints found)"))

    default_choice = "1" if endpoints else "N"
    while True:
        choice = input(t(f"\n  選択 [{default_choice}]: ",
                          f"\n  Selection [{default_choice}]: ")).strip() or default_choice
        if choice.lower() == "n":
            default_ep = compute_default_vs_endpoint_name(username)
            while True:
                new_name = input(t(f"    新規エンドポイント名を入力 [{default_ep}]: ",
                                    f"    Enter new endpoint name [{default_ep}]: ")).strip() \
                    or default_ep
                ok, msg = validate_vs_endpoint_name(new_name)
                if ok:
                    break
                print_error(msg)
            print(t(f"\n  ⏳ '{new_name}' を作成中... 10〜15 分かかるためコーヒーブレイクを推奨します。",
                    f"\n  ⏳ Creating '{new_name}'... This takes 10-15 min — coffee break time."))
            result = create_vs_endpoint_new(token, host, new_name)
            if "error" in result:
                print_error(t(f"作成失敗: {result['error'][:200]}",
                               f"Creation failed: {result['error'][:200]}"))
                continue
            print(t("  Provisioning 中... ONLINE になるまで待機します。",
                    "  Provisioning... waiting until ONLINE."))
            ok = wait_for_vs_endpoint_ready(token, host, new_name, timeout_sec=1500)
            if ok:
                print_success(t(f"VS エンドポイント作成完了: {new_name}",
                                 f"VS endpoint created: {new_name}"))
            else:
                print(t(f"  ⚠ タイムアウト（後続処理で再確認されます）: {new_name}",
                         f"  ⚠ Timeout (will be re-checked later): {new_name}"))
            return new_name
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(endpoints):
                selected = endpoints[idx]
                name = selected["name"]
                state = selected.get("endpoint_status", {}).get("state", "UNKNOWN")
                print_success(f"VS endpoint: {name} ({state})")
                return name
        except ValueError:
            pass
        print(t("  無効な選択です。", "  Invalid selection."))


def select_warehouse_interactive(
    profile_name: str, token: str = "", host: str = "", user: str = ""
) -> tuple[str, str]:
    """List warehouses with CAN_USE+ permission, or offer to create a new one.

    Returns (warehouse_id, warehouse_name).
    """
    print_step(t("SQL ウェアハウスの選択...", "Selecting SQL warehouse..."))
    print(t("  使用権限のあるウェアハウスを検索中（少々お待ちください）...",
            "  Searching for warehouses you can use (this may take a moment)..."))

    if token and host and user:
        warehouses = filter_usable_warehouses(profile_name, token, host, user)
    else:
        # Fallback: list all visible warehouses
        result = run_command(
            ["databricks", "warehouses", "list", "-p", profile_name, "-o", "json"],
            check=False,
        )
        warehouses = (
            json.loads(result.stdout)
            if result.returncode == 0 and result.stdout.strip() else []
        )
        warehouses.sort(
            key=lambda w: (0 if w.get("state") == "RUNNING" else 1, w.get("name", ""))
        )

    print()
    print(t("  オプション:", "  Options:"))
    print(t("    [N] 新規作成（Serverless Pro X-Small、自動停止 60 分。作成 1〜2 分）",
            "    [N] Create new (Serverless Pro X-Small, auto-stop 60min. Takes 1-2 min)"))
    if warehouses:
        print(t("    既存のウェアハウスから番号で選択（使用権限あり）:",
                "    Or pick an existing warehouse by number (you have CAN_USE+):"))
        for i, w in enumerate(warehouses, 1):
            state = w.get("state", "UNKNOWN")
            name = w.get("name", "?")
            wid = w.get("id", "?")
            perm = w.get("_user_permission", "")
            marker = f" [{state}]" + (f" [{perm}]" if perm else "")
            print(f"      {i}. {name} ({wid}){marker}")
    else:
        print(t("    （使用権限のある既存ウェアハウスは見つかりませんでした）",
                "    (No existing warehouses found where you have CAN_USE permission)"))

    default_choice = "1" if warehouses else "N"
    while True:
        choice = input(t(f"\n  選択 [{default_choice}]: ",
                          f"\n  Selection [{default_choice}]: ")).strip() or default_choice
        if choice.lower() == "n":
            default_wh = compute_default_warehouse_name(user)
            while True:
                new_name = input(t(f"    新規ウェアハウス名を入力 [{default_wh}]: ",
                                    f"    Enter new warehouse name [{default_wh}]: ")).strip() \
                    or default_wh
                ok, msg = validate_sql_warehouse_name(new_name)
                if ok:
                    break
                print_error(msg)
            print(t(f"\n  ウェアハウス '{new_name}' を作成中...",
                    f"\n  Creating warehouse '{new_name}'..."))
            if not token or not host:
                print_error(t("token / host が未設定のため作成できません。",
                               "Cannot create: token / host not set."))
                continue
            result = create_sql_warehouse(token, host, new_name)
            if "error" in result:
                print_error(t(f"作成失敗: {result['error'][:200]}",
                               f"Creation failed: {result['error'][:200]}"))
                continue
            wid = result.get("id", "")
            print_success(t(f"ウェアハウス作成完了: {new_name} ({wid})",
                             f"Warehouse created: {new_name} ({wid})"))
            print(t("  起動を待機中（最大 5 分）...", "  Waiting for startup (up to 5 min)..."))
            wait_for_warehouse_ready(profile_name, wid, timeout_sec=300)
            return wid, new_name
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(warehouses):
                selected = warehouses[idx]
                wid = selected["id"]
                wname = selected.get("name", "?")
                print_success(f"Warehouse: {wname} ({wid})")
                return wid, wname
        except ValueError:
            pass
        print(t("  無効な選択です。", "  Invalid selection."))


# ── Data & resource creation ─────────────────────────────────────────


def create_catalog_schema(token: str, host: str, warehouse_id: str, catalog: str, schema: str):
    """Create catalog and schema via SQL API."""
    print_step(t("カタログ・スキーマの作成...", "Creating catalog and schema..."))

    # バッククォートで囲むことで特殊文字を含むカタログ名にも対応
    data = run_sql_statement(f"CREATE CATALOG IF NOT EXISTS `{catalog}`", token, host, warehouse_id)
    state = data.get("status", {}).get("state", "FAILED")
    if state in ("SUCCEEDED", "CLOSED"):
        print_success(t(f"カタログ: {catalog}", f"Catalog: {catalog}"))
    else:
        # 権限不足の場合は既存カタログを使うので警告のみ
        print(t(f"  カタログ作成: {state}（既に存在するか、権限がない場合はそのまま続行します）",
                 f"  Catalog creation: {state} (continuing if it already exists or insufficient permissions)"))

    data = run_sql_statement(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}`", token, host, warehouse_id)
    state = data.get("status", {}).get("state", "FAILED")
    if state in ("SUCCEEDED", "CLOSED"):
        print_success(t(f"スキーマ: {catalog}.{schema}", f"Schema: {catalog}.{schema}"))
    else:
        print(t(f"  スキーマ作成: {state}（既に存在するか、権限がない場合はそのまま続行します）",
                 f"  Schema creation: {state} (continuing if it already exists or insufficient permissions)"))

    # スキーマの存在を確認
    verify = run_sql_statement(f"DESCRIBE SCHEMA `{catalog}`.`{schema}`", token, host, warehouse_id)
    verify_state = verify.get("status", {}).get("state", "FAILED")
    if verify_state in ("SUCCEEDED", "CLOSED"):
        print_success(t(f"スキーマ確認OK: {catalog}.{schema}",
                         f"Schema verified: {catalog}.{schema}"))
    else:
        print_error(t(f"スキーマ {catalog}.{schema} にアクセスできません。カタログ/スキーマが存在し、権限があることを確認してください。",
                       f"Cannot access schema {catalog}.{schema}. Please verify the catalog/schema exists and you have permissions."))
        sys.exit(1)


def check_tables_exist(token: str, host: str, warehouse_id: str, catalog: str, schema: str) -> bool:
    """全6テーブルと policy_docs_chunked が存在するかチェック。

    存在しないのは想定内なので silent=True で SQL エラーログを抑制する。
    """
    required_tables = ["customers", "products", "stores", "transactions", "transaction_items", "payment_history"]
    for table in required_tables:
        data = run_sql_statement(
            f"DESCRIBE TABLE `{catalog}`.`{schema}`.`{table}`",
            token, host, warehouse_id, silent=True,
        )
        if data.get("status", {}).get("state") not in ("SUCCEEDED", "CLOSED"):
            return False
    return True


def check_chunked_table_exists(token: str, host: str, warehouse_id: str, catalog: str, schema: str) -> bool:
    """policy_docs_chunked テーブルが存在するかチェック。

    存在しないのは想定内なので silent=True でエラーログを抑制する。
    """
    data = run_sql_statement(
        f"DESCRIBE TABLE `{catalog}`.`{schema}`.policy_docs_chunked",
        token, host, warehouse_id, silent=True,
    )
    return data.get("status", {}).get("state") in ("SUCCEEDED", "CLOSED")


def generate_data(profile_name: str, warehouse_id: str, catalog: str, schema: str, token: str = "", host: str = ""):
    """Generate structured data and chunked policy docs."""
    # scripts/quickstart_core.py から見て、data/ はリポ root にある
    data_dir = Path(__file__).parent.parent / "data"
    env = os.environ.copy()
    env["CATALOG"] = catalog
    env["SCHEMA"] = schema

    # 構造化データのスキップチェック
    if token and host:
        print_step(t("構造化データの確認中...", "Checking structured data..."))
        if check_tables_exist(token, host, warehouse_id, catalog, schema):
            print_success(t("構造化データは既に存在します（スキップ）",
                             "Structured data already exists (skipping)"))
            # チャンクテーブルも確認
            if check_chunked_table_exists(token, host, warehouse_id, catalog, schema):
                print_success(t("ポリシー文書チャンクも既に存在します（スキップ）",
                                 "Policy document chunks already exist (skipping)"))
                return
            else:
                # チャンクだけ生成
                print_step(t("ポリシー文書のチャンク生成...",
                              "Generating policy document chunks..."))
                result = subprocess.run(
                    [sys.executable, str(data_dir / "execute_chunking.py"),
                     "--profile", profile_name, "--warehouse-id", warehouse_id],
                    capture_output=True, text=True, env=env,
                )
                if result.returncode == 0:
                    print_success(t("ポリシー文書チャンク生成完了",
                                     "Policy document chunk generation complete"))
                else:
                    err_detail = result.stderr[-300:] if result.stderr else ""
                    print_error(t(f"チャンク生成に失敗: {err_detail}",
                                   f"Chunk generation failed: {err_detail}"))
                    raise RuntimeError(f"Chunk generation failed: {err_detail}")
                return

    # Structured data
    print_step(t("構造化データの生成（6テーブル）...",
                  "Generating structured data (6 tables)..."))
    print(t("  所要時間: 約5〜10分", "  Estimated time: 5-10 minutes"))
    result = subprocess.run(
        [sys.executable, str(data_dir / "execute_sql.py"),
         "--profile", profile_name, "--warehouse-id", warehouse_id],
        capture_output=True, text=True, env=env,
    )
    if result.returncode == 0:
        print_success(t("構造化データ生成完了",
                         "Structured data generation complete"))
    else:
        err_detail = result.stderr[-300:] if result.stderr else ""
        print_error(t(f"構造化データ生成に失敗: {err_detail}",
                       f"Structured data generation failed: {err_detail}"))
        raise RuntimeError(f"Structured data generation failed: {err_detail}")

    # Chunked policy docs
    print_step(t("ポリシー文書のチャンク生成...",
                  "Generating policy document chunks..."))
    result = subprocess.run(
        [sys.executable, str(data_dir / "execute_chunking.py"),
         "--profile", profile_name, "--warehouse-id", warehouse_id],
        capture_output=True, text=True, env=env,
    )
    if result.returncode == 0:
        print_success(t("ポリシー文書チャンク生成完了",
                         "Policy document chunk generation complete"))
    else:
        err_detail = result.stderr[-300:] if result.stderr else ""
        print_error(t(f"ポリシー文書チャンク生成に失敗: {err_detail}",
                       f"Policy document chunk generation failed: {err_detail}"))
        raise RuntimeError(f"Policy document chunk generation failed: {err_detail}")


def enable_cdf(token: str, host: str, warehouse_id: str, catalog: str, schema: str):
    """Enable Change Data Feed on policy_docs_chunked table."""
    print_step(t("Change Data Feed の有効化...",
                  "Enabling Change Data Feed..."))
    stmt = f"ALTER TABLE `{catalog}`.`{schema}`.policy_docs_chunked SET TBLPROPERTIES (delta.enableChangeDataFeed = true)"
    data = run_sql_statement(stmt, token, host, warehouse_id)
    state = data.get("status", {}).get("state", "FAILED")
    if state in ("SUCCEEDED", "CLOSED"):
        print_success(t("CDF 有効化完了", "CDF enabled"))
    else:
        print(t(f"  CDF: {state} (既に有効な場合はOK)",
                 f"  CDF: {state} (OK if already enabled)"))


def create_vector_search_index(token: str, host: str, catalog: str, schema: str, vs_endpoint: str) -> str:
    """Create Vector Search index and wait for READY.

    SDK の create_delta_sync_index_and_wait を使用：エンドポイントの
    ONLINE 詐欺（state は ONLINE だがクエリ可能になるまで数分かかる）を
    SDK 側で吸収してくれる。
    """
    from databricks.vector_search.client import VectorSearchClient

    index_name = f"{catalog}.{schema}.policy_docs_index"
    print_step(t(f"Vector Search インデックスの作成 ({index_name})...",
                  f"Creating Vector Search index ({index_name})..."))

    # 既存を再利用（READY ならスキップ）
    existing = api_get(f"/api/2.0/vector-search/indexes/{index_name}", token, host)
    if "error" not in existing and existing.get("status", {}).get("ready") is True:
        print_success(t(f"インデックス {index_name} は既に READY です（スキップ）",
                         f"Index {index_name} is already READY (skipping)"))
        return index_name

    vsc = VectorSearchClient(
        workspace_url=host,
        personal_access_token=token,
        disable_notice=True,
    )
    print(t("  作成 + READY 待ち（最大 60 分、SDK が状態遷移を内部追跡）...",
             "  Creating + waiting for READY (up to 60 min, SDK handles state)..."))
    try:
        vsc.create_delta_sync_index_and_wait(
            endpoint_name=vs_endpoint,
            index_name=index_name,
            primary_key="chunk_id",
            source_table_name=f"{catalog}.{schema}.policy_docs_chunked",
            pipeline_type="TRIGGERED",
            embedding_source_column="content",
            embedding_model_endpoint_name="databricks-qwen3-embedding-0-6b",
            verbose=True,
            timeout=timedelta(minutes=60),
        )
    except Exception as e:
        # ALREADY_EXISTS は再利用可能なので最終ステータスだけ確認
        msg = str(e)
        if "ALREADY_EXISTS" in msg or "already exists" in msg.lower():
            print(t("  インデックスは既に存在。ステータス確認中...",
                     "  Index already exists. Checking status..."))
        else:
            print_error(t(f"インデックス作成失敗: {msg[:200]}",
                           f"Index creation failed: {msg[:200]}"))
            raise RuntimeError(f"VS Index creation failed: {msg[:300]}") from e

    # SDK が wait を返した時点で READY だが、最終確認
    status = api_get(f"/api/2.0/vector-search/indexes/{index_name}", token, host)
    if status.get("status", {}).get("ready") is True:
        print_success(t(f"インデックス READY: {index_name}",
                         f"Index READY: {index_name}"))
    else:
        print(t("  ⚠ wait 完了後も ready=False。Databricks UI で確認してください。",
                 "  Warning: wait returned but ready=False. Please check the Databricks UI."))
    return index_name


# ── Genie Space ──────────────────────────────────────────────────────


def _get_table_columns(token: str, host: str, warehouse_id: str, full_table_name: str) -> list[dict]:
    """テーブルのカラム情報を DESCRIBE TABLE で取得。"""
    data = run_sql_statement(f"DESCRIBE TABLE `{full_table_name.replace('.', '`.`')}`", token, host, warehouse_id)
    if data.get("status", {}).get("state") not in ("SUCCEEDED", "CLOSED"):
        return []
    columns = []
    for row in data.get("result", {}).get("data_array", []):
        if row and row[0] and not row[0].startswith("#"):
            columns.append({"name": row[0], "type": row[1] if len(row) > 1 else "string"})
    return columns


def _build_serialized_space(catalog: str, schema: str, tables: list[str]) -> str:
    """serialized_space の JSON 文字列を生成。

    Genie API は version 2 (integer) を要求する。version 1 を送ると
    "The export format has changed since this export was taken" の 409 が返る。
    テーブルは identifier でアルファベット順ソート必須。
    """
    data_sources_tables = [
        {"identifier": f"{catalog}.{schema}.{t}"}
        for t in sorted(tables)
    ]

    space_config = {
        "version": 2,
        "config": {},
        "data_sources": {"tables": data_sources_tables},
    }
    return json.dumps(space_config, ensure_ascii=False)


def create_genie_space(token: str, host: str, warehouse_id: str, catalog: str, schema: str) -> str:
    """Genie Space を新規作成または既存の ID を入力。"""
    print_step(t("Genie Space の設定", "Genie Space setup"))
    print()
    print(t("  1) 新規作成（API で自動作成）", "  1) Create new (auto-create via API)"))
    print(t("  2) 既存の Genie Space ID を入力", "  2) Enter existing Genie Space ID"))

    while True:
        choice = input(t("\n  選択 [1]: ", "\n  Select [1]: ")).strip() or "1"
        if choice in ("1", "2"):
            break
        print(t("  1 または 2 を入力してください。", "  Please enter 1 or 2."))

    if choice == "2":
        # 既存 ID の入力
        while True:
            space_id = input(t("  Genie Space ID を入力してください: ",
                                "  Enter Genie Space ID: ")).strip()
            if not space_id:
                print(t("  ID を入力してください。", "  Please enter an ID."))
                continue
            # 存在チェック
            result = api_get(f"/api/2.0/genie/spaces/{space_id}", token, host)
            if "error" not in result and result.get("space_id"):
                title = result.get("title", "?")
                print_success(t(f"Genie Space 確認OK: {title} ({space_id})",
                                 f"Genie Space verified: {title} ({space_id})"))
                return space_id
            else:
                print_error(t(f"Space ID '{space_id}' が見つかりません。もう一度入力してください。",
                               f"Space ID '{space_id}' not found. Please try again."))

    # 新規作成
    tables = ["customers", "products", "stores", "transactions", "transaction_items", "payment_history"]
    serialized = _build_serialized_space(catalog, schema, tables)

    print(t("  Genie Space を作成中...", "  Creating Genie Space..."))
    body = {
        "title": "フレッシュマート 小売データ",
        "description": "フレッシュマートの小売データに対する自然言語クエリ。顧客、商品、店舗、取引、支払い履歴を検索できます。",
        "warehouse_id": warehouse_id,
        "serialized_space": serialized,
    }
    result = api_post("/api/2.0/genie/spaces", token, host, body)

    space_id = result.get("space_id", "")
    if space_id:
        print_success(t(f"Genie Space 作成完了 (ID: {space_id})",
                         f"Genie Space created (ID: {space_id})"))
        return space_id

    # API 失敗時はフォールバック
    if "error" in result:
        print_error(t(f"自動作成に失敗: {result['error'][:200]}",
                       f"Auto-creation failed: {result['error'][:200]}"))
        print(t("  Databricks UI から手動で作成してください：",
                 "  Please create it manually from the Databricks UI:"))
        print(t(f"  1. {host} を開く",
                 f"  1. Open {host}"))
        print(t("  2. 左メニュー Genie > New Genie Space",
                 "  2. Left menu: Genie > New Genie Space"))
        print(t("  3. 名前: フレッシュマート 小売データ",
                 "  3. Name: FreshMart Retail Data"))
        print(t(f"  4. スキーマ {catalog}.{schema} のテーブルを全て追加",
                 f"  4. Add all tables from schema {catalog}.{schema}"))
        print(t("  5. SQL ウェアハウスを選択して Create",
                 "  5. Select SQL warehouse and click Create"))
        print(t("  6. URL から Space ID をコピー",
                 "  6. Copy the Space ID from the URL"))
        while True:
            space_id = input(t("\n  Genie Space ID を入力してください: ",
                                "\n  Enter Genie Space ID: ")).strip()
            if space_id:
                return space_id
            print(t("  ID を入力してください。", "  Please enter an ID."))

    return space_id


# ── Dependencies ─────────────────────────────────────────────────────


def install_dependencies():
    """Install Python and Node.js dependencies."""
    print_step(t("依存関係のインストール...", "Installing dependencies..."))

    # Python
    result = subprocess.run(
        ["uv", "sync"], capture_output=True, text=True,
    )
    if result.returncode == 0:
        print_success(t("Python 依存関係 (uv sync)", "Python dependencies (uv sync)"))
    else:
        print_error(t(f"uv sync 失敗: {result.stderr[-200:]}",
                       f"uv sync failed: {result.stderr[-200:]}"))

    # Node.js
    frontend_dir = Path("e2e-chatbot-app-next")
    if frontend_dir.exists():
        result = subprocess.run(
            ["npm", "install"], capture_output=True, text=True, cwd=frontend_dir,
        )
        if result.returncode == 0:
            print_success(t("Node.js 依存関係 (npm install)", "Node.js dependencies (npm install)"))
        else:
            print(t("  ⚠ npm install に失敗。手動で実行してください: cd e2e-chatbot-app-next && npm install",
                     "  Warning: npm install failed. Please run manually: cd e2e-chatbot-app-next && npm install"))
    else:
        print(t("  ⚠ e2e-chatbot-app-next/ が見つかりません（フロントエンドなし）",
                 "  Warning: e2e-chatbot-app-next/ not found (no frontend)"))


def init_lakebase_tables() -> bool:
    """Briefly start the agent server to trigger Lakebase table creation.

    The LangGraph checkpointer and DatabricksStore run auto-migrations on
    startup, creating all required PostgreSQL tables. We start the server
    for a few seconds, then stop it.

    Returns True if the server started and presumably created the tables.
    """
    import time

    print_step(t("Lakebase テーブルを初期化中（サーバーを一時起動）...",
                  "Initializing Lakebase tables (briefly starting server)..."))

    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "agent_server.start_server:app",
             "--host", "127.0.0.1", "--port", "18765"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "PORT": "18765"},
        )

        # Wait for initialization (migrations run on import/startup)
        for i in range(20):
            time.sleep(1)
            if proc.poll() is not None:
                # Process exited early — check if it at least started
                break
            # Check if server is responding
            try:
                import urllib.request
                urllib.request.urlopen("http://127.0.0.1:18765/health", timeout=2)
                print_success(t("サーバー起動確認、テーブル作成済み",
                                 "Server started, tables created"))
                break
            except Exception:
                pass  # Not ready yet

        # Stop the server
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

        print_success(t("Lakebase テーブル初期化完了",
                         "Lakebase table initialization complete"))
        return True
    except Exception as e:
        print(t(f"  ⚠ テーブル初期化をスキップ: {str(e)[:150]}",
                 f"  Warning: Skipping table init: {str(e)[:150]}"))
        print(t("  アプリ初回起動後に grant-sp-permissions を再実行してください。",
                 "  Run grant-sp-permissions again after the first app startup."))
        return False


# ── Permission-aware resource filtering & creation ───────────────────


DEFAULT_LLM_MODEL_SERVICE = "system.ai.claude-sonnet-5"


def list_gateway_chat_model_services(
    token: str, host: str, catalog: str = "system", schema: str = "ai",
) -> list[str]:
    """Return chat-capable Unity AI Gateway model service names in a UC schema.

    Filters `/api/2.1/unity-catalog/model-services?catalog_name=...&schema_name=...`
    by `supported_api_types` containing `"mlflow/v1/chat/completions"`
    (excludes embeddings-only services). Returns bare names
    (e.g. `"system.ai.claude-sonnet-5"`) sorted alphabetically.
    """
    result = api_get(
        f"/api/2.1/unity-catalog/model-services?catalog_name={catalog}&schema_name={schema}",
        token, host,
    )
    services = result.get("model_services", []) if isinstance(result, dict) else []
    chat_names = []
    for ms in services:
        api_types = ms.get("supported_api_types") or []
        if "mlflow/v1/chat/completions" not in api_types:
            continue
        raw_name = ms.get("name", "")
        # "model-services/system.ai.claude-sonnet-5" -> "system.ai.claude-sonnet-5"
        bare = raw_name.removeprefix("model-services/") if raw_name.startswith("model-services/") else raw_name
        if bare:
            chat_names.append(bare)
    chat_names.sort()
    return chat_names


def select_llm_model_service_interactive(
    token: str, host: str, default: str = DEFAULT_LLM_MODEL_SERVICE,
) -> str:
    """Show Unity AI Gateway chat model services and let the user pick one.

    Default is highlighted with ★ but the user must explicitly confirm
    (no implicit fallback if the default is missing).
    """
    print_step(t("LLM モデルサービスの選択（Unity AI Gateway 経由）...",
                  "Selecting LLM model service (via Unity AI Gateway)..."))
    names = list_gateway_chat_model_services(token, host)
    if not names:
        print_error(t(
            "利用可能なチャット用モデルサービスが見つかりません。\n"
            "ワークスペースで Unity AI Gateway が有効化されているか、"
            "account admin に確認してください。",
            "No chat-capable model services available.\n"
            "Please ask your account admin to verify Unity AI Gateway is enabled.",
        ))
        manual = input(t(f"\n  モデルサービス名を手動入力 [{default}]: ",
                          f"\n  Enter model service name manually [{default}]: ")).strip()
        return manual or default

    print()
    print(t("  利用可能なチャットモデルサービス:",
            "  Available chat model services:"))
    default_idx = -1
    for i, name in enumerate(names, 1):
        marker = " ★ (推奨デフォルト)" if name == default else ""
        if name == default:
            default_idx = i
        print(f"    {i}. {name}{marker}")

    if default_idx == -1:
        print(t(f"\n  ⚠ 推奨デフォルト ({default}) はこのワークスペースにありません。",
                f"\n  ⚠ Recommended default ({default}) is not available in this workspace."))
        default_choice = "1"
    else:
        default_choice = str(default_idx)

    while True:
        choice = input(t(f"\n  番号で選択 [{default_choice}]: ",
                          f"\n  Select by number [{default_choice}]: ")).strip() or default_choice
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(names):
                selected = names[idx]
                print_success(f"LLM model service: {selected}")
                return selected
        except ValueError:
            pass
        print(t("  無効な選択です。", "  Invalid selection."))


def check_ai_gateway_available(token: str, host: str) -> bool:
    """Return True if the Unity AI Gateway URL responds (any 2xx/4xx)

    404 = feature not enabled (account admin needs to turn on the Preview).
    401/403 = auth issue.
    2xx / 4xx (other) = endpoint exists.
    """
    # A HEAD on /chat/completions should return 405 (Method Not Allowed) or
    # 4xx-family, which we still count as "endpoint exists". A plain GET on
    # the base path is safer.
    import urllib.request, urllib.error
    url = f"{host}/ai-gateway/mlflow/v1/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 500
    except urllib.error.HTTPError as e:
        # 404 = not enabled
        return e.code != 404
    except Exception:
        return False


def select_catalog_interactive(
    token: str, host: str, user: str, default: str = ""
) -> str:
    """Let the user select a catalog from those they have CREATE_SCHEMA on,
    or enter a name to create a new one."""
    print_step(t("カタログの選択...", "Selecting catalog..."))
    print(t("  書き込み権限のあるカタログを検索中（少々お待ちください）...",
            "  Searching for catalogs you can write to (this may take a moment)..."))
    writable = filter_writable_catalogs(token, host, user)
    names = [c.get("name", "") for c in writable if c.get("name")]

    print()
    print(t("  オプション:", "  Options:"))
    print(t("    [N] 新しいカタログを作成", "    [N] Create a new catalog"))
    if names:
        print(t("    既存のカタログから番号で選択（書き込み権限あり）:",
                "    Or pick an existing catalog by number (you have write access):"))
        for i, name in enumerate(names, 1):
            marker = " ★" if name == default else ""
            print(f"      {i}. {name}{marker}")
    else:
        print(t("    （書き込み権限のある既存カタログは見つかりませんでした）",
                "    (No existing catalogs found where you have write access)"))

    default_choice = (
        "N" if not names
        else (str(names.index(default) + 1) if default in names else "1")
    )
    while True:
        choice = input(t(f"\n  選択 [{default_choice}]: ",
                          f"\n  Selection [{default_choice}]: ")).strip() or default_choice
        if choice.lower() == "n":
            new_name = input(t("    新規カタログ名を入力: ",
                                "    Enter new catalog name: ")).strip()
            if new_name:
                return new_name
            print(t("    名前が必要です。", "    A name is required."))
            continue
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(names):
                return names[idx]
        except ValueError:
            pass
        print(t("  無効な選択です。", "  Invalid selection."))


def get_effective_uc_permissions(
    token: str, host: str, securable_type: str, full_name: str, principal: str = None
) -> list[str]:
    """Get effective UC permissions for a securable. Returns list of privilege names.

    securable_type: 'catalog', 'schema', 'table', 'function', etc.
    full_name: name of the securable (e.g., catalog name, or 'cat.schema')
    principal: user email or SP application ID. If None, returns all assignments.
    """
    import urllib.parse
    path = f"/api/2.1/unity-catalog/effective-permissions/{securable_type}/{full_name}"
    if principal:
        path += f"?principal={urllib.parse.quote(principal)}"
    result = api_get(path, token, host)
    if "error" in result:
        return []
    privs: list[str] = []
    for assignment in result.get("privilege_assignments", []):
        for p in assignment.get("privileges", []):
            name = p.get("privilege") if isinstance(p, dict) else p
            if name:
                privs.append(name)
    return privs


def filter_writable_catalogs(
    token: str, host: str, user: str, max_workers: int = 8
) -> list[dict]:
    """Return catalogs where the user can create a schema.

    Filters by the CREATE_SCHEMA effective permission. Catalog ownership and
    ALL_PRIVILEGES are also reflected as CREATE_SCHEMA in effective permissions.
    Permission checks are issued in parallel.
    """
    from concurrent.futures import ThreadPoolExecutor

    result = api_get("/api/2.1/unity-catalog/catalogs", token, host)
    catalogs = result.get("catalogs", []) if isinstance(result, dict) else []
    if not catalogs:
        return []

    def _check(cat: dict) -> dict | None:
        name = cat.get("name", "")
        if not name:
            return None
        privs = get_effective_uc_permissions(token, host, "catalog", name, user)
        if "CREATE_SCHEMA" in privs:
            return cat
        return None

    writable: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for r in ex.map(_check, catalogs):
            if r is not None:
                writable.append(r)
    writable.sort(key=lambda c: c.get("name", ""))
    return writable


def get_current_user_groups(token: str, host: str) -> set[str]:
    """Return the set of group display names the current user belongs to.

    Uses the SCIM Me endpoint. Returns lowercase group names.
    Returns empty set on error (caller should treat as "no groups detected").
    """
    result = api_get("/api/2.0/preview/scim/v2/Me", token, host)
    if "error" in result or not isinstance(result, dict):
        return set()
    groups: set[str] = set()
    for g in result.get("groups", []):
        display = g.get("display") or g.get("displayName") or ""
        if display:
            groups.add(display.lower())
    return groups


def get_warehouse_user_permission(
    token: str, host: str, warehouse_id: str, user: str,
    user_groups: set[str] | None = None,
) -> str | None:
    """Return the user's effective permission on a SQL warehouse, or None.

    Returns one of: "IS_OWNER", "CAN_MANAGE", "CAN_USE", "CAN_VIEW", "CAN_MONITOR".
    Returns None if the user has no permission entry — directly or via group.

    user_groups: optional pre-fetched lowercase group names. If None, only
                 direct user/SP grants are checked.
    """
    result = api_get(f"/api/2.0/permissions/warehouses/{warehouse_id}", token, host)
    if "error" in result:
        return None
    rank = {
        "IS_OWNER": 5,
        "CAN_MANAGE": 4,
        "CAN_USE": 3,
        "CAN_MONITOR": 2,
        "CAN_VIEW": 1,
    }
    best: str | None = None
    user_lc = (user or "").lower()
    user_groups = user_groups or set()
    for entry in result.get("access_control_list", []):
        # Match by direct user, service principal, or group membership
        matched = False
        if (entry.get("user_name") or "").lower() == user_lc and user_lc:
            matched = True
        elif (entry.get("service_principal_name") or "").lower() == user_lc and user_lc:
            matched = True
        elif (entry.get("group_name") or "").lower() in user_groups:
            matched = True
        if not matched:
            continue
        for p in entry.get("all_permissions", []):
            level = p.get("permission_level", "")
            if level and (best is None or rank.get(level, 0) > rank.get(best, 0)):
                best = level
    return best


def filter_usable_warehouses(
    profile_name: str, token: str, host: str, user: str, max_workers: int = 8
) -> list[dict]:
    """Return SQL warehouses on which the user has CAN_USE or higher.

    Calls `databricks warehouses list` first, then checks permissions in parallel.
    Falls back to returning all warehouses if permission API is unavailable.
    """
    from concurrent.futures import ThreadPoolExecutor

    try:
        result = run_command(
            ["databricks", "warehouses", "list", "-p", profile_name, "-o", "json"],
            check=False,
        )
        if result.returncode != 0:
            return []
        warehouses = json.loads(result.stdout) if result.stdout.strip() else []
    except Exception:
        return []

    if not warehouses:
        return []

    # Pre-fetch user's groups so we can check group-based grants too
    user_groups = get_current_user_groups(token, host)

    rank = {"IS_OWNER": 5, "CAN_MANAGE": 4, "CAN_USE": 3}

    def _check(wh: dict) -> dict | None:
        wid = wh.get("id", "")
        if not wid:
            return None
        level = get_warehouse_user_permission(
            token, host, wid, user, user_groups=user_groups,
        )
        if level and rank.get(level, 0) >= 3:  # CAN_USE or higher
            wh["_user_permission"] = level
            return wh
        return None

    usable: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for r in ex.map(_check, warehouses):
            if r is not None:
                usable.append(r)

    # Fallback: if no direct/group grant was detected on any warehouse,
    # the user likely has access via a path we can't see (workspace admin,
    # nested group, account-level group, etc.). Trust the warehouses-list
    # API (which only returns visible warehouses) and include them all
    # without a permission label.
    if not usable and warehouses:
        for wh in warehouses:
            wh["_user_permission"] = "(unverified)"
        usable = warehouses

    usable.sort(key=lambda w: (0 if w.get("state") == "RUNNING" else 1, w.get("name", "")))
    return usable


def create_sql_warehouse(
    token: str, host: str, name: str,
    cluster_size: str = "X-Small",
    warehouse_type: str = "PRO",
    enable_serverless_compute: bool = True,
    auto_stop_mins: int = 60,
) -> dict:
    """Create a new SQL warehouse via REST API（冪等化）。

    同名のウェアハウスが既に存在する場合は **作成せず既存のものを再利用** する
    （warehouse は名前の一意性制約がないため、デフォルトの API は同名複数を作って
    しまう。それを避けるため事前にリストして名前マッチがあれば再利用する）。

    Returns:
        dict with 'id' (and 'reused' bool if reused), or {'error': ...} on failure.
    """
    # 1. 既存の同名 warehouse を探す
    existing = api_get("/api/2.0/sql/warehouses", token, host)
    if isinstance(existing, dict) and "warehouses" in existing:
        for w in existing.get("warehouses", []):
            if w.get("name") == name:
                print_success(t(
                    f"  既存のウェアハウス '{name}' を再利用します（id: {w.get('id')}）",
                    f"  Reusing existing warehouse '{name}' (id: {w.get('id')})",
                ))
                return {**w, "reused": True}

    # 2. 存在しなければ新規作成
    body = {
        "name": name,
        "cluster_size": cluster_size,
        "warehouse_type": warehouse_type,
        "enable_serverless_compute": enable_serverless_compute,
        "auto_stop_mins": auto_stop_mins,
        "min_num_clusters": 1,
        "max_num_clusters": 1,
        "channel": {"name": "CHANNEL_NAME_CURRENT"},
    }
    return api_post("/api/2.0/sql/warehouses", token, host, body)


def create_vs_endpoint_new(
    token: str, host: str, name: str, endpoint_type: str = "STANDARD"
) -> dict:
    """Create a new Vector Search endpoint and wait until ONLINE（冪等化）。

    同名エンドポイントが既に存在する場合は **作成せず既存のものを再利用** する。
    新規作成は 10〜15 分かかるが、SDK の create_endpoint_and_wait は内部で
    state 遷移を追跡しつつ待機する。endpoint_status.state="ONLINE" を返した
    直後でもクエリ可能になるまで遅延がある「ONLINE 詐欺」問題は、後段の
    create_delta_sync_index_and_wait が吸収する。

    Returns:
        dict with 'name' / 'endpoint_status' (and 'reused' bool if reused).
    """
    from databricks.vector_search.client import VectorSearchClient

    # 1. 既存エンドポイントの確認
    existing = api_get(f"/api/2.0/vector-search/endpoints/{name}", token, host)
    if isinstance(existing, dict) and "error" not in existing and existing.get("name") == name:
        state = existing.get("endpoint_status", {}).get("state", "?")
        print_success(t(
            f"  既存の VS エンドポイント '{name}' を再利用します（state: {state}）",
            f"  Reusing existing VS endpoint '{name}' (state: {state})",
        ))
        return {**existing, "reused": True}

    # 2. SDK で作成 + ONLINE まで待機
    print(t(f"  VS エンドポイント '{name}' を作成中（最大 60 分、ONLINE まで待機）...",
             f"  Creating VS endpoint '{name}' (up to 60 min, waiting until ONLINE)..."))
    vsc = VectorSearchClient(
        workspace_url=host,
        personal_access_token=token,
        disable_notice=True,
    )
    try:
        vsc.create_endpoint_and_wait(
            name=name,
            endpoint_type=endpoint_type,
            verbose=True,
            timeout=timedelta(minutes=60),
        )
    except Exception as e:
        print_error(t(f"VS エンドポイント作成失敗: {str(e)[:200]}",
                       f"VS endpoint creation failed: {str(e)[:200]}"))
        return {"error": str(e)}
    info = api_get(f"/api/2.0/vector-search/endpoints/{name}", token, host)
    return info if isinstance(info, dict) else {"name": name}


def wait_for_vs_endpoint_ready(
    token: str, host: str, name: str, timeout_sec: int = 1200, poll_sec: int = 30
) -> bool:
    """Poll a VS endpoint until ONLINE or timeout. Returns True if ONLINE."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        info = api_get(f"/api/2.0/vector-search/endpoints/{name}", token, host)
        if "error" not in info:
            state = info.get("endpoint_status", {}).get("state", "")
            if state == "ONLINE":
                return True
        time.sleep(poll_sec)
    return False


def wait_for_warehouse_ready(
    profile_name: str, warehouse_id: str, timeout_sec: int = 300, poll_sec: int = 5
) -> bool:
    """Poll a warehouse until RUNNING/STARTING completes. Returns True on RUNNING."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            result = run_command(
                ["databricks", "warehouses", "get", warehouse_id, "-p", profile_name, "-o", "json"],
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                state = json.loads(result.stdout).get("state", "")
                if state == "RUNNING":
                    return True
                if state in ("STOPPED", "DELETED"):
                    return False
        except Exception:
            pass
        time.sleep(poll_sec)
    return False
