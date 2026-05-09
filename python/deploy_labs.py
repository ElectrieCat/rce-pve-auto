import os
import json
import shutil
from python.parser import load_labs_matrix, load_lab_config
from python.terraform_utils import run_terraform_apply, run_terraform_plan, run_terraform_destroy, run_terraform_destroy_plan


def get_user_lab_status(lab_config: dict, group_name: str, user_name: str):
    """
    Resolves the effective (permit, managed, destroy) flags for a user in a lab.
    Hierarchy: group-level -> member-level (member overrides group).

    Returns (permit=True, managed=False, destroy=False) if the group is not
    explicitly listed in the lab config — managed=False means the lab will not
    be deployed for this group at all, which is the safe default when a group
    has not been explicitly configured for a lab.
    """
    # Group not listed in this lab config at all — do not deploy for them.
    group_settings = lab_config.get('groups', {}).get(group_name)
    if group_settings is None:
        return True, False, False

    permit  = group_settings.get('permit',  True)
    managed = group_settings.get('managed', True)
    destroy = group_settings.get('destroy', False)

    for member in group_settings.get('members', []):
        if member.get('name') == user_name:
            permit  = member.get('permit',  permit)
            managed = member.get('managed', managed)
            destroy = member.get('destroy', destroy)
            break

    return permit, managed, destroy


