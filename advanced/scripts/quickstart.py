#!/usr/bin/env python3
"""
Quickstart setup script for Databricks agent development.

This script handles:
- Checking prerequisites (uv, nvm, Node 20, Databricks CLI)
- Databricks authentication (OAuth)
- MLflow experiment creation
- Environment variable configuration (.env)
- Lakebase instance setup (for memory-enabled templates)

Usage:
    uv run quickstart [OPTIONS]

Options:
    --profile NAME    Use specified Databricks profile (non-interactive)
    --host URL        Databricks workspace URL (for initial setup)
    --lakebase-autoscaling-project NAME  Autoscaling Lakebase project name
    --lakebase-autoscaling-branch NAME   Autoscaling Lakebase branch name
    -h, --help        Show this help message
"""

import argparse
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path


# ── i18n ──────────────────────────────────────────────────────────────
LANG = "ja"  # default; overridden by select_language()


def t(ja: str, en: str) -> str:
    """Return the string for the current language."""
    return ja if LANG == "ja" else en


def select_language():
    """Prompt user to select language at the very beginning."""
    global LANG
    print("=" * 50)
    print("  Language / 言語選択")
    print("=" * 50)
    print("  1) 日本語")
    print("  2) English")
    choice = input("\n  Select / 選択 [1]: ").strip()
    if choice == "2":
        LANG = "en"
        print("\n  → English selected\n")
    else:
        LANG = "ja"
        print("\n  → 日本語を選択しました\n")


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


def get_workspace_client(profile_name: str):
    """Create a WorkspaceClient with the given profile."""
    try:
        from databricks.sdk import WorkspaceClient

        return WorkspaceClient(profile=profile_name)
    except Exception:
        return None


def create_lakebase_instance(profile_name: str) -> dict:
    """Create a new Lakebase autoscaling instance (project + branch).

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
        name = input(t("新しい Lakebase オートスケーリングプロジェクト名を入力: ",
                        "Enter a name for the new Lakebase autoscaling project: ")).strip()
        if not name:
            print(t("  名前を入力してください。", "  Please enter a name."))
            continue

        # 使用可能な文字をチェック（英数字、ハイフン、アンダースコアのみ）
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$', name):
            print_error(t("プロジェクト名には英数字、ハイフン(-)、アンダースコア(_)のみ使用できます。先頭は英数字にしてください。",
                           "Project name can only contain alphanumeric characters, hyphens (-), and underscores (_). Must start with an alphanumeric character."))
            continue

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
            print_error(t(f"作成に失敗しました: {err_msg[:200]}",
                           f"Creation failed: {err_msg[:200]}"))
            if "already exists" in err_msg.lower():
                print(t("  この名前は既に使用されています。別の名前を入力してください。",
                         "  This name is already in use. Please enter a different name."))
            else:
                print(t("  名前を変えてもう一度試してください。",
                         "  Please try again with a different name."))
            continue


def select_lakebase_interactive(profile_name: str) -> dict:
    """Interactive Lakebase setup.

    Flow:
    1. New or existing?
    2. New -> Create autoscaling project + branch
    3. Existing -> Enter project + branch names

    Returns:
        Dict with {"type": "autoscaling", "project": str, "branch": str}
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
        return create_lakebase_instance(profile_name)

    # Existing autoscaling instance - ask for project and branch
    project = input(t("\nオートスケーリングプロジェクト名を入力: ",
                       "\nEnter the autoscaling project name: ")).strip()
    if not project:
        print_error(t("プロジェクト名は必須です",
                       "Project name is required"))
        sys.exit(1)

    branch = input(t("ブランチ名を入力: ",
                      "Enter the branch name: ")).strip()
    if not branch:
        print_error(t("ブランチ名は必須です",
                       "Branch name is required"))
        sys.exit(1)

    return {"type": "autoscaling", "project": project, "branch": branch}


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


# ── New helper functions ──


def get_auth_token(profile_name: str) -> str:
    """Get bearer token from Databricks CLI."""
    result = run_command(
        ["databricks", "auth", "token", "-p", profile_name, "-o", "json"],
        check=True,
    )
    return json.loads(result.stdout)["access_token"]


