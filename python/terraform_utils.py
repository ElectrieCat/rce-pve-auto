import subprocess
import os
from python.parser import load_auth_config


def _prepare_env():
    """
    Builds the environment dict for Terraform subprocesses.

    We start from a copy of the current process environment so that
    system-level variables (PATH, HOME, etc.) are inherited — without
    these, the 'terraform' binary cannot be located or run correctly.
    Auth credentials and cache settings are then added on top.
    """
    auth = load_auth_config()
    if not auth:
        return None

    env = os.environ.copy()

    env["PROXMOX_VE_ENDPOINT"] = auth.get("endpoint", "")
    env["PROXMOX_VE_INSECURE"] = str(auth.get("insecure", True)).lower()

    api_token = auth.get("api_token")
    if api_token:
        env["PROXMOX_VE_API_TOKEN"] = api_token
    else:
        env["PROXMOX_VE_USERNAME"] = auth.get("username", "")
        env["PROXMOX_VE_PASSWORD"] = auth.get("password", "")

    cache_dir = os.path.abspath("terraform/providers_cache")
    os.makedirs(cache_dir, exist_ok=True)
    env["TF_PLUGIN_CACHE_DIR"] = cache_dir

    return env


def _handle_tf_error(e, directory):
    """Analyzes a CalledProcessError from Terraform and prints a useful message."""
    print(f"[ERROR] Terraform failed in {directory}")
    stdout = (e.stdout or b"").decode('utf-8')
    stderr = (e.stderr or b"").decode('utf-8')
    error_msg = stderr + stdout

    if "Permission check failed" in error_msg and "API token" in error_msg:
        print("\n" + "!" * 60)
        print("[HINT] Proxmox API Tokens have limited permissions (e.g. cannot change passwords).")
        print("Please switch to 'username' and 'password' in 'configs/auth.yaml'")
        print("to perform this operation (root@pam is recommended).")
        print("!" * 60 + "\n")
    else:
        if stdout:
            print(f"STDOUT: {stdout}")
        if stderr:
            print(f"STDERR: {stderr}")


def _run_terraform_command(directory, *tf_args, capture_init=True):
    """
    Core Terraform executor. Always runs 'terraform init' first, then
    runs 'terraform' with whatever arguments are passed in tf_args.

    Args:
        directory:     Working directory for the Terraform run.
        *tf_args:      Arguments passed directly to the terraform binary
                       after 'init'. E.g. ("apply", "-auto-approve") or
                       ("plan", "-destroy"). This makes it easy to pass
                       any custom arguments when needed.
        capture_init:  If True, suppresses init output (default).
                       Set to False to see full init output.

    Returns:
        True on success, False on failure.
    """
    env = _prepare_env()
    if env is None:
        return False

    try:
        subprocess.run(
            ["terraform", "init", "-input=false"],
            cwd=directory,
            check=True,
            capture_output=capture_init,
            env=env
        )
        subprocess.run(
            ["terraform", *tf_args],
            cwd=directory,
            check=True,
            env=env
        )
        return True
    except subprocess.CalledProcessError as e:
        _handle_tf_error(e, directory)
        return False


def run_terraform_apply(directory):
    """Runs terraform init + apply."""
    print(f"[*] Running Terraform Apply in: {directory}")
    result = _run_terraform_command(
        directory,
        "apply", "-auto-approve", "-input=false", "-parallelism=4"
    )
    if result:
        print(f"[SUCCESS] Terraform applied in {directory}")
    return result


def run_terraform_destroy(directory):
    """Runs terraform init + destroy."""
    print(f"[*] DESTROYING resources in: {directory}")
    result = _run_terraform_command(
        directory,
        "destroy", "-auto-approve", "-input=false", "-parallelism=1"
    )
    if result:
        print(f"[SUCCESS] Resources destroyed in {directory}")
    return result


def run_terraform_plan(directory):
    """Runs terraform init + plan."""
    print(f"\n{'=' * 60}\n[*] PLANNING changes in: {directory}\n{'=' * 60}")
    return _run_terraform_command(directory, "plan", "-input=false")


def run_terraform_destroy_plan(directory):
    """Runs terraform init + plan -destroy."""
    print(f"\n{'!' * 60}\n[*] DESTROY PLAN for: {directory}\n{'!' * 60}")
    return _run_terraform_command(directory, "plan", "-destroy", "-input=false")


def run_terraform_custom(directory, *tf_args):
    """
    Runs terraform init followed by any custom arguments the caller provides.
    Useful for advanced or one-off operations not covered by the standard wrappers.

    Example:
        run_terraform_custom(my_dir, "state", "list")
        run_terraform_custom(my_dir, "import", "proxmox_...", "resource_id")
    """
    print(f"[*] Running Terraform with custom args {list(tf_args)} in: {directory}")
    return _run_terraform_command(directory, *tf_args)