def deploy_lab(lab_name: str, users_config: dict, plan_only: bool = False):
    """Deploys a lab for all eligible users across all groups."""

    # 1. Load lab matrix entry
    labs_matrix = load_labs_matrix()
    lab_info = labs_matrix.get(lab_name)
    if not lab_info:
        print(f"[ERROR] Lab '{lab_name}' not found in labs.yaml")
        return

    lab_id = lab_info.get('internal-id')
    if lab_id is None:
        print(f"[ERROR] Lab '{lab_name}' has no 'internal-id' in labs.yaml.")
        return

    # 2. Load and validate lab config (main.yaml)
    lab_full_config = load_lab_config(lab_name)
    if not lab_full_config:
        print(f"[ERROR] Lab config (main.yaml) for '{lab_name}' is missing or empty. Aborting.")
        return

    pve_locals_config = lab_full_config.get('pve-locals')
    if not pve_locals_config:
        print(f"[ERROR] 'pve-locals' section is missing in main.yaml for lab '{lab_name}'.")
        return

    storage = pve_locals_config.get('storage')
    node = pve_locals_config.get('node')

    if not storage:
        print(f"[ERROR] 'storage' is not defined in pve-locals for lab '{lab_name}'. Aborting.")
        return
    if not node:
        print(f"[ERROR] 'node' is not defined in pve-locals for lab '{lab_name}'. Aborting.")
        return

    pve_locals = {"storage": storage, "node": node}
    nets_config = lab_full_config.get('nets', {})

    snap_config = lab_full_config.get('snapshots', {})
    snap_create = snap_config.get('create', False)
    snap_ram = bool(snap_config.get('include-ram', False))   # enforce bool here, at parse time
    snap_name = snap_config.get('name')
    snap_description = snap_config.get('description', "Auto Snapshot")

    if snap_create and not snap_name:
        print(f"[ERROR] Snapshot 'name' is required when 'create: true' in lab '{lab_name}'.")
        return

    # 3. User loop
    if not users_config:
        print("[ERROR] No users found in configuration. Nothing to deploy.")
        return

    print(f"[*] Deploying lab '{lab_name}'...")

    for group_name, group_info in users_config.items():
        for user_name, user_data in group_info['members'].items():
            permit, managed, destroy = get_user_lab_status(lab_info, group_name, user_name)

            if not managed:
                print(f"[SKIP] Lab '{lab_name}' for '{user_name}' in group '{group_name}': managed=false in labs.yaml.")
                continue
            if destroy:
                print(f"[SKIP] Lab '{lab_name}' for '{user_name}' in group '{group_name}': marked for destroy. Use 'destroy-lab'.")
                continue

            user_idx = user_data.get('internal_id')
            if user_idx is None:
                print(f"[ERROR] User '{user_name}' has no 'internal-id' in users.yaml. Skipping.")
                continue

            user_dir = os.path.join("groups", group_name, "users", user_name)
            lab_dir = os.path.join(user_dir, "labs", lab_name)
            os.makedirs(lab_dir, exist_ok=True)

            # 4. Build network config
            tf_networks = {}
            for i, (net_key, net_params) in enumerate(nets_config.items(), 1):
                real_bridge_name = f"u{user_idx}l{lab_id}n{i}"
                vlan_aware = net_params.get('vlan-aware', False)
                tf_networks[net_key] = {
                    "real_name": real_bridge_name,
                    "type": net_params.get('type', 'local-bridge'),
                    "autostart": net_params.get('autostart', True),
                    "vlan_aware": vlan_aware,
                    # vids is only passed when vlan_aware is true; empty string otherwise
                    # so the Terraform variable always has a value to receive.
                    "vids": net_params.get('vlans', "") if vlan_aware else "",
                    "mtu": net_params.get('mtu', 1500),
                    "bridge_ports": net_params.get('bridge-ports', ""),
                    "comment": net_params.get('comment') or f"{group_name}_{user_name}_{lab_name}_{net_key}",
                    "ipv4_cidr": net_params.get('ipv4-cidr'),
                    "ipv4_gw": net_params.get('ipv4-gw'),
                    "ipv6_cidr": net_params.get('ipv6-cidr'),
                    "ipv6_gw": net_params.get('ipv6-gw'),
                }

            lab_tfvars = {
                "user_name": user_name,
                "group_name": group_name,
                "lab_name": lab_name,
                "pool_id": f"{group_name}_{user_name}_{lab_name}",
                "permit": permit,
                "networks": tf_networks,
                "pve_locals": pve_locals,
            }

            with open(os.path.join(lab_dir, "terraform.tfvars.json"), 'w') as f:
                json.dump(lab_tfvars, f, indent=4)

            # 5. Copy .tf files from lab config directory
            lab_config_dir = os.path.join("configs", "labs", lab_name)
            tf_files_found = False
            if os.path.exists(lab_config_dir):
                for file_name in os.listdir(lab_config_dir):
                    if file_name.endswith(".tf"):
                        shutil.copy(
                            os.path.join(lab_config_dir, file_name),
                            os.path.join(lab_dir, file_name)
                        )
                        tf_files_found = True

            if not tf_files_found:
                print(f"[WARNING] No .tf files found in '{lab_config_dir}'. Skipping '{user_name}'.")
                continue

            # 6. Run Terraform
            if plan_only:
                run_terraform_plan(lab_dir)
            else:
                print(f"[*] Deploying lab '{lab_name}' for '{user_name}'...")
                if run_terraform_apply(lab_dir) and snap_create:
                    from python.snapshots import create_initial_snapshot
                    create_initial_snapshot(
                        lab_dir=lab_dir,
                        node_name=node,
                        snap_name=snap_name,
                        include_ram=snap_ram,
                        description=snap_description,
                    )


