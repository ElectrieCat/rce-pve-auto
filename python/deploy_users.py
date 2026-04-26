import os
import json
import secrets
import string
import csv
import shutil
from python.terraform_utils import run_terraform, run_terraform_destroy


def generate_password(policy):
    """Generates a secure password based on the given policy."""
    length = policy.get('length', 8)
    characters = ""
    if policy.get('lowercase', True): characters += string.ascii_lowercase
    if policy.get('uppercase', True): characters += string.ascii_uppercase
    if policy.get('numbers', True): characters += string.digits
    if policy.get('special', True): characters += "!@#$%^&*()-_+="

    if not characters:
        characters = string.ascii_letters + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))


def export_csv(group_name, group_dir):
    """Generates a CSV file with passwords for the group."""
    os.makedirs("passwords", exist_ok=True)
    csv_path = os.path.join("passwords", f"{group_name}.csv")
    users_dir = os.path.join(group_dir, "users")
    if not os.path.exists(users_dir): return

    with open(csv_path, mode='w', newline='', encoding='utf-8') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["Username", "Password", "Enabled", "Comment"])
        for user_name in os.listdir(users_dir):
            user_dir = os.path.join(users_dir, user_name)
            tfvars_path = os.path.join(user_dir, "terraform.tfvars.json")
            if os.path.exists(tfvars_path):
                with open(tfvars_path, 'r', encoding='utf-8') as f:
                    tfvars = json.load(f)
                    writer.writerow([
                        tfvars.get("username", user_name),
                        tfvars.get("password", ""),
                        tfvars.get("enabled", True),
                        tfvars.get("comment", "")
                    ])
    print(f"[SUCCESS] Passwords exported to {csv_path}")


def cleanup_orphaned_users(group_name, config):
    """Removes users from Proxmox and disk if they are not in config and have no labs."""
    group_dir = os.path.join("groups", group_name)
    users_base_dir = os.path.join(group_dir, "users")
    if not os.path.exists(users_base_dir): return

    # If group is missing from config, all users are orphans
    if group_name in config:
        active_users = config[group_name]['members'].keys()
    else:
        active_users = []

    existing_user_dirs = os.listdir(users_base_dir)

    for user_dir_name in existing_user_dirs:
        if user_dir_name not in active_users:
            user_path = os.path.join(users_base_dir, user_dir_name)

            # --- Safety check logic remains the same ---
            labs_path = os.path.join(user_path, "labs")
            has_active_labs = False
            if os.path.exists(labs_path):
                if [d for d in os.listdir(labs_path) if os.path.isdir(os.path.join(labs_path, d))]:
                    print(f"[WARNING] Cannot delete user '{user_dir_name}': Active labs found.")
                    has_active_labs = True
            if [d for d in os.listdir(user_path) if
                os.path.isdir(os.path.join(user_path, d)) and d not in [".terraform", "labs"]]:
                print(f"[WARNING] Cannot delete user '{user_dir_name}': Unknown directories found.")
                has_active_labs = True

            if has_active_labs: continue

            print(f"[!] Orphaned user '{user_dir_name}' is clean. Deleting...")
            if run_terraform_destroy(user_path):
                shutil.rmtree(user_path)
    if os.path.exists(group_dir):
        export_csv(group_name, group_dir)

def cleanup_orphaned_groups(config):
    """Removes groups from Proxmox and disk if they are not in config."""
    groups_base_dir = "groups"
    if not os.path.exists(groups_base_dir): return

    existing_groups = os.listdir(groups_base_dir)
    active_groups = config.keys()

    for group_name in existing_groups:
        if group_name not in active_groups:
            group_path = os.path.join(groups_base_dir, group_name)

            print(f"[!] Found orphaned group: {group_name}. Checking for remaining users...")

            # 1. Try to clean up users in this old group first
            cleanup_orphaned_users(group_name, config)

            # 2. Check if users directory is now empty or gone
            users_dir = os.path.join(group_path, "users")
            if os.path.exists(users_dir) and os.listdir(users_dir):
                print(f"[WARNING] Cannot delete group '{group_name}': Some users (with labs) still exist.")
                continue

            # 3. Final safety: check for any other subdirs in group folder (except .terraform)
            other_dirs = [d for d in os.listdir(group_path) if
                          os.path.isdir(os.path.join(group_path, d)) and d not in [".terraform", "users"]]
            if other_dirs:
                print(f"[WARNING] Cannot delete group '{group_name}': Manual subdirectories found: {other_dirs}")
                continue

            # 4. If everything is clear, destroy group
            print(f"[!] Group '{group_name}' is empty. Destroying...")
            if run_terraform_destroy(group_path):
                shutil.rmtree(group_path)
                # Removing group passwords csv file
                csv_path = os.path.join("passwords", f"{group_name}.csv")
                if os.path.exists(csv_path):
                    os.remove(csv_path)
                    print(f"[SUCCESS] Password file {csv_path} removed.")

                print(f"[SUCCESS] Group '{group_name}' removed completely.")


