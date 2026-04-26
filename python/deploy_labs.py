import os
import json
import shutil
from python.parser import load_labs_matrix, load_lab_config
from python.terraform_utils import run_terraform, run_terraform_plan, run_terraform_destroy, run_terraform_destroy_plan


def get_user_lab_status(lab_config, group_name, user_name):
    """Hierarchy: Default -> Group -> Member (overrides)"""
    permit, managed, destroy = True, True, False
    group_settings = lab_config.get('groups', {}).get(group_name, {})
    if group_settings:
        permit = group_settings.get('permit', True)
        managed = group_settings.get('managed', True)
        destroy = group_settings.get('destroy', False)
        for member in group_settings.get('members', []):
            if member.get('name') == user_name:
                permit = member.get('permit', permit)
                managed = member.get('managed', managed)
                destroy = member.get('destroy', destroy)
                break
    return permit, managed, destroy


def deploy_lab(lab_name, users_config, plan_only=False):
    # 1. Load Matrix
    labs_matrix = load_labs_matrix()
    lab_info = labs_matrix.get(lab_name)
    if not lab_info:
        print(f"[ERROR] Lab '{lab_name}' not found in labs.yaml")
        return

    lab_id = lab_info.get('internal-id')
    if lab_id is None:
        print(f"[ERROR] Lab '{lab_name}' has no 'internal-id' in labs.yaml!")
        return

    # 2. Load and Validate Lab Config (main.yaml)
    lab_full_config = load_lab_config(lab_name)
    if not lab_full_config:
        return

    # --- STRICT VALIDATION FOR LOCALS ---
    pve_locals_config = lab_full_config.get('pve-locals')
    if not pve_locals_config:
        print(f"[ERROR] 'pve-locals' section is missing in main.yaml for lab '{lab_name}'")
        return

    storage = pve_locals_config.get('storage')
    node = pve_locals_config.get('node')

    if not storage:
        print(f"[ERROR] 'storage' is not defined in pve-locals for lab '{lab_name}'. Action aborted for safety.")
        return
    if not node:
        print(f"[ERROR] 'node' is not defined in pve-locals for lab '{lab_name}'. Action aborted for safety.")
        return

    pve_locals = {"storage": storage, "node": node}
    nets_config = lab_full_config.get('nets', {})

    snap_config = lab_full_config.get('snapshots', {})
    snap_create = snap_config.get('create', False)
    snap_ram = snap_config.get('include-ram', False)
    snap_name = snap_config.get('name')
    snap_description = snap_config.get('description')

    # validate the snapshots configs
    if snap_create and not snap_config.get('name'):
        print(f"[ERROR] You have to specify 'name' for snapshot in lab '{lab_name}'")
        return


    # 3. User Loop
    for group_name, group_info in users_config.items():
        for user_name, user_data in group_info['members'].items():
            permit, managed, destroy = get_user_lab_status(lab_info, group_name, user_name)

            if not managed or destroy:
                if destroy: print(
                    f"[SKIP] Lab {lab_name} for {user_name} is marked for destroy. Use 'destroy-lab' command.")
                continue

            user_idx = user_data.get('internal_id')
            if user_idx is None:
                print(f"[ERROR] User '{user_name}' has no 'internal-id' in users.yaml!")
                continue

            user_dir = os.path.join("groups", group_name, "users", user_name)
            lab_dir = os.path.join(user_dir, "labs", lab_name)
            os.makedirs(lab_dir, exist_ok=True)

            # 4. Generate Network Config (FIX: Underscores for TF compatibility)
            tf_networks = {}
            for i, (net_key, net_params) in enumerate(nets_config.items(), 1):
                real_bridge_name = f"u{user_idx}l{lab_id}n{i}"
                tf_networks[net_key] = {
                    "real_name": real_bridge_name,
                    "type": net_params.get('type', 'local-bridge'),
                    "autostart": net_params.get('autostart', True),
                    # not yet possible due to bpg limitations
                    #"vlan_aware": net_params.get('vlan-aware', False),  # Changed to _
                    #"vlan_id": net_params.get('vlans', ""),
                    "mtu": net_params.get('mtu', 1500),
                    "bridge_ports": net_params.get('bridge-ports', ""),  # Changed to _
                    "comment": net_params.get('comment') or f"{group_name}_{user_name}_{lab_name}_{net_key}",
                    "ipv4_cidr": net_params.get('ipv4-cidr'),  # Changed to _
                    "ipv4_gw": net_params.get('ipv4-gw'),  # Changed to _
                    "ipv6_cidr": net_params.get('ipv6-cidr'),  # Changed to _
                    "ipv6_gw": net_params.get('ipv6-gw')  # Changed to _
                }

            lab_tfvars = {
                "user_name": user_name,
                "group_name": group_name,
                "lab_name": lab_name,
                "pool_id": f"{group_name}_{user_name}_{lab_name}",
                "permit": permit,
                "networks": tf_networks,
                "pve_locals": pve_locals
            }

            with open(os.path.join(lab_dir, "terraform.tfvars.json"), 'w') as f:
                json.dump(lab_tfvars, f, indent=4)

            # 5. Copy .tf files
            lab_config_dir = os.path.join("configs", "labs", lab_name)
            tf_files_found = False
            if os.path.exists(lab_config_dir):
                for file_name in os.listdir(lab_config_dir):
                    if file_name.endswith(".tf"):
                        shutil.copy(os.path.join(lab_config_dir, file_name), os.path.join(lab_dir, file_name))
                        tf_files_found = True

            # 6. Run Terraform ONCE per user
            if tf_files_found:
                if plan_only:
                    run_terraform_plan(lab_dir)
                else:
                    print(f"[*] Deploying lab for {user_name}...")
                    run_terraform(lab_dir)

                    if snap_create:
                        from python.snapshots import create_initial_snapshot
                        create_initial_snapshot(
                            lab_dir=lab_dir,
                            node_name=node,
                            snap_name=snap_name,
                            include_ram=snap_ram,
                            description=snap_description
                        )
            else:
                print(f"[WARNING] No .tf files found in {lab_config_dir}")

def destroy_lab(lab_name, users_config, plan_only=False):
    """Handles ONLY destruction with detailed feedback for each user."""
    labs_matrix = load_labs_matrix()
    lab_info = labs_matrix.get(lab_name)
    if not lab_info:
        print(f"[ERROR] Lab '{lab_name}' not found in labs.yaml")
        return

    for group_name, group_info in users_config.items():
        for user_name in group_info['members'].keys():
            permit, managed, destroy = get_user_lab_status(lab_info, group_name, user_name)

            lab_dir = os.path.join("groups", group_name, "users", user_name, "labs", lab_name)

            # Если папки физически нет, нам нечего обсуждать для этого юзера
            if not os.path.exists(lab_dir):
                continue

            # Логика уведомлений
            if not managed:
                print(f"[SKIP] Lab '{lab_name}' for '{user_name}' is UNMANAGED. Manual action required.")
                continue

            if not destroy:
                print(f"[KEEP] Lab '{lab_name}' for '{user_name}' is protected (destroy: false).")
                continue

            # Если дошли сюда, значит managed: true И destroy: true
            if plan_only:
                run_terraform_destroy_plan(lab_dir)
            else:
                print(f"[!] DESTROYING lab '{lab_name}' for '{user_name}'...")
                if run_terraform_destroy(lab_dir):
                    shutil.rmtree(lab_dir)
                    print(f"[SUCCESS] Folder removed for {user_name}")
                else:
                    print(f"[ERROR] Terraform destroy failed for {user_name}. Directory preserved.")