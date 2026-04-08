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
    --lakebase-provisioned-name NAME   Provisioned Lakebase instance name
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
    print("\nTroubleshooting tips:")
    print("  • Ensure you have network connectivity to your Databricks workspace")
    print("  • Try running 'databricks auth login' manually to see detailed errors")
    print("  • Check that your workspace URL is correct")
    print("  • If using a browser for OAuth, ensure popups are not blocked")


def print_troubleshooting_api() -> None:
    print("\nTroubleshooting tips:")
    print("  • Your authentication token may have expired - try 'databricks auth login' to refresh")
    print("  • Verify your profile is valid with 'databricks auth profiles'")
    print("  • Check network connectivity to your Databricks workspace")


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
    print_step("Checking prerequisites...")

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
                print_success(f"{name} is installed: {version}")
            except Exception:
                print_success(f"{name} is installed")
        else:
            print(f"  {name} is not installed")

    return prereqs


def check_missing_prerequisites(prereqs: dict[str, bool]) -> list[str]:
    """Return list of missing prerequisites with install instructions."""
    missing = []

    if not prereqs["uv"]:
        missing.append("uv - Install with: curl -LsSf https://astral.sh/uv/install.sh | sh")

    if not prereqs["node"] or not prereqs["npm"]:
        missing.append("Node.js 20 - Install with: nvm install 20 (or download from nodejs.org)")

    if not prereqs["databricks"]:
        if platform.system() == "Darwin":
            missing.append("Databricks CLI - Install with: brew install databricks/tap/databricks")
        else:
            missing.append(
                "Databricks CLI - Install with: curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh"
            )

    if missing:
        missing.append(
            "Note: These install commands are for Unix/macOS. For Windows, please visit the official documentation for each tool."
        )

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
    print_step("Setting up configuration files...")

    env_local = Path(".env")
    env_example = Path(".env.example")

    if env_local.exists():
        print("  .env already exists, skipping copy...")
    elif env_example.exists():
        shutil.copy(env_example, env_local)
        print_success("Copied .env.example to .env")
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
        print_success("Created .env")


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
    print(f"\nAuthenticating profile '{profile_name}'...")
    print("You will be prompted to log in to Databricks in your browser.\n")

    cmd = ["databricks", "auth", "login", "--profile", profile_name]
    if host:
        cmd.extend(["--host", host])

    try:
        # Run interactively so user can see browser prompt
        result = subprocess.run(cmd)
        return result.returncode == 0
    except Exception as e:
        print_error(f"Authentication failed: {e}")
        return False


def select_profile_interactive(profiles: list[dict]) -> str:
    """Let user select a profile interactively."""
    print("\nFound existing Databricks profiles:\n")

    # Print header and profiles
    for i, profile in enumerate(profiles, 1):
        print(f"  {i}) {profile['line']}")

    print()

    while True:
        choice = input("Enter the number of the profile you want to use: ").strip()
        if not choice:
            print_error("Profile selection is required")
            continue

        try:
            index = int(choice) - 1
            if 0 <= index < len(profiles):
                return profiles[index]["name"]
            else:
                print_error(f"Please choose a number between 1 and {len(profiles)}")
        except ValueError:
            print_error("Please enter a valid number")


def setup_databricks_auth(profile_arg: str = None, host_arg: str = None) -> str:
    """Set up Databricks authentication and return the profile name."""
    print_step("Setting up Databricks authentication...")

    # If profile was specified via CLI, use it directly
    if profile_arg:
        profile_name = profile_arg
        print(f"Using specified profile: {profile_name}")
    else:
        # Check for existing profiles
        profiles = get_databricks_profiles()

        if profiles:
            profile_name = select_profile_interactive(profiles)
            print(f"\nSelected profile: {profile_name}")
        else:
            # No profiles exist - need to create one
            profile_name = None

    # Validate or authenticate the profile
    if profile_name:
        if validate_profile(profile_name):
            print_success(f"Successfully validated profile '{profile_name}'")
        else:
            print(f"Profile '{profile_name}' is not authenticated.")
            if not authenticate_profile(profile_name):
                print_error(f"Failed to authenticate profile '{profile_name}'")
                print_troubleshooting_auth()
                sys.exit(1)
            print_success(f"Successfully authenticated profile '{profile_name}'")
    else:
        # Create new profile
        print("No existing profiles found. Setting up Databricks authentication...")

        if host_arg:
            host = host_arg
            print(f"Using specified host: {host}")
        else:
            host = input(
                "\nPlease enter your Databricks host URL\n(e.g., https://your-workspace.cloud.databricks.com): "
            ).strip()

            if not host:
                print_error("Databricks host is required")
                sys.exit(1)

        profile_name = "DEFAULT"
        if not authenticate_profile(profile_name, host):
            print_error("Databricks authentication failed")
            print_troubleshooting_auth()
            sys.exit(1)
        print_success(f"Successfully authenticated with Databricks")

    # Update .env with profile
    update_env_file("DATABRICKS_CONFIG_PROFILE", profile_name)
    update_env_file("MLFLOW_TRACKING_URI", f'"databricks://{profile_name}"')
    print_success(f"Databricks profile '{profile_name}' saved to .env")

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
        print_error(f"Failed to get Databricks username: {e}")
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
            print_success(f"Created experiment '{base_name}' with ID: {experiment_id}")
            return base_name, experiment_id

        # Name already exists, try with random suffix
        print(f"Experiment '{base_name}' already exists, creating with random suffix...")
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
        print_success(f"Created experiment '{new_name}' with ID: {experiment_id}")
        return new_name, experiment_id

    except Exception as e:
        print_error(f"Failed to create MLflow experiment '{base_name}': {e}")
        print_troubleshooting_api()
        sys.exit(1)