def prepare_user_environments(group_name, config):
    if group_name not in config:
        print(f"[ERROR] Group '{group_name}' not found in configuration.")
        return

    # --- FIX: Define group_data BEFORE using it ---
    group_data = config[group_name]

    # Cleanup orphaned users first
    cleanup_orphaned_users(group_name, config)

    group_dir = os.path.join("groups", group_name)
    os.makedirs(group_dir, exist_ok=True)

    # Generate group tfvars
    group_tfvars_path = os.path.join(group_dir, "terraform.tfvars.json")
    group_tfvars = {
        "group_name": group_name,
        "comment": group_data.get("comment", "")
    }
    with open(group_tfvars_path, 'w', encoding='utf-8') as f:
        json.dump(group_tfvars, f, indent=4)

    # Generate group main.tf wrapper
    group_main_tf = """
module "proxmox_group" {
  source     = "../../terraform/modules/group_module"
  group_name = var.group_name
  comment    = var.comment
}

variable "group_name" { type = string }
variable "comment" { type = string }
""".strip()
    with open(os.path.join(group_dir, "main.tf"), 'w', encoding='utf-8') as f:
        f.write(group_main_tf)

    print(f"[*] Prepared environment for group '{group_name}'")

    # Prepare users
    for user_name, user_data in group_data['members'].items():
        user_dir = os.path.join(group_dir, "users", user_name)
        os.makedirs(user_dir, exist_ok=True)
        tfvars_path = os.path.join(user_dir, "terraform.tfvars.json")

        tfvars = {}
        if os.path.exists(tfvars_path):
            with open(tfvars_path, 'r', encoding='utf-8') as f:
                tfvars = json.load(f)

        user_internal_id = user_data.get("internal_id")
        if user_internal_id is None:
            print(f"[ERROR] Cannot deploy user '{user_name}': internal-id is missing in users.yaml")
            continue

        tfvars.update({
            "username": user_name,
            "internal_id": user_data["internal_id"],
            "enabled": user_data["enabled"],
            "comment": user_data["comment"],
            "groups": [group_name]
        })

        if "password" not in tfvars:
            tfvars["password"] = generate_password(user_data["password_policy"])

        with open(tfvars_path, 'w', encoding='utf-8') as f:
            json.dump(tfvars, f, indent=4)

        user_main_tf = """
module "proxmox_user" {
  source   = "../../../../terraform/modules/user_module"
  username = var.username
  password = var.password
  enabled  = var.enabled
  comment  = var.comment
  groups   = var.groups
  internal_id = var.internal_id
}

variable "username" { type = string }
variable "password" { type = string }
variable "enabled"  { type = bool }
variable "comment"  { type = string }
variable "groups"   { type = list(string) }
variable "internal_id" { type = number }
""".strip()
        with open(os.path.join(user_dir, "main.tf"), 'w', encoding='utf-8') as f:
            f.write(user_main_tf)
        print(f"[*] Prepared environment for {user_name} (Enabled: {user_data['enabled']})")

    # Terraform execution
    print(f"[*] Initializing and applying Group resources...")
    if not run_terraform(group_dir):
        print("[ERROR] Group deployment failed.")
        return

    for user_name in group_data['members'].keys():
        user_dir = os.path.join(group_dir, "users", user_name)
        print(f"[*] Deploying user: {user_name}...")
        run_terraform(user_dir)

    export_csv(group_name, group_dir)


def change_passwords(group_name, config, target_user=None):
    """Forcefully regenerates passwords and applies changes via Terraform with Rollback."""
    if group_name not in config:
        print(f"[ERROR] Group '{group_name}' not found.")
        return

    group_data = config[group_name]
    group_dir = os.path.join("groups", group_name)

    if target_user:
        if target_user not in group_data['members']:
            print(f"[ERROR] User '{target_user}' not found in group '{group_name}'.")
            return
        users_to_change = [target_user]
    else:
        users_to_change = list(group_data['members'].keys())

    any_success = False

    for user_name in users_to_change:
        user_dir = os.path.join(group_dir, "users", user_name)
        tfvars_path = os.path.join(user_dir, "terraform.tfvars.json")

        if not os.path.exists(tfvars_path):
            continue

        # 1. Read existing tfvars and KEEP OLD PASSWORD for rollback
        with open(tfvars_path, 'r', encoding='utf-8') as f:
            tfvars = json.load(f)

        old_password = tfvars.get("password")

        # 2. Generate and save NEW password
        user_policy = group_data['members'][user_name]['password_policy']
        new_password = generate_password(user_policy)
        tfvars["password"] = new_password

        with open(tfvars_path, 'w', encoding='utf-8') as f:
            json.dump(tfvars, f, indent=4)

        print(f"[*] Attempting password update for {user_name}...")

        # 3. Run Terraform Apply
        if run_terraform(user_dir):
            print(f"[SUCCESS] Password updated in Proxmox for {user_name}")
            any_success = True
        else:
            # --- ROLLBACK LOGIC ---
            print(f"[ROLLBACK] Terraform failed. Reverting local password for {user_name}...")
            tfvars["password"] = old_password
            with open(tfvars_path, 'w', encoding='utf-8') as f:
                json.dump(tfvars, f, indent=4)
            print(f"[!] Local file for {user_name} restored to previous state.")

    # 4. Export CSV ONLY if at least one password was actually changed in Proxmox
    if any_success:
        export_csv(group_name, group_dir)
    else:
        print("[*] No changes were applied to Proxmox, CSV update skipped.")