def terraform_run_lab(
    lab_name: str,
    users_config: dict,
    tf_args: list,
    filter_group: str = None,
    filter_user: str = None,
    force_managed: bool = False,
):
    """
    Runs custom Terraform arguments against lab directories for the given
    lab_name, optionally scoped to a specific group and/or user.

    Unmanaged labs are skipped unless force_managed=True is passed, in which
    case the managed flag is ignored and the command runs regardless.
    This is intentionally only available via terraform-run, not deploy/destroy.

    Args:
        lab_name:      Name of the lab as defined in labs.yaml.
        users_config:  Parsed users config dict.
        tf_args:       Terraform arguments to pass after 'init'.
        filter_group:  If set, only process users in this group.
        filter_user:   If set, only process this specific user (requires filter_group).
        force_managed: If True, run even on unmanaged lab directories.
    """
    from python.terraform_utils import run_terraform_custom

    labs_matrix = load_labs_matrix()
    lab_info = labs_matrix.get(lab_name)
    if not lab_info:
        print(f"[ERROR] Lab '{lab_name}' not found in labs.yaml.")
        return

    ran_any = False

    for group_name, group_info in users_config.items():
        if filter_group and group_name != filter_group:
            continue

        for user_name in group_info['members'].keys():
            if filter_user and user_name != filter_user:
                continue

            _permit, managed, _destroy = get_user_lab_status(lab_info, group_name, user_name)

            if not managed:
                if force_managed:
                    print(
                        f"[WARN] Lab '{lab_name}' for '{user_name}' is unmanaged — "
                        f"running anyway because --force-managed was specified."
                    )
                else:
                    print(
                        f"[SKIP] Lab '{lab_name}' for '{user_name}' is unmanaged. "
                        f"Use --force-managed to override, or run terraform manually in the directory."
                    )
                    continue

            lab_dir = os.path.join("groups", group_name, "users", user_name, "labs", lab_name)
            if not os.path.exists(lab_dir):
                print(f"[SKIP] Lab directory not found for '{user_name}': {lab_dir}")
                continue

            print(f"[*] Running terraform {' '.join(tf_args)} for '{user_name}' in {lab_dir}...")
            run_terraform_custom(lab_dir, *tf_args)
            ran_any = True

    if not ran_any:
        print(f"[*] No eligible lab directories found for '{lab_name}' with the given filters.")


def destroy_lab(lab_name: str, users_config: dict, plan_only: bool = False) -> bool:
    """
    Destroys labs that are marked with destroy: true for each user.

    In plan_only mode, shows what would be destroyed without making any changes.
    The directory check is skipped in plan mode so the operator sees the full
    picture from config even if the lab has never been deployed.

    Returns True if any labs are scheduled for destruction (whether or not
    plan_only is set), so the CLI knows whether to ask for confirmation.
    """
    labs_matrix = load_labs_matrix()
    lab_info = labs_matrix.get(lab_name)
    if not lab_info:
        print(f"[ERROR] Lab '{lab_name}' not found in labs.yaml")
        return False

    # Collect per-group skip summaries to avoid one line per user.
    # Structure: { group_name: { "unmanaged": [users], "kept": [users] } }
    skips: dict = {}
    found_any = False

    for group_name, group_info in users_config.items():
        for user_name in group_info['members'].keys():
            permit, managed, destroy = get_user_lab_status(lab_info, group_name, user_name)
            lab_dir = os.path.join("groups", group_name, "users", user_name, "labs", lab_name)

            # In apply mode, skip users whose lab directory doesn't exist yet.
            # In plan mode, always evaluate so the operator sees the full config picture.
            if not plan_only and not os.path.exists(lab_dir):
                continue

            if not managed:
                skips.setdefault(group_name, {"unmanaged": [], "kept": []})["unmanaged"].append(user_name)
                continue

            if not destroy:
                skips.setdefault(group_name, {"unmanaged": [], "kept": []})["kept"].append(user_name)
                continue

            found_any = True
            if plan_only:
                if os.path.exists(lab_dir):
                    print(f"[PLAN] Would destroy lab '{lab_name}' for '{user_name}' ({group_name}):")
                    run_terraform_destroy_plan(lab_dir)
                else:
                    print(
                        f"[PLAN] Would destroy lab '{lab_name}' for '{user_name}' ({group_name}) "
                        f"— directory does not exist yet, nothing to destroy."
                    )
            else:
                print(f"[!] DESTROYING lab '{lab_name}' for '{user_name}'...")
                if run_terraform_destroy(lab_dir):
                    shutil.rmtree(lab_dir)
                    print(f"[SUCCESS] Lab directory removed for '{user_name}'.")
                else:
                    print(f"[ERROR] Terraform destroy failed for '{user_name}'. Directory preserved.")

    # Print one summary line per group for skipped users
    for group_name, buckets in skips.items():
        if buckets["unmanaged"]:
            users = ", ".join(buckets["unmanaged"])
            print(f"[SKIP] {group_name}: {users} — unmanaged, manual action required.")
        if buckets["kept"]:
            users = ", ".join(buckets["kept"])
            print(f"[KEEP] {group_name}: {users} — destroy=false, protected.")

    if not found_any and not skips:
        print(f"[*] No labs found for '{lab_name}' matching destroy=true.")

    return found_any