def create_mlflow_experiment(
    profile_name: str, username: str
) -> tuple[str, str, str, str]:
    """Create two MLflow experiments (monitoring + evaluation) and return
    (monitoring_name, monitoring_id, eval_name, eval_id)."""
    print_step("Creating MLflow experiments (monitoring + evaluation)...")

    monitoring_name, monitoring_id = _create_single_experiment(
        profile_name, f"/Users/{username}/freshmart-agent-monitoring"
    )
    eval_name, eval_id = _create_single_experiment(
        profile_name, f"/Users/{username}/freshmart-agent-evaluation"
    )

    return monitoring_name, monitoring_id, eval_name, eval_id


def check_lakebase_required() -> bool:
    """Check if databricks.yml has Lakebase configuration (provisioned or autoscaling)."""
    databricks_yml = Path("databricks.yml")
    if not databricks_yml.exists():
        return False

    content = databricks_yml.read_text()
    return (
        "LAKEBASE_INSTANCE_NAME" in content
        or "LAKEBASE_AUTOSCALING_PROJECT" in content
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
        print_error("Could not connect to Databricks. Check your CLI profile.")
        sys.exit(1)

    name = input("Enter a name for the new Lakebase autoscaling project: ").strip()
    if not name:
        print_error("Instance name is required")
        sys.exit(1)

    print(f"\nCreating Lakebase autoscaling project '{name}'...")
    try:
        from databricks.sdk.service.postgres import Branch, BranchSpec, Project, ProjectSpec

        project_op = w.postgres.create_project(
            project=Project(spec=ProjectSpec(display_name=name)),
            project_id=name,
        )
        project = project_op.wait()
        project_short = project.name.removeprefix("projects/")
        print_success(f"Created project: {project_short}")

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
        print_success(f"Created branch: {branch_name} (id: {branch.uid})")

        return {"type": "autoscaling", "project": project_short, "branch": branch_name}
    except Exception as e:
        print_error(f"Failed to create Lakebase instance: {e}")
        sys.exit(1)


def select_lakebase_interactive(profile_name: str) -> dict:
    """Interactive Lakebase setup.

    Flow:
    1. New or existing?
    2. New -> Create autoscaling project + branch
    3. Existing -> Provisioned or autoscaling?
       - Provisioned -> Enter instance name
       - Autoscaling -> Enter project + branch names

    Returns:
        Dict with either:
        - {"type": "provisioned", "instance_name": str}
        - {"type": "autoscaling", "project": str, "branch": str}
    """
    print("\nLakebase Setup")
    print("  1) Create a new Lakebase instance")
    print("  2) Use an existing Lakebase instance")
    print()

    while True:
        choice = input("Enter your choice (1 or 2): ").strip()
        if choice in ("1", "2"):
            break
        print_error("Please enter 1 or 2")

    if choice == "1":
        return create_lakebase_instance(profile_name)

    # Existing instance
    print("\nWhat type of Lakebase instance?")
    print("  See https://docs.databricks.com/aws/en/oltp/#feature-comparison for details.")
    print("  1) Autoscaling (recommended)")
    print("  2) Provisioned")
    print()

    while True:
        type_choice = input("Enter your choice (1 or 2): ").strip()
        if type_choice in ("1", "2"):
            break
        print_error("Please enter 1 or 2")

    if type_choice == "2":
        name = input("\nEnter the provisioned Lakebase instance name: ").strip()
        if not name:
            print_error("Instance name is required")
            sys.exit(1)
        return {"type": "provisioned", "instance_name": name}

    # Autoscaling - ask for project and branch
    project = input("\nEnter the autoscaling project name: ").strip()
    if not project:
        print_error("Project name is required")
        sys.exit(1)

    branch = input("Enter the branch name: ").strip()
    if not branch:
        print_error("Branch name is required")
        sys.exit(1)

    return {"type": "autoscaling", "project": project, "branch": branch}


def validate_lakebase_instance(profile_name: str, lakebase_name: str) -> dict | None:
    """Validate that the Lakebase instance exists and user has access.

    Returns the instance info dict on success, None on failure.
    """
    print(f"Validating Lakebase instance '{lakebase_name}'...")

    result = run_command(
        [
            "databricks",
            "-p",
            profile_name,
            "database",
            "get-database-instance",
            lakebase_name,
            "--output",
            "json",
        ],
        check=False,
    )

    if result.returncode == 0:
        print_success(f"Lakebase instance '{lakebase_name}' validated")
        return json.loads(result.stdout)

    # Check if database command is not recognized (old CLI version)
    if 'unknown command "database" for "databricks"' in (result.stderr or ""):
        print_error(
            "The 'databricks database' command requires a newer version of the Databricks CLI."
        )
        print("  Please upgrade: https://docs.databricks.com/dev-tools/cli/install.html")
        return None

    error_msg = result.stderr.lower() if result.stderr else ""
    if "not found" in error_msg:
        print_error(
            f"Lakebase instance '{lakebase_name}' not found. Please check the instance name."
        )
    elif "permission" in error_msg or "forbidden" in error_msg or "unauthorized" in error_msg:
        print_error(f"No permission to access Lakebase instance '{lakebase_name}'")
    else:
        print_error(
            f"Failed to validate Lakebase instance: {result.stderr.strip() if result.stderr else 'Unknown error'}"
        )
    return None


def validate_lakebase_autoscaling(profile_name: str, project: str, branch: str) -> dict | None:
    """Validate that the Lakebase autoscaling project and branch exist.

    Uses the postgres API (/api/2.0/postgres/) to verify the project and branch,
    then fetches the endpoint host for PGHOST.

    Returns a dict with {"host": str} on success (host may be empty if endpoint
    not found), or None on failure.
    """
    print(f"Validating Lakebase autoscaling project '{project}', branch '{branch}'...")

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
            print_error(
                f"Lakebase autoscaling project '{project}' not found. Please check the project name."
            )
        elif "permission" in error_msg or "forbidden" in error_msg or "unauthorized" in error_msg:
            print_error(f"No permission to access Lakebase project '{project}'")
        else:
            print_error(
                f"Failed to validate Lakebase project: {result.stderr.strip() if result.stderr else 'Unknown error'}"
            )
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
            print_error(
                f"Lakebase autoscaling branch '{branch}' not found in project '{project}'. Please check the branch name."
            )
        elif "permission" in error_msg or "forbidden" in error_msg or "unauthorized" in error_msg:
            print_error(f"No permission to access Lakebase branch '{branch}'")
        else:
            print_error(
                f"Failed to validate Lakebase branch: {result.stderr.strip() if result.stderr else 'Unknown error'}"
            )
        return None

    print_success(f"Lakebase autoscaling project '{project}', branch '{branch}' validated")

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

    return {"host": pg_host}


def setup_lakebase(
    profile_name: str,
    username: str,
    provisioned_name: str = None,
    autoscaling_project: str = None,
    autoscaling_branch: str = None,
) -> dict:
    """Set up Lakebase instance for memory features.

    Returns:
        Dict with either:
        - {"type": "provisioned", "instance_name": str}
        - {"type": "autoscaling", "project": str, "branch": str}
    """
    print_step("Setting up Lakebase instance for memory...")

    # If --lakebase-provisioned-name was provided, use it directly
    if provisioned_name:
        print(f"Using provided provisioned Lakebase instance: {provisioned_name}")
        instance_info = validate_lakebase_instance(profile_name, provisioned_name)
        if not instance_info:
            sys.exit(1)
        update_env_file("LAKEBASE_INSTANCE_NAME", provisioned_name)
        update_env_file("LAKEBASE_AUTOSCALING_PROJECT", "")
        update_env_file("LAKEBASE_AUTOSCALING_BRANCH", "")
        print_success(f"Lakebase instance name '{provisioned_name}' saved to .env")

        # Set up PostgreSQL connection environment variables
        pg_host = instance_info.get("read_write_dns", "")
        if pg_host:
            update_env_file("PGHOST", pg_host)
            print_success(f"PGHOST set to '{pg_host}'")
        else:
            print_error("Could not get read_write_dns from Lakebase instance")

        update_env_file("PGUSER", username)
        print_success(f"PGUSER set to '{username}'")

        update_env_file("PGDATABASE", "databricks_postgres")
        print_success("PGDATABASE set to 'databricks_postgres'")

        return {"type": "provisioned", "instance_name": provisioned_name}

    # If --lakebase-autoscaling-project and --lakebase-autoscaling-branch were provided
    if autoscaling_project and autoscaling_branch:
        print(f"Using autoscaling Lakebase: project={autoscaling_project}, branch={autoscaling_branch}")
        branch_info = validate_lakebase_autoscaling(profile_name, autoscaling_project, autoscaling_branch)
        if not branch_info:
            sys.exit(1)
        update_env_file("LAKEBASE_AUTOSCALING_PROJECT", autoscaling_project)
        update_env_file("LAKEBASE_AUTOSCALING_BRANCH", autoscaling_branch)
        update_env_file("LAKEBASE_INSTANCE_NAME", "")

        # Set up PostgreSQL connection environment variables
        pg_host = branch_info.get("host", "")
        if pg_host:
            update_env_file("PGHOST", pg_host)
            print_success(f"PGHOST set to '{pg_host}'")
        else:
            print_error("Could not get endpoint host from Lakebase branch (PGHOST not set)")

        update_env_file("PGUSER", username)
        print_success(f"PGUSER set to '{username}'")

        update_env_file("PGDATABASE", "databricks_postgres")
        print_success("PGDATABASE set to 'databricks_postgres'")

        print_success(
            f"Lakebase autoscaling config saved to .env (project: {autoscaling_project}, branch: {autoscaling_branch})"
        )
        return {"type": "autoscaling", "project": autoscaling_project, "branch": autoscaling_branch}

    # Interactive selection
    selection = select_lakebase_interactive(profile_name)

    if selection["type"] == "provisioned":
        instance_name = selection["instance_name"]
        instance_info = validate_lakebase_instance(profile_name, instance_name)
        if not instance_info:
            sys.exit(1)
        update_env_file("LAKEBASE_INSTANCE_NAME", instance_name)
        update_env_file("LAKEBASE_AUTOSCALING_PROJECT", "")
        update_env_file("LAKEBASE_AUTOSCALING_BRANCH", "")
        print_success(f"Lakebase provisioned instance '{instance_name}' saved to .env")

        # Set up PostgreSQL connection environment variables
        pg_host = instance_info.get("read_write_dns", "")
        if pg_host:
            update_env_file("PGHOST", pg_host)
            print_success(f"PGHOST set to '{pg_host}'")
        else:
            print_error("Could not get read_write_dns from Lakebase instance")

        update_env_file("PGUSER", username)
        print_success(f"PGUSER set to '{username}'")

        update_env_file("PGDATABASE", "databricks_postgres")
        print_success("PGDATABASE set to 'databricks_postgres'")
    else:
        project = selection["project"]
        branch = selection["branch"]
        branch_info = validate_lakebase_autoscaling(profile_name, project, branch)
        if not branch_info:
            sys.exit(1)
        update_env_file("LAKEBASE_AUTOSCALING_PROJECT", project)
        update_env_file("LAKEBASE_AUTOSCALING_BRANCH", branch)
        update_env_file("LAKEBASE_INSTANCE_NAME", "")

        # Set up PostgreSQL connection environment variables
        pg_host = branch_info.get("host", "")
        if pg_host:
            update_env_file("PGHOST", pg_host)
            print_success(f"PGHOST set to '{pg_host}'")
        else:
            print_error("Could not get endpoint host from Lakebase branch (PGHOST not set)")

        update_env_file("PGUSER", username)
        print_success(f"PGUSER set to '{username}'")

        update_env_file("PGDATABASE", "databricks_postgres")
        print_success("PGDATABASE set to 'databricks_postgres'")

        print_success(
            f"Lakebase autoscaling config saved to .env (project: {project}, branch: {branch})"
        )

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

    # Build replacement block with only the relevant env vars
    if lakebase_config["type"] == "provisioned":
        new_lines = [
            f"{indent}- name: LAKEBASE_INSTANCE_NAME",
            f'{indent}  value: "{lakebase_config["instance_name"]}"',
        ]
    else:
        new_lines = [
            f"{indent}- name: LAKEBASE_AUTOSCALING_PROJECT",
            f'{indent}  value: "{lakebase_config["project"]}"',
            f"{indent}- name: LAKEBASE_AUTOSCALING_BRANCH",
            f'{indent}  value: "{lakebase_config["branch"]}"',
        ]

    final = result[:insert_idx] + new_lines + result[insert_idx:]
    return "\n".join(final) + "\n"


def _replace_lakebase_resource(content: str, lakebase_config: dict) -> str:
    """Update the Lakebase database resource section in databricks.yml.

    For provisioned: uncomments and fills in the database resource block.
    For autoscaling: removes the commented-out provisioned resource block
    (autoscaling postgres resource is added via API after deploy).
    """
    LAKEBASE_COMMENTS = {
        "autoscaling postgres resource must be added via api after deploy",
        "see: .claude/skills/add-tools/examples/lakebase-autoscaling.md",
        "use for provisioned lakebase resource",
    }

    lines = content.splitlines()
    result = []
    i = 0
    found_database = False
    resource_indent = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        bare = stripped.lstrip("#").strip().lower()

        # Skip lakebase-related comment lines in the resources section
        if bare in LAKEBASE_COMMENTS or (bare == "" and stripped == "#"):
            # Bare "#" line between lakebase resource comments — skip it
            # But only if we're inside the lakebase resource area (near other lakebase comments)
            # Check if next or previous lines are lakebase-related
            is_lakebase_area = False
            if bare in LAKEBASE_COMMENTS:
                is_lakebase_area = True
            elif stripped == "#":
                # Check surrounding lines for lakebase context
                for offset in [-1, 1]:
                    neighbor_idx = i + offset
                    if 0 <= neighbor_idx < len(lines):
                        neighbor_bare = lines[neighbor_idx].strip().lstrip("#").strip().lower()
                        if neighbor_bare in LAKEBASE_COMMENTS or "database" in neighbor_bare:
                            is_lakebase_area = True
                            break

            if is_lakebase_area:
                if resource_indent is None:
                    for prev in reversed(result):
                        m = re.match(r"^(\s+)- name:", prev)
                        if m:
                            resource_indent = m.group(1)
                            break
                i += 1
                continue

        # Match the commented-out database resource lines
        if re.match(r"\s*#\s*- name: ['\"]?database['\"]?", stripped):
            found_database = True
            if resource_indent is None:
                for prev in reversed(result):
                    m = re.match(r"^(\s+)- name:", prev)
                    if m:
                        resource_indent = m.group(1)
                        break
            # Skip all subsequent commented lines that are part of this block
            i += 1
            while i < len(lines):
                next_stripped = lines[i].strip()
                if next_stripped.startswith("#") and (
                    "database:" in next_stripped
                    or "instance_name:" in next_stripped
                    or "database_name:" in next_stripped
                    or "permission:" in next_stripped
                ):
                    i += 1
                else:
                    break

            # For provisioned, insert the uncommented resource block
            if lakebase_config["type"] == "provisioned":
                indent = resource_indent or "        "
                instance_name = lakebase_config["instance_name"]
                result.append(f"{indent}- name: 'database'")
                result.append(f"{indent}  database:")
                result.append(f"{indent}    instance_name: '{instance_name}'")
                result.append(f"{indent}    database_name: 'databricks_postgres'")
                result.append(f"{indent}    permission: 'CAN_CONNECT_AND_CREATE'")
            continue

        # Match an uncommented database resource (from a previous provisioned run)
        if re.match(r"\s*- name: ['\"]?database['\"]?", stripped):
            found_database = True
            if resource_indent is None:
                m = re.match(r"^(\s+)- name:", line)
                if m:
                    resource_indent = m.group(1)
            # Skip all subsequent lines that are part of this block
            i += 1
            while i < len(lines):
                next_stripped = lines[i].strip()
                if next_stripped and not next_stripped.startswith("-") and not next_stripped.startswith("#"):
                    i += 1
                else:
                    break

            # For provisioned, insert the updated resource block
            if lakebase_config["type"] == "provisioned":
                indent = resource_indent or "        "
                instance_name = lakebase_config["instance_name"]
                result.append(f"{indent}- name: 'database'")
                result.append(f"{indent}  database:")
                result.append(f"{indent}    instance_name: '{instance_name}'")
                result.append(f"{indent}    database_name: 'databricks_postgres'")
                result.append(f"{indent}    permission: 'CAN_CONNECT_AND_CREATE'")
            continue

        result.append(line)
        i += 1

    # If provisioned but no existing database resource was found (e.g. after autoscaling
    # removed it), append the resource block after the last resource entry
    if lakebase_config["type"] == "provisioned" and not found_database:
        # Find the last "- name:" line in the resources section to insert after
        insert_idx = None
        for idx in range(len(result) - 1, -1, -1):
            if re.match(r"\s+- name:", result[idx]):
                # Find the end of this resource block
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
            instance_name = lakebase_config["instance_name"]
            new_lines = [
                f"{indent}- name: 'database'",
                f"{indent}  database:",
                f"{indent}    instance_name: '{instance_name}'",
                f"{indent}    database_name: 'databricks_postgres'",
                f"{indent}    permission: 'CAN_CONNECT_AND_CREATE'",
            ]
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
        print_success("Updated databricks.yml with Lakebase config")


def update_app_yaml_lakebase(lakebase_config: dict) -> None:
    """Update app.yaml: keep only the relevant Lakebase env vars, remove the others."""
    app_yaml_path = Path("app.yaml")
    if not app_yaml_path.exists():
        return

    content = app_yaml_path.read_text()
    updated = _replace_lakebase_env_vars(content, lakebase_config)
    if updated != content:
        app_yaml_path.write_text(updated)
        print_success("Updated app.yaml with Lakebase config")


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
    print_success("Updated databricks.yml with experiment ID")


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


def select_warehouse_interactive(profile_name: str) -> tuple[str, str]:
    """List warehouses and let user select one. Returns (warehouse_id, warehouse_name)."""
    print_step("SQL ウェアハウスの選択...")
    result = run_command(
        ["databricks", "warehouses", "list", "-p", profile_name, "-o", "json"],
        check=True,
    )
    warehouses = json.loads(result.stdout)
    if not warehouses:
        print_error("利用可能な SQL ウェアハウスがありません。")
        sys.exit(1)

    # Sort: RUNNING first
    warehouses.sort(key=lambda w: (0 if w.get("state") == "RUNNING" else 1, w.get("name", "")))

    print("  利用可能なウェアハウス:")
    for i, w in enumerate(warehouses, 1):
        state = w.get("state", "UNKNOWN")
        name = w.get("name", "?")
        wid = w.get("id", "?")
        marker = " [RUNNING]" if state == "RUNNING" else f" [{state}]"
        print(f"    {i}. {name} ({wid}){marker}")

    while True:
        choice = input(f"\n  番号で選択 [1]: ").strip() or "1"
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
        print("  無効な選択です。もう一度入力してください。")


def create_catalog_schema(token: str, host: str, warehouse_id: str, catalog: str, schema: str):
    """Create catalog and schema via SQL API."""
    print_step("カタログ・スキーマの作成...")

    # バッククォートで囲むことで特殊文字を含むカタログ名にも対応
    data = run_sql_statement(f"CREATE CATALOG IF NOT EXISTS `{catalog}`", token, host, warehouse_id)
    state = data.get("status", {}).get("state", "FAILED")
    if state in ("SUCCEEDED", "CLOSED"):
        print_success(f"カタログ: {catalog}")
    else:
        # 権限不足の場合は既存カタログを使うので警告のみ
        print(f"  カタログ作成: {state}（既に存在するか、権限がない場合はそのまま続行します）")

    data = run_sql_statement(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}`", token, host, warehouse_id)
    state = data.get("status", {}).get("state", "FAILED")
    if state in ("SUCCEEDED", "CLOSED"):
        print_success(f"スキーマ: {catalog}.{schema}")
    else:
        print(f"  スキーマ作成: {state}（既に存在するか、権限がない場合はそのまま続行します）")

    # スキーマの存在を確認
    verify = run_sql_statement(f"DESCRIBE SCHEMA `{catalog}`.`{schema}`", token, host, warehouse_id)
    verify_state = verify.get("status", {}).get("state", "FAILED")
    if verify_state in ("SUCCEEDED", "CLOSED"):
        print_success(f"スキーマ確認OK: {catalog}.{schema}")
    else:
        print_error(f"スキーマ {catalog}.{schema} にアクセスできません。カタログ/スキーマが存在し、権限があることを確認してください。")
        sys.exit(1)


def generate_data(profile_name: str, warehouse_id: str, catalog: str, schema: str):
    """Generate structured data and chunked policy docs."""
    data_dir = Path(__file__).parent.parent.parent / "data"
    env = os.environ.copy()
    env["CATALOG"] = catalog
    env["SCHEMA"] = schema

    # Structured data
    print_step("構造化データの生成（6テーブル）...")
    print("  所要時間: 約5〜10分")
    result = subprocess.run(
        [sys.executable, str(data_dir / "execute_sql.py"),
         "--profile", profile_name, "--warehouse-id", warehouse_id],
        capture_output=True, text=True, env=env,
    )
    if result.returncode == 0:
        print_success("構造化データ生成完了")
    else:
        print_error(f"構造化データ生成に失敗: {result.stderr[-300:]}")
        sys.exit(1)

    # Chunked policy docs
    print_step("ポリシー文書のチャンク生成...")
    result = subprocess.run(
        [sys.executable, str(data_dir / "execute_chunking.py"),
         "--profile", profile_name, "--warehouse-id", warehouse_id],
        capture_output=True, text=True, env=env,
    )
    if result.returncode == 0:
        print_success("ポリシー文書チャンク生成完了")
    else:
        print_error(f"ポリシー文書チャンク生成に失敗: {result.stderr[-300:]}")
        sys.exit(1)


def enable_cdf(token: str, host: str, warehouse_id: str, catalog: str, schema: str):
    """Enable Change Data Feed on policy_docs_chunked table."""
    print_step("Change Data Feed の有効化...")
    stmt = f"ALTER TABLE `{catalog}`.`{schema}`.policy_docs_chunked SET TBLPROPERTIES (delta.enableChangeDataFeed = true)"
    data = run_sql_statement(stmt, token, host, warehouse_id)
    state = data.get("status", {}).get("state", "FAILED")
    if state in ("SUCCEEDED", "CLOSED"):
        print_success("CDF 有効化完了")
    else:
        print(f"  CDF: {state} (既に有効な場合はOK)")


def create_vector_search_index(token: str, host: str, catalog: str, schema: str, vs_endpoint: str) -> str:
    """Create Vector Search index and wait for READY."""
    index_name = f"{catalog}.{schema}.policy_docs_index"
    print_step(f"Vector Search インデックスの作成 ({index_name})...")

    # Check if already exists
    existing = api_get(f"/api/2.0/vector-search/indexes/{index_name}", token, host)
    if "error" not in existing and existing.get("status", {}).get("ready") == True:
        print_success(f"インデックス {index_name} は既に READY です（スキップ）")
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
            print("  インデックスは既に存在します。ステータス確認中...")
        else:
            print_error(f"インデックス作成失敗: {result['error']}")
            print("  手動で Databricks UI から作成してください。")
            return index_name
    else:
        print_success("インデックス作成開始")

    # Poll for READY
    print("  READY 待ち（最大10分）...", end="", flush=True)
    for i in range(40):  # 40 * 15s = 10 min
        time.sleep(15)
        print(".", end="", flush=True)
        status = api_get(f"/api/2.0/vector-search/indexes/{index_name}", token, host)
        if status.get("status", {}).get("ready") == True:
            print()
            print_success(f"インデックス READY: {index_name}")
            return index_name

    print()
    print("  ⚠ タイムアウト。Databricks UI でステータスを確認してください。")
    return index_name


def create_genie_space(token: str, host: str, warehouse_id: str, catalog: str, schema: str) -> str:
    """Create Genie Space with all retail tables."""
    print_step("Genie Space の作成...")
    tables = ["customers", "products", "stores", "transactions", "transaction_items", "payment_history"]
    table_ids = [f"{catalog}.{schema}.{t}" for t in tables]

    body = {
        "title": "フレッシュマート 小売データ",
        "description": "フレッシュマートの小売データに対する自然言語クエリ。顧客、商品、店舗、取引、支払い履歴を検索できます。",
        "warehouse_id": warehouse_id,
        "table_identifiers": table_ids,
    }
    result = api_post("/api/2.0/genie/spaces", token, host, body)

    space_id = result.get("space_id", "")
    if space_id:
        print_success(f"Genie Space 作成完了 (ID: {space_id})")
        return space_id

    # API may return error - Genie Space creation can be complex
    if "error" in result:
        print_error(f"Genie Space の自動作成に失敗: {result['error'][:200]}")
        print("  Databricks UI から手動で作成してください:")
        print(f"  1. {host} を開く")
        print(f"  2. 左メニュー Genie > New Genie Space")
        print(f"  3. 名前: フレッシュマート 小売データ")
        print(f"  4. スキーマ {catalog}.{schema} のテーブルを全て追加")
        print(f"  5. SQL ウェアハウスを選択して Create")
        print(f"  6. URL から Space ID をコピー（URL の最後の部分）")
        space_id = input("\n  Genie Space ID を入力してください: ").strip()
        return space_id

    return space_id


def install_dependencies():
    """Install Python and Node.js dependencies."""
    print_step("依存関係のインストール...")

    # Python
    result = subprocess.run(
        ["uv", "sync"], capture_output=True, text=True,
    )
    if result.returncode == 0:
        print_success("Python 依存関係 (uv sync)")
    else:
        print_error(f"uv sync 失敗: {result.stderr[-200:]}")

    # Node.js
    frontend_dir = Path("e2e-chatbot-app-next")
    if frontend_dir.exists():
        result = subprocess.run(
            ["npm", "install"], capture_output=True, text=True, cwd=frontend_dir,
        )
        if result.returncode == 0:
            print_success("Node.js 依存関係 (npm install)")
        else:
            print("  ⚠ npm install に失敗。手動で実行してください: cd e2e-chatbot-app-next && npm install")
    else:
        print("  ⚠ e2e-chatbot-app-next/ が見つかりません（フロントエンドなし）")


def main():
    parser = argparse.ArgumentParser(
        description="フレッシュマート AI エージェント - クイックスタートセットアップ",
    )
    parser.add_argument("--profile", default=None, help="Databricks CLI プロファイル名")
    parser.add_argument("--host", default=None, help="Databricks ワークスペース URL")
    parser.add_argument("--catalog", default=None, help="Unity Catalog 名")
    parser.add_argument("--schema", default=None, help="スキーマ名")
    parser.add_argument("--warehouse-id", default=None, help="SQL Warehouse ID")
    parser.add_argument("--vs-endpoint", default=None, help="Vector Search エンドポイント名")
    parser.add_argument(
        "--lakebase-provisioned-name",
        help="プロビジョニング済み Lakebase インスタンス名",
    )
    parser.add_argument(
        "--lakebase-autoscaling-project",
        help="Lakebase オートスケーリングプロジェクト名",
    )
    parser.add_argument(
        "--lakebase-autoscaling-branch",
        help="Lakebase オートスケーリングブランチ名",
    )
    args = parser.parse_args()

    try:
        print_header("フレッシュマート AI エージェント - クイックスタートセットアップ")

        # ── Phase 1: 前提条件チェック ──
        print_step("[1/7] 前提条件チェック")
        prereqs = check_prerequisites()
        missing = check_missing_prerequisites(prereqs)
        if missing:
            print_error("不足している前提条件:")
            for item in missing:
                print(f"  • {item}")
            print("\nインストール後に再実行してください。")
            sys.exit(1)
        node_error = check_node_version()
        if node_error:
            print_error(f"Node.js バージョンエラー: {node_error}")
            sys.exit(1)
        print_success("前提条件OK")
        setup_env_file()

        # ── Phase 2: 認証 ──
        print_step("[2/7] Databricks 認証")
        profile_name = setup_databricks_auth(args.profile, args.host)
        username = get_databricks_username(profile_name)
        host = get_databricks_host(profile_name)
        token = get_auth_token(profile_name)
        print_success(f"認証OK: {username}")
        print(f"  ワークスペース: {host}")

        # ── Phase 3: ユーザー入力 ──
        print_step("[3/7] ワークスペース設定")

        # Catalog
        default_catalog = args.catalog or username.split("@")[0].replace(".", "_")
        catalog = input(f"  カタログ名 [{default_catalog}]: ").strip() or default_catalog

        # Schema
        default_schema = args.schema or "retail_agent"
        schema = input(f"  スキーマ名 [{default_schema}]: ").strip() or default_schema

        # Warehouse
        if args.warehouse_id:
            warehouse_id = args.warehouse_id
            print_success(f"Warehouse ID: {warehouse_id}")
        else:
            warehouse_id, _ = select_warehouse_interactive(profile_name)

        # VS Endpoint
        if args.vs_endpoint:
            vs_endpoint = args.vs_endpoint
        else:
            vs_endpoint = input("  Vector Search エンドポイント名（既存）: ").strip()
        if vs_endpoint:
            # Verify endpoint exists
            ep_status = api_get(f"/api/2.0/vector-search/endpoints/{vs_endpoint}", token, host)
            if "error" not in ep_status:
                ep_state = ep_status.get("endpoint_status", {}).get("state", "UNKNOWN")
                print_success(f"VS エンドポイント: {vs_endpoint} ({ep_state})")
            else:
                print(f"  ⚠ エンドポイント {vs_endpoint} が見つかりません。手動で作成してください。")

        # ── Phase 4: リソース作成 ──
        print_step("[4/7] リソース作成")

        # 4-1: Catalog & Schema
        create_catalog_schema(token, host, warehouse_id, catalog, schema)

        # 4-2 & 4-3: Data generation
        generate_data(profile_name, warehouse_id, catalog, schema)

        # 4-4: CDF
        enable_cdf(token, host, warehouse_id, catalog, schema)

        # 4-5: Vector Search Index
        vs_index = ""
        if vs_endpoint:
            vs_index = create_vector_search_index(token, host, catalog, schema, vs_endpoint)
        else:
            vs_index = f"{catalog}.{schema}.policy_docs_index"
            print("  ⚠ VS エンドポイント未指定。インデックスは手動で作成してください。")

        # 4-6: Genie Space
        genie_space_id = create_genie_space(token, host, warehouse_id, catalog, schema)

        # 4-7: Lakebase
        lakebase_config = None
        lakebase_required = (
            args.lakebase_provisioned_name
            or (args.lakebase_autoscaling_project and args.lakebase_autoscaling_branch)
            or check_lakebase_required()
        )
        if lakebase_required:
            lakebase_config = setup_lakebase(
                profile_name, username,
                provisioned_name=args.lakebase_provisioned_name,
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
        print_step("[5/7] 環境設定 (.env)")
        update_env_file("DATABRICKS_HOST", host)
        update_env_file("MLFLOW_EXPERIMENT_ID", monitoring_id)
        update_env_file("MLFLOW_EVAL_EXPERIMENT_ID", eval_id)
        update_env_file("GENIE_SPACE_ID", genie_space_id)
        update_env_file("VECTOR_SEARCH_INDEX", vs_index)
        update_databricks_yml_experiment(monitoring_id)
        print_success(".env 更新完了")

        # Delta Table tracing
        print()
        print("  トレース送信先の選択:")
        print("    デフォルト: MLflow Experiment（すぐに使える）")
        print("    オプション: Unity Catalog Delta Table（SQL クエリ可能、長期保持）")
        tracing_dest = ""
        use_delta = input("\n  Unity Catalog Delta Table に送信しますか？ (y/N): ").strip().lower()
        if use_delta == "y":
            tracing_dest = f"{catalog}.{schema}"
            update_env_file("MLFLOW_TRACING_DESTINATION", tracing_dest)
            print_success(f"トレース送信先: Unity Catalog ({tracing_dest})")
        else:
            print_success("トレース送信先: MLflow Experiment（デフォルト）")

        # ── Phase 6: 依存関係 ──
        print_step("[6/7] 依存関係のインストール")
        install_dependencies()

        # ── Phase 7: サマリー ──
        print_header("セットアップ完了！")
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

        if host:
            summary += f"\n  {host}/ml/experiments/{monitoring_id}"

        if tracing_dest:
            summary += f"\n\n✓ トレース送信先: Unity Catalog ({tracing_dest})"
            summary += "\n  ⚠ トレーステーブルの初期作成が必要です（下記参照）"
        else:
            summary += "\n\n✓ トレース送信先: MLflow Experiment（デフォルト）"

        if lakebase_config:
            if lakebase_config["type"] == "provisioned":
                summary += f"\n\n✓ Lakebase: {lakebase_config['instance_name']}"
            else:
                summary += f"\n\n✓ Lakebase: {lakebase_config['project']} (branch: {lakebase_config['branch']})"

        if not tracing_dest:
            summary += "\n\n次のステップ: uv run start-app\n"
        print(summary)

        # Delta Table の手順表示（選択した場合のみ）
        if tracing_dest and "." in tracing_dest:
            _cat, _sch = tracing_dest.split(".", 1)
            print("=" * 60)
            print("⚠ Unity Catalog トレーステーブルの初期作成が必要です")
            print("=" * 60)
            print()
            print("トレーステーブルは Databricks ノートブック上でのみ作成可能です。")
            print("ローカルからは実行できません。")
            print()
            print("【手順】")
            print("1. Databricks ワークスペースでノートブックを開く")
            print("2. SQL Warehouse ID を確認する：")
            print(f"   既に選択済み: {warehouse_id}")
            print("3. 以下のコードをノートブックで実行する：")
            print()
            print("```python")
            print("import os")
            print(f'os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = "{warehouse_id}"')
            print()
            print("import mlflow")
            print("from mlflow.entities import UCSchemaLocation")
            print()
            print("mlflow.tracing.set_experiment_trace_location(")
            print(f'    location=UCSchemaLocation(catalog_name="{_cat}", schema_name="{_sch}"),')
            print(f'    experiment_id="{monitoring_id}",')
            print(")")
            print("```")
            print()
            print("実行後、以下の3つの Delta Table が自動作成されます：")
            print(f"  - {tracing_dest}.mlflow_experiment_trace_otel_spans")
            print(f"  - {tracing_dest}.mlflow_experiment_trace_otel_logs")
            print(f"  - {tracing_dest}.mlflow_experiment_trace_otel_metrics")
            print()
            print("テーブル作成後に 'uv run start-app' を実行してください。")
            print("=" * 60)

    except KeyboardInterrupt:
        print("\n\nセットアップが中断されました。")
        sys.exit(1)
    except Exception as e:
        print_error(f"セットアップ中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
