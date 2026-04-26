import subprocess
import os
from python.parser import load_auth_config


def _prepare_env():
    """Internal helper to prepare environment variables for Terraform."""
    auth = load_auth_config()
    if not auth:
        return None

    env = os.environ.copy()
    env["PROXMOX_VE_ENDPOINT"] = auth.get("endpoint", "")
    env["PROXMOX_VE_INSECURE"] = str(auth.get("insecure", True)).lower()

    # Priority: API Token, then Password
    api_token = auth.get("api_token")
    if api_token:
        env["PROXMOX_VE_API_TOKEN"] = api_token
    else:
        env["PROXMOX_VE_USERNAME"] = auth.get("username", "")
        env["PROXMOX_VE_PASSWORD"] = auth.get("password", "")

    # Set cache directory for providers
    cache_dir = os.path.abspath("terraform/providers_cache")
    os.makedirs(cache_dir, exist_ok=True)
    env["TF_PLUGIN_CACHE_DIR"] = cache_dir

    return env


def _handle_tf_error(e, directory):
    """Internal helper to analyze and print Terraform errors."""
    print(f"[ERROR] Terraform failed in {directory}")
    error_msg = (e.stderr or b"").decode('utf-8') + (e.stdout or b"").decode('utf-8')

    if "Permission check failed" in error_msg and "API token" in error_msg:
        print("\n" + "!" * 60)
        print("[HINT] Proxmox API Tokens have limited permissions (e.g. cannot change passwords).")
        print("Please switch to 'username' and 'password' in 'configs/auth.yaml'")
        print("to perform this operation (root@pam is recommended).")
        print("!" * 60 + "\n")
    else:
        if e.stdout: print(f"STDOUT: {e.stdout.decode('utf-8')}")
        if e.stderr: print(f"STDERR: {e.stderr.decode('utf-8')}")


def run_terraform(directory):
    """Runs terraform init and apply."""
    env = _prepare_env()
    if env is None: return False

    print(f"[*] Running Terraform Apply in: {directory}")
    try:
        # Init
        subprocess.run(["terraform", "init", "-input=false"], cwd=directory, check=True, capture_output=True, env=env)
        # Apply
        subprocess.run(
            ["terraform", "apply", "-auto-approve", "-input=false", "-parallelism=1"],
            cwd=directory, check=True, env=env
        )
        print(f"[SUCCESS] Terraform applied in {directory}")
        return True
    except subprocess.CalledProcessError as e:
        _handle_tf_error(e, directory)
        return False


def run_terraform_destroy(directory):
    """Runs terraform destroy."""
    env = _prepare_env()
    if env is None: return False

    print(f"[*] DESTROYING resources in: {directory}")
    try:
        # Init
        subprocess.run(["terraform", "init", "-input=false"], cwd=directory, check=True, capture_output=True, env=env)
        # Destroy
        subprocess.run(
            ["terraform", "destroy", "-auto-approve", "-input=false", "-parallelism=1"],
            cwd=directory, check=True, env=env
        )
        print(f"[SUCCESS] Resources destroyed in {directory}")
        return True
    except subprocess.CalledProcessError as e:
        _handle_tf_error(e, directory)
        return False


def run_terraform_plan(directory):
    """Runs terraform init and plan with real-time output."""
    env = _prepare_env()
    if env is None: return False

    print(f"\n{'=' * 60}\n[*] PLANNING changes in: {directory}\n{'=' * 60}")
    try:
        subprocess.run(["terraform", "init", "-input=false"], cwd=directory, check=True, capture_output=True, env=env)
        subprocess.run(["terraform", "plan", "-input=false"], cwd=directory, check=True, env=env)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Plan failed in {directory}")
        return False


def run_terraform_destroy_plan(directory):
    """Runs terraform plan -destroy to show what will be removed."""
    env = _prepare_env()
    if env is None: return False

    print(f"\n{'!' * 60}\n[*] DESTROY PLAN for: {directory}\n{'!' * 60}")
    try:
        subprocess.run(["terraform", "init", "-input=false"], cwd=directory, check=True, capture_output=True, env=env)
        subprocess.run(["terraform", "plan", "-destroy", "-input=false"], cwd=directory, check=True, env=env)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Destroy plan failed in {directory}")
        return False