def run_sql_statement(statement: str, token: str, host: str, warehouse_id: str) -> dict:
    """Execute SQL via REST API."""
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
        if state == "FAILED":
            err = data.get("status", {}).get("error", {}).get("message", "Unknown error")
            print_error(f"SQL failed: {err}")
        return data
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print_error(f"SQL execution error: HTTP {e.code}: {body[:300]}")
        return {"status": {"state": "FAILED"}}
    except Exception as e:
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
    notebook_content = f"""# Databricks notebook source
import os
os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = "{warehouse_id}"

import mlflow
from mlflow.entities import UCSchemaLocation

mlflow.tracing.set_experiment_trace_location(
    location=UCSchemaLocation(catalog_name="{catalog}", schema_name="{schema}"),
    experiment_id="{experiment_id}",
)
print("Trace location set successfully.")
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
    submit_result = api_post("/api/2.0/jobs/runs/submit", token, host, {
        "run_name": "quickstart_trace_setup",
        "tasks": [{
            "task_key": "trace_setup",
            "notebook_task": {"notebook_path": notebook_path},
            "environment_key": "default",
        }],
        "environments": [{
            "environment_key": "default",
            "spec": {"client": "1"},
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
        print_error(t(f"実行失敗 (state={final_state}): {state_msg[:200]}",
                       f"Run failed (state={final_state}): {state_msg[:200]}"))
        return False


def select_vs_endpoint_interactive(token: str, host: str) -> str:
    """List Vector Search endpoints and let user select one. Returns endpoint name."""
    print_step(t("Vector Search エンドポイントの選択...", "Selecting Vector Search endpoint..."))
    ep_data = api_get("/api/2.0/vector-search/endpoints", token, host)
    endpoints = ep_data.get("endpoints", [])
    if not endpoints:
        print_error(t("利用可能な Vector Search エンドポイントがありません。",
                       "No Vector Search endpoints available."))
        print(t("  Databricks UI の Compute > Vector Search > Create Endpoint から作成してください。",
                 "  Create one from Databricks UI: Compute > Vector Search > Create Endpoint."))
        # Fall back to manual input
        name = input(t("\n  エンドポイント名を手動入力（スキップする場合は空Enter）: ",
                        "\n  Enter endpoint name manually (or press Enter to skip): ")).strip()
        return name

    # Sort: ONLINE first, then by name
    state_order = {"ONLINE": 0, "PROVISIONING": 1}
    endpoints.sort(key=lambda e: (state_order.get(e.get("endpoint_status", {}).get("state", ""), 9),
                                   e.get("name", "")))

    print(t("  利用可能な Vector Search エンドポイント:",
             "  Available Vector Search endpoints:"))
    for i, ep in enumerate(endpoints, 1):
        name = ep.get("name", "?")
        state = ep.get("endpoint_status", {}).get("state", "UNKNOWN")
        marker = " [ONLINE]" if state == "ONLINE" else f" [{state}]"
        print(f"    {i}. {name}{marker}")

    while True:
        choice = input(t("\n  番号で選択 [1]: ", "\n  Select by number [1]: ")).strip() or "1"
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
        print(t("  無効な選択です。もう一度入力してください。",
                 "  Invalid selection. Please try again."))


def select_warehouse_interactive(profile_name: str) -> tuple[str, str]:
    """List warehouses and let user select one. Returns (warehouse_id, warehouse_name)."""
    print_step(t("SQL ウェアハウスの選択...", "Selecting SQL warehouse..."))
    result = run_command(
        ["databricks", "warehouses", "list", "-p", profile_name, "-o", "json"],
        check=True,
    )
    warehouses = json.loads(result.stdout)
    if not warehouses:
        print_error(t("利用可能な SQL ウェアハウスがありません。",
                       "No SQL warehouses available."))
        sys.exit(1)

    # Sort: RUNNING first
    warehouses.sort(key=lambda w: (0 if w.get("state") == "RUNNING" else 1, w.get("name", "")))

    print(t("  利用可能なウェアハウス:", "  Available warehouses:"))
    for i, w in enumerate(warehouses, 1):
        state = w.get("state", "UNKNOWN")
        name = w.get("name", "?")
        wid = w.get("id", "?")
        marker = " [RUNNING]" if state == "RUNNING" else f" [{state}]"
        print(f"    {i}. {name} ({wid}){marker}")

    while True:
        choice = input(t("\n  番号で選択 [1]: ", "\n  Select by number [1]: ")).strip() or "1"
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(warehouses):
                selected = warehouses[idx]
                wid = selected["id"]
                wname = selected["name"]
                print_success(f"Warehouse: {wname} ({wid})")
                return wid, wname
        except ValueError:
            pass
        print(t("  無効な選択です。もう一度入力してください。",
                 "  Invalid selection. Please try again."))


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
    """全6テーブルと policy_docs_chunked が存在するかチェック。"""
    required_tables = ["customers", "products", "stores", "transactions", "transaction_items", "payment_history"]
    for table in required_tables:
        data = run_sql_statement(
            f"DESCRIBE TABLE `{catalog}`.`{schema}`.`{table}`", token, host, warehouse_id
        )
        if data.get("status", {}).get("state") not in ("SUCCEEDED", "CLOSED"):
            return False
    return True


def check_chunked_table_exists(token: str, host: str, warehouse_id: str, catalog: str, schema: str) -> bool:
    """policy_docs_chunked テーブルが存在するかチェック。"""
    data = run_sql_statement(
        f"DESCRIBE TABLE `{catalog}`.`{schema}`.policy_docs_chunked", token, host, warehouse_id
    )
    return data.get("status", {}).get("state") in ("SUCCEEDED", "CLOSED")


def generate_data(profile_name: str, warehouse_id: str, catalog: str, schema: str, token: str = "", host: str = ""):
    """Generate structured data and chunked policy docs."""
    data_dir = Path(__file__).parent.parent.parent / "data"
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
                    print_error(t(f"チャンク生成に失敗: {result.stderr[-300:]}",
                                   f"Chunk generation failed: {result.stderr[-300:]}"))
                    sys.exit(1)
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
        print_error(t(f"構造化データ生成に失敗: {result.stderr[-300:]}",
                       f"Structured data generation failed: {result.stderr[-300:]}"))
        sys.exit(1)

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
        print_error(t(f"ポリシー文書チャンク生成に失敗: {result.stderr[-300:]}",
                       f"Policy document chunk generation failed: {result.stderr[-300:]}"))
        sys.exit(1)


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
    """Create Vector Search index and wait for READY."""
    index_name = f"{catalog}.{schema}.policy_docs_index"
    print_step(t(f"Vector Search インデックスの作成 ({index_name})...",
                  f"Creating Vector Search index ({index_name})..."))

    # Check if already exists
    existing = api_get(f"/api/2.0/vector-search/indexes/{index_name}", token, host)
    if "error" not in existing and existing.get("status", {}).get("ready") == True:
        print_success(t(f"インデックス {index_name} は既に READY です（スキップ）",
                         f"Index {index_name} is already READY (skipping)"))
        return index_name

    # Create
    body = {
        "name": index_name,
        "endpoint_name": vs_endpoint,
        "primary_key": "chunk_id",
        "delta_sync_index_spec": {
            "source_table": f"{catalog}.{schema}.policy_docs_chunked",
            "pipeline_type": "TRIGGERED",
            "embedding_source_columns": [
                {
                    "name": "content",
                    "embedding_model_endpoint_name": "databricks-qwen3-embedding-0-6b",
                }
            ],
        },
    }
    result = api_post("/api/2.0/vector-search/indexes", token, host, body)
    if "error" in result:
        # May already exist
        if "ALREADY_EXISTS" in str(result.get("error", "")):
            print(t("  インデックスは既に存在します。ステータス確認中...",
                     "  Index already exists. Checking status..."))
        else:
            print_error(t(f"インデックス作成失敗: {result['error']}",
                           f"Index creation failed: {result['error']}"))
            print(t("  手動で Databricks UI から作成してください。",
                     "  Please create it manually from the Databricks UI."))
            return index_name
    else:
        print_success(t("インデックス作成開始", "Index creation started"))

    # Poll for READY
    print(t("  READY 待ち（最大10分）...", "  Waiting for READY (up to 10 min)..."), end="", flush=True)
    for i in range(40):  # 40 * 15s = 10 min
        time.sleep(15)
        print(".", end="", flush=True)
        status = api_get(f"/api/2.0/vector-search/indexes/{index_name}", token, host)
        if status.get("status", {}).get("ready") == True:
            print()
            print_success(t(f"インデックス READY: {index_name}",
                             f"Index READY: {index_name}"))
            return index_name

    print()
    print(t("  ⚠ タイムアウト。Databricks UI でステータスを確認してください。",
             "  Warning: Timeout. Please check the status in the Databricks UI."))
    return index_name


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

    version "1" のシンプルな形式を使用。テーブルは identifier でアルファベット順ソート必須。
    """
    data_sources_tables = [
        {"identifier": f"{catalog}.{schema}.{t}"}
        for t in sorted(tables)
    ]

    space_config = {
        "version": "1",
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


def main():
    parser = argparse.ArgumentParser(
        description="FreshMart AI Agent - Quickstart Setup",
    )
    parser.add_argument("--profile", default=None, help="Databricks CLI profile name")
    parser.add_argument("--host", default=None, help="Databricks workspace URL")
    parser.add_argument("--catalog", default=None, help="Unity Catalog name")
    parser.add_argument("--schema", default=None, help="Schema name")
    parser.add_argument("--warehouse-id", default=None, help="SQL Warehouse ID")
    parser.add_argument("--vs-endpoint", default=None, help="Vector Search endpoint name")
    parser.add_argument(
        "--lakebase-autoscaling-project",
        help="Lakebase autoscaling project name",
    )
    parser.add_argument(
        "--lakebase-autoscaling-branch",
        help="Lakebase autoscaling branch name",
    )
    args = parser.parse_args()

    select_language()

    try:
        print_header(t("フレッシュマート AI エージェント - クイックスタートセットアップ",
                        "FreshMart AI Agent - Quickstart Setup"))

        # ── Phase 1: 前提条件チェック ──
        print_step(t("[1/7] 前提条件チェック", "[1/7] Prerequisites check"))
        prereqs = check_prerequisites()
        missing = check_missing_prerequisites(prereqs)
        if missing:
            print_error(t("不足している前提条件:", "Missing prerequisites:"))
            for item in missing:
                print(f"  • {item}")
            print(t("\nインストール後に再実行してください。",
                     "\nPlease install the above and run again."))
            sys.exit(1)
        node_error = check_node_version()
        if node_error:
            print_error(t(f"Node.js バージョンエラー: {node_error}",
                           f"Node.js version error: {node_error}"))
            sys.exit(1)
        print_success(t("前提条件OK", "Prerequisites OK"))
        setup_env_file()

        # ── Phase 2: 認証 ──
        print_step(t("[2/7] Databricks 認証", "[2/7] Databricks authentication"))
        profile_name = setup_databricks_auth(args.profile, args.host)
        username = get_databricks_username(profile_name)
        host = get_databricks_host(profile_name)
        token = get_auth_token(profile_name)
        print_success(t(f"認証OK: {username}", f"Authenticated: {username}"))
        print(t(f"  ワークスペース: {host}", f"  Workspace: {host}"))

        # ── Phase 3: ユーザー入力 ──
        print_step(t("[3/7] ワークスペース設定", "[3/7] Workspace configuration"))

        # Catalog
        default_catalog = args.catalog or username.split("@")[0].replace(".", "_")
        catalog = input(t(f"  カタログ名 [{default_catalog}]: ",
                           f"  Catalog name [{default_catalog}]: ")).strip() or default_catalog

        # Schema
        default_schema = args.schema or "retail_agent"
        schema = input(t(f"  スキーマ名 [{default_schema}]: ",
                          f"  Schema name [{default_schema}]: ")).strip() or default_schema

        # Warehouse
        if args.warehouse_id:
            warehouse_id = args.warehouse_id
            print_success(f"Warehouse ID: {warehouse_id}")
        else:
            warehouse_id, _ = select_warehouse_interactive(profile_name)

        # VS Endpoint
        if args.vs_endpoint:
            vs_endpoint = args.vs_endpoint
            # Verify the provided endpoint exists
            ep_status = api_get(f"/api/2.0/vector-search/endpoints/{vs_endpoint}", token, host)
            if "error" not in ep_status:
                ep_state = ep_status.get("endpoint_status", {}).get("state", "UNKNOWN")
                print_success(t(f"VS エンドポイント: {vs_endpoint} ({ep_state})",
                                 f"VS endpoint: {vs_endpoint} ({ep_state})"))
            else:
                print(t(f"  ⚠ エンドポイント {vs_endpoint} が見つかりません。",
                         f"  Warning: Endpoint {vs_endpoint} not found."))
                vs_endpoint = ""
        else:
            vs_endpoint = select_vs_endpoint_interactive(token, host)

        # ── Phase 4: リソース作成 ──
        print_step(t("[4/7] リソース作成", "[4/7] Resource creation"))

        # 4-1: Catalog & Schema
        create_catalog_schema(token, host, warehouse_id, catalog, schema)

        # 4-2 & 4-3: Data generation (skip if tables already exist)
        generate_data(profile_name, warehouse_id, catalog, schema, token=token, host=host)

        # 4-4: CDF
        enable_cdf(token, host, warehouse_id, catalog, schema)

        # 4-5: Vector Search Index
        vs_index = ""
        if vs_endpoint:
            vs_index = create_vector_search_index(token, host, catalog, schema, vs_endpoint)
        else:
            vs_index = f"{catalog}.{schema}.policy_docs_index"
            print(t("  ⚠ VS エンドポイント未指定。インデックスは手動で作成してください。",
                     "  Warning: VS endpoint not specified. Please create the index manually."))

        # 4-6: Genie Space
        genie_space_id = create_genie_space(token, host, warehouse_id, catalog, schema)

        # 4-7: Lakebase
        lakebase_config = None
        lakebase_required = (
            (args.lakebase_autoscaling_project and args.lakebase_autoscaling_branch)
            or check_lakebase_required()
        )
        if lakebase_required:
            lakebase_config = setup_lakebase(
                profile_name, username,
                autoscaling_project=args.lakebase_autoscaling_project,
                autoscaling_branch=args.lakebase_autoscaling_branch,
            )
            update_databricks_yml_lakebase(lakebase_config)
            update_app_yaml_lakebase(lakebase_config)

        # 4-8: MLflow Experiments
        monitoring_name, monitoring_id, eval_name, eval_id = create_mlflow_experiment(
            profile_name, username
        )

        # ── Phase 5: .env 更新 ──
        print_step(t("[5/7] 環境設定 (.env)", "[5/7] Environment configuration (.env)"))
        update_env_file("DATABRICKS_HOST", host)
        update_env_file("MLFLOW_EXPERIMENT_ID", monitoring_id)
        update_env_file("MLFLOW_EVAL_EXPERIMENT_ID", eval_id)
        update_env_file("GENIE_SPACE_ID", genie_space_id)
        update_env_file("VECTOR_SEARCH_INDEX", vs_index)
        update_databricks_yml_experiment(monitoring_id)
        update_databricks_yml_resources(genie_space_id, vs_index)
        print_success(t(".env / databricks.yml 更新完了",
                         ".env / databricks.yml updated"))

        # Delta Table tracing
        # 既存 Experiment に UC テーブル紐付けがあるか確認
        tracing_dest = ""
        _existing_dest = ""
        try:
            exp_result = run_command(
                ["databricks", "experiments", "get-experiment", monitoring_id, "-p", profile_name, "-o", "json"],
                check=False,
            )
            if exp_result.returncode == 0:
                exp_data = json.loads(exp_result.stdout)
                exp_tags = exp_data.get("experiment", exp_data).get("tags", [])
                for tag in exp_tags:
                    if tag.get("key") == "mlflow.experiment.databricksTraceDestinationPath":
                        _existing_dest = tag.get("value", "")
                        break
        except Exception:
            pass

        if _existing_dest:
            # 既存 Experiment に Delta Table 紐付けが既にある
            tracing_dest = _existing_dest
            update_env_file("MLFLOW_TRACING_DESTINATION", tracing_dest)
            update_env_file("MLFLOW_TRACING_SQL_WAREHOUSE_ID", warehouse_id)
            append_env_to_app_yaml("MLFLOW_TRACING_DESTINATION", tracing_dest)
            append_env_to_app_yaml("MLFLOW_TRACING_SQL_WAREHOUSE_ID", warehouse_id)
            print_success(t(f"トレース送信先: Unity Catalog ({tracing_dest})（既存 Experiment から検出）",
                             f"Trace destination: Unity Catalog ({tracing_dest}) (detected from existing Experiment)"))
        else:
            print()
            print(t("  トレース送信先の選択:", "  Select trace destination:"))
            print(t("    デフォルト: MLflow Experiment（すぐに使える）",
                     "    Default: MLflow Experiment (ready to use)"))
            print(t("    オプション: Unity Catalog Delta Table（SQL クエリ可能、長期保持）",
                     "    Option: Unity Catalog Delta Table (SQL queryable, long-term retention)"))
            use_delta = input(t("\n  Unity Catalog Delta Table に送信しますか？ (y/N): ",
                                 "\n  Send traces to Unity Catalog Delta Table? (y/N): ")).strip().lower()
            if use_delta == "y":
                default_dest = f"{catalog}.{schema}"
                tracing_dest = input(t(f"  送信先スキーマ [{default_dest}]: ",
                                        f"  Destination schema [{default_dest}]: ")).strip() or default_dest

                # カタログ・スキーマの存在確認、なければ作成
                if "." in tracing_dest:
                    _t_cat, _t_sch = tracing_dest.split(".", 1)
                    verify = run_sql_statement(f"DESCRIBE SCHEMA `{_t_cat}`.`{_t_sch}`", token, host, warehouse_id)
                    if verify.get("status", {}).get("state") not in ("SUCCEEDED", "CLOSED"):
                        print(t(f"  スキーマ {tracing_dest} が存在しません。作成します...",
                                 f"  Schema {tracing_dest} does not exist. Creating..."))
                        run_sql_statement(f"CREATE CATALOG IF NOT EXISTS `{_t_cat}`", token, host, warehouse_id)
                        run_sql_statement(f"CREATE SCHEMA IF NOT EXISTS `{_t_cat}`.`{_t_sch}`", token, host, warehouse_id)
                        verify2 = run_sql_statement(f"DESCRIBE SCHEMA `{_t_cat}`.`{_t_sch}`", token, host, warehouse_id)
                        if verify2.get("status", {}).get("state") in ("SUCCEEDED", "CLOSED"):
                            print_success(t(f"スキーマ作成完了: {tracing_dest}",
                                             f"Schema created: {tracing_dest}"))
                        else:
                            print_error(t(f"スキーマ {tracing_dest} の作成に失敗しました。権限を確認してください。",
                                           f"Failed to create schema {tracing_dest}. Please check permissions."))

                update_env_file("MLFLOW_TRACING_DESTINATION", tracing_dest)
                update_env_file("MLFLOW_TRACING_SQL_WAREHOUSE_ID", warehouse_id)
                append_env_to_app_yaml("MLFLOW_TRACING_DESTINATION", tracing_dest)
                append_env_to_app_yaml("MLFLOW_TRACING_SQL_WAREHOUSE_ID", warehouse_id)
                print_success(t(f"トレース送信先: Unity Catalog ({tracing_dest})",
                                 f"Trace destination: Unity Catalog ({tracing_dest})"))
                print_success(t(".env と app.yaml の両方に設定を追加しました",
                                 "Settings added to both .env and app.yaml"))
            else:
                print_success(t("トレース送信先: MLflow Experiment（デフォルト）",
                                 "Trace destination: MLflow Experiment (default)"))

        # Prompt Registry
        print()
        print(t("  Prompt Registry の選択:", "  Prompt Registry selection:"))
        print(t("    デフォルト: ハードコード（agent.py に組み込み済み、設定不要）",
                 "    Default: Hardcoded (built into agent.py, no setup needed)"))
        print(t("    オプション: Unity Catalog Prompt Registry（バージョン管理・A/Bテスト・ロールバック）",
                 "    Option: Unity Catalog Prompt Registry (version control, A/B testing, rollback)"))
        use_prompt_registry = input(t("\n  Prompt Registry を使用しますか？ (y/N): ",
                                       "\n  Use Prompt Registry? (y/N): ")).strip().lower()
        if use_prompt_registry == "y":
            prompt_name = f"{catalog}.{schema}.freshmart_system_prompt"
            print(t(f"  プロンプト登録中: {prompt_name} ...",
                     f"  Registering prompt: {prompt_name} ..."))
            try:
                result = subprocess.run(
                    ["uv", "run", "register-prompt", "--name", prompt_name],
                    capture_output=True, text=True,
                )
                if result.returncode == 0:
                    update_env_file("PROMPT_REGISTRY_NAME", prompt_name)
                    append_env_to_app_yaml("PROMPT_REGISTRY_NAME", prompt_name)
                    print_success(f"Prompt Registry: {prompt_name}")
                else:
                    print_error(t(f"プロンプト登録に失敗: {result.stderr[-200:]}",
                                   f"Prompt registration failed: {result.stderr[-200:]}"))
                    print(t("  ハードコード版を使用します。",
                             "  Using hardcoded version."))
            except Exception as e:
                print_error(t(f"プロンプト登録に失敗: {e}",
                               f"Prompt registration failed: {e}"))
                print(t("  ハードコード版を使用します。",
                         "  Using hardcoded version."))
        else:
            print_success(t("Prompt Registry: 使用しない（ハードコード版）",
                             "Prompt Registry: Not used (hardcoded version)"))

        # workshop_setup.py のプレースホルダーを更新
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
                '"<LAKEBASE-PROJECT>"': f'"{lakebase_config["project"]}"' if lakebase_config else '"<LAKEBASE-PROJECT>"',
                '"<LAKEBASE-BRANCH>"': f'"{lakebase_config["branch"]}"' if lakebase_config else '"<LAKEBASE-BRANCH>"',
            }
            for old, new in replacements.items():
                content = content.replace(old, new)
            setup_notebook.write_text(content)
            print_success(t("workshop_setup.py のプレースホルダーを更新しました",
                             "Updated placeholders in workshop_setup.py"))

        # ── Phase 6: 依存関係 ──
        print_step(t("[6/7] 依存関係のインストール", "[6/7] Installing dependencies"))
        install_dependencies()

        # ── Phase 7: サマリー ──
        print_header(t("セットアップ完了！", "Setup Complete!"))
        if LANG == "ja":
            summary = f"""
✓ カタログ: {catalog}
✓ スキーマ: {catalog}.{schema}
✓ 構造化データ: 6テーブル生成済み
✓ ポリシー文書: チャンク分割済み
✓ Vector Search: {vs_index}
✓ Genie Space ID: {genie_space_id}

✓ MLflow モニタリング実験: {monitoring_name}
  ID: {monitoring_id}
✓ MLflow 評価実験: {eval_name}
  ID: {eval_id}"""
        else:
            summary = f"""
✓ Catalog: {catalog}
✓ Schema: {catalog}.{schema}
✓ Structured data: 6 tables generated
✓ Policy documents: Chunked
✓ Vector Search: {vs_index}
✓ Genie Space ID: {genie_space_id}

✓ MLflow monitoring experiment: {monitoring_name}
  ID: {monitoring_id}
✓ MLflow evaluation experiment: {eval_name}
  ID: {eval_id}"""

        if host:
            summary += f"\n  {host}/ml/experiments/{monitoring_id}"

        if tracing_dest:
            summary += t(f"\n\n✓ トレース送信先: Unity Catalog ({tracing_dest})",
                          f"\n\n✓ Trace destination: Unity Catalog ({tracing_dest})")
            summary += t("\n  ⚠ トレーステーブルの初期作成が必要です（下記参照）",
                          "\n  Warning: Initial trace table creation required (see below)")
        else:
            summary += t("\n\n✓ トレース送信先: MLflow Experiment（デフォルト）",
                          "\n\n✓ Trace destination: MLflow Experiment (default)")

        if lakebase_config:
            summary += f"\n\n✓ Lakebase: {lakebase_config['project']} (branch: {lakebase_config['branch']})"

        if not tracing_dest:
            summary += t("\n\n次のステップ: uv run start-app\n",
                          "\n\nNext step: uv run start-app\n")
        print(summary)

        # Delta Table トレーステーブルの自動作成（選択した場合のみ）
        if tracing_dest and "." in tracing_dest and not _existing_dest:
            # 新規設定の場合のみ実行（既存 Experiment から検出した場合は既に設定済みなのでスキップ）
            _cat, _sch = tracing_dest.split(".", 1)
            print()
            print("=" * 60)
            print(t("Unity Catalog トレーステーブルの初期作成",
                     "Unity Catalog Trace Table Setup"))
            print("=" * 60)
            print(t("  Databricks 上でサーバーレス実行してトレーステーブルを作成します...",
                     "  Running serverless on Databricks to create trace tables..."))

            success = run_trace_setup_on_databricks(
                profile_name=profile_name,
                username=username,
                catalog=_cat,
                schema=_sch,
                warehouse_id=warehouse_id,
                experiment_id=monitoring_id,
            )
            if success:
                print_success(t("トレーステーブル作成完了!", "Trace table setup complete!"))
                print(t("  以下の Delta Table が作成されました:",
                         "  The following Delta Tables were created:"))
                print(f"    - {tracing_dest}.mlflow_experiment_trace_otel_spans")
                print(f"    - {tracing_dest}.mlflow_experiment_trace_otel_logs")
                print(f"    - {tracing_dest}.mlflow_experiment_trace_otel_metrics")
            else:
                print_error(t("自動作成に失敗しました。手動で実行してください:",
                               "Automatic setup failed. Please run manually:"))
                print()
                print("```python")
                print("import os")
                print(f'os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = "{warehouse_id}"')
                print("import mlflow")
                print("from mlflow.entities import UCSchemaLocation")
                print(f'mlflow.tracing.set_experiment_trace_location(')
                print(f'    location=UCSchemaLocation(catalog_name="{_cat}", schema_name="{_sch}"),')
                print(f'    experiment_id="{monitoring_id}",')
                print(")")
                print("```")
            print("=" * 60)

        # チームメンバーへの共有情報
        print()
        print("=" * 60)
        print(t("チームメンバーに共有する情報",
                 "Information to share with team members"))
        print("=" * 60)
        print()
        print(t("チームでハンズオンを実施する場合、以下の情報をメンバーに共有してください。",
                 "If running a team hands-on, share the following information with members."))
        print(t("メンバーはクイックスタート実行時にこれらの値を入力します。",
                 "Members will enter these values when running quickstart."))
        print()
        print(t(f"  カタログ名:            {catalog}",
                 f"  Catalog:               {catalog}"))
        print(t(f"  スキーマ名:            {schema}",
                 f"  Schema:                {schema}"))
        print(t(f"  VS エンドポイント名:   {vs_endpoint}",
                 f"  VS endpoint:           {vs_endpoint}"))
        print(f"  Genie Space ID:        {genie_space_id}")
        if lakebase_config:
            print(t(f"  Lakebase プロジェクト:  {lakebase_config['project']}",
                     f"  Lakebase project:      {lakebase_config['project']}"))
            print(t(f"  Lakebase ブランチ:      {lakebase_config['branch']}",
                     f"  Lakebase branch:       {lakebase_config['branch']}"))
        print(t(f"  モニタリング Exp ID:   {monitoring_id}",
                 f"  Monitoring Exp ID:     {monitoring_id}"))
        print(t(f"  評価 Exp ID:           {eval_id}",
                 f"  Evaluation Exp ID:     {eval_id}"))
        print()
        print(t("メンバーの権限付与は以下で実行できます：",
                 "Grant permissions to members with:"))
        print(f"  uv run grant-team-access member1@company.com member2@company.com")
        print("=" * 60)

    except KeyboardInterrupt:
        print(t("\n\nセットアップが中断されました。",
                 "\n\nSetup was interrupted."))
        sys.exit(1)
    except Exception as e:
        print_error(t(f"セットアップ中にエラーが発生しました: {e}",
                       f"Error during setup: {e}"))
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
