import json
import subprocess
from urllib.parse import urlparse
from proxmoxer import ProxmoxAPI
from python.parser import load_auth_config


def get_proxmox_api():
    """
    Initializes and returns a ProxmoxAPI client using credentials from auth.yaml.
    Returns None if the config is missing or credentials are invalid.
    """
    auth = load_auth_config()
    if not auth:
        print("[ERROR] Auth config not found or invalid.")
        return None

    endpoint = auth.get("endpoint", "")

    # Ensure the endpoint has a scheme so urlparse can split it correctly
    if "://" not in endpoint:
        endpoint = "https://" + endpoint

    parsed_url = urlparse(endpoint)
    host = parsed_url.hostname
    port = parsed_url.port or 443

    if not host:
        print("[ERROR] PVE endpoint not specified or invalid in auth config.")
        return None

    insecure = auth.get("insecure", True)
    api_token = auth.get("api_token")
    username = auth.get("username")
    password = auth.get("password")

    try:
        if api_token:
            # Expected format: user@realm!token_name=token_value
            user_and_name, token_value = api_token.split('=', 1)
            user, token_name = user_and_name.split('!')

            proxmox = ProxmoxAPI(
                host,
                port=port,
                user=user,
                token_name=token_name,
                token_value=token_value,
                verify_ssl=not insecure
            )
        elif username and password:
            proxmox = ProxmoxAPI(
                host,
                port=port,
                user=username,
                password=password,
                verify_ssl=not insecure
            )
        else:
            print("[ERROR] Neither API token nor username/password found in auth config.")
            return None

        return proxmox
    except Exception as e:
        print(f"[ERROR] Failed to initialize Proxmox API: {e}")
        return None


def get_terraform_vm_ids(lab_dir):
    """
    Runs 'terraform output -json' in lab_dir and extracts the list of VM IDs
    from the 'vm_snapshot_ids' output variable.
    Returns a list of VM IDs, or an empty list if none are found.
    """
    try:
        cmd = ["terraform", f"-chdir={lab_dir}", "output", "-json"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        outputs = json.loads(result.stdout)

        if "vm_snapshot_ids" not in outputs:
            print(f"[WARNING] No 'vm_snapshot_ids' output found in {lab_dir}. Cannot create snapshots.")
            return []

        vm_data = outputs["vm_snapshot_ids"].get("value")

        if isinstance(vm_data, list):
            return vm_data
        if isinstance(vm_data, dict):
            return list(vm_data.values())
        if isinstance(vm_data, (int, str)):
            return [vm_data]

        print(f"[WARNING] Unexpected format for 'vm_snapshot_ids' in {lab_dir}.")
        return []

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to run terraform output in {lab_dir}: {e}")
        return []
    except (json.JSONDecodeError, KeyError) as e:
        print(f"[ERROR] Failed to parse terraform output from {lab_dir}: {e}")
        return []


def create_initial_snapshot(
    lab_dir: str,
    node_name: str,
    snap_name: str,
    include_ram: bool,
    description: str = "Auto Snapshot"
):
    """
    Creates a snapshot for every VM listed in the lab's terraform output.

    Args:
        lab_dir:     Path to the lab's terraform directory.
        node_name:   Proxmox node where the VMs reside.
        snap_name:   Name of the snapshot to create.
        include_ram: Whether to include RAM state in the snapshot.
                     Must be a bool — enforced by the caller (parser).
        description: Human-readable description for the snapshot.
    """
    vm_ids = get_terraform_vm_ids(lab_dir)
    if not vm_ids:
        return

    proxmox = get_proxmox_api()
    if not proxmox:
        return

    for vm_id in vm_ids:
        try:
            existing = proxmox.nodes(node_name).qemu(vm_id).snapshot.get()
            existing_names = [s['name'] for s in existing]

            if snap_name in existing_names:
                print(f"[SKIP] Snapshot '{snap_name}' already exists for VM {vm_id}")
                continue

            print(
                f"[*] Creating snapshot '{snap_name}' for VM {vm_id} "
                f"(RAM included: {include_ram}). Please wait..."
            )
            proxmox.nodes(node_name).qemu(vm_id).snapshot.post(
                snapname=snap_name,
                description=description,
                vmstate=1 if include_ram else 0
            )
            print(f"[SUCCESS] Snapshot created for VM {vm_id}")

        except Exception as e:
            print(f"[ERROR] Could not create snapshot for VM {vm_id}: {e}")