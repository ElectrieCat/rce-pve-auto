import os
import json
import secrets
import string
import csv
import shutil
from python.terraform_utils import run_terraform_apply, run_terraform_plan, run_terraform_destroy, run_terraform_destroy_plan

# ---------------------------------------------------------------------------
# Terraform template files
# These live here as constants so they are easy to find and edit without
# hunting through logic code. If the modules ever move, only these change.
# ---------------------------------------------------------------------------

_GROUP_MAIN_TF = """\
module "proxmox_group" {
  source     = "../../terraform/modules/group_module"
  group_name = var.group_name
  comment    = var.comment
}

variable "group_name" { type = string }
variable "comment"    { type = string }
"""

_USER_MAIN_TF = """\
module "proxmox_user" {
  source      = "../../../../terraform/modules/user_module"
  username    = var.username
  password    = var.password
  enabled     = var.enabled
  comment     = var.comment
  groups      = var.groups
  internal_id = var.internal_id
}

variable "username"    { type = string }
variable "password"    { type = string }
variable "enabled"     { type = bool }
variable "comment"     { type = string }
variable "groups"      { type = list(string) }
variable "internal_id" { type = number }
"""


# ---------------------------------------------------------------------------
# Password utilities
# ---------------------------------------------------------------------------

def generate_password(policy: dict) -> str:
    """Generates a random password according to the given policy dict."""
    length = policy.get('length', 8)
    characters = ""
    if policy.get('lowercase', True):
        characters += string.ascii_lowercase
    if policy.get('uppercase', True):
        characters += string.ascii_uppercase
    if policy.get('numbers', True):
        characters += string.digits
    if policy.get('special', True):
        characters += "!@#$%^&*()-_+="

    if not characters:
        characters = string.ascii_letters + string.digits

    return ''.join(secrets.choice(characters) for _ in range(length))


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def export_csv(group_name: str, group_dir: str):
    """Writes a CSV of usernames and passwords for the given group."""
    os.makedirs("passwords", exist_ok=True)
    csv_path = os.path.join("passwords", f"{group_name}.csv")
    users_dir = os.path.join(group_dir, "users")

    if not os.path.exists(users_dir):
        return

    with open(csv_path, mode='w', newline='', encoding='utf-8') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["Username", "Password", "Enabled", "Comment"])

        for user_name in sorted(os.listdir(users_dir)):
            tfvars_path = os.path.join(users_dir, user_name, "terraform.tfvars.json")
            if not os.path.exists(tfvars_path):
                continue
            with open(tfvars_path, 'r', encoding='utf-8') as f:
                tfvars = json.load(f)
            writer.writerow([
                tfvars.get("username", user_name),
                tfvars.get("password", ""),
                tfvars.get("enabled", True),
                tfvars.get("comment", "")
            ])

    print(f"[SUCCESS] Passwords exported to {csv_path}")


# ---------------------------------------------------------------------------
# Terraform file writers
# ---------------------------------------------------------------------------

def _write_group_tf_files(group_dir: str, group_name: str, comment: str):
    """Writes terraform.tfvars.json and main.tf for a group directory."""
    tfvars = {
        "group_name": group_name,
        "comment": comment
    }
    with open(os.path.join(group_dir, "terraform.tfvars.json"), 'w', encoding='utf-8') as f:
        json.dump(tfvars, f, indent=4)

    with open(os.path.join(group_dir, "main.tf"), 'w', encoding='utf-8') as f:
        f.write(_GROUP_MAIN_TF)


def _write_user_tf_files(user_dir: str, user_name: str, user_data: dict, group_name: str):
    """
    Writes terraform.tfvars.json and main.tf for a user directory.
    Preserves an existing password if one is already stored on disk.
    Returns False if the user is missing a required internal_id, True otherwise.
    """
    tfvars_path = os.path.join(user_dir, "terraform.tfvars.json")

    # Load existing tfvars so we can preserve the stored password
    existing_tfvars = {}
    if os.path.exists(tfvars_path):
        with open(tfvars_path, 'r', encoding='utf-8') as f:
            existing_tfvars = json.load(f)

    internal_id = user_data.get("internal_id")
    if internal_id is None:
        print(f"[ERROR] Cannot deploy user '{user_name}': internal-id is missing in users.yaml")
        return False

    tfvars = {
        **existing_tfvars,
        "username": user_name,
        "internal_id": internal_id,
        "enabled": user_data["enabled"],
        "comment": user_data["comment"],
        "groups": [group_name],
    }

    # Only generate a password if one doesn't already exist
    if "password" not in tfvars:
        tfvars["password"] = generate_password(user_data["password_policy"])

    with open(tfvars_path, 'w', encoding='utf-8') as f:
        json.dump(tfvars, f, indent=4)

    with open(os.path.join(user_dir, "main.tf"), 'w', encoding='utf-8') as f:
        f.write(_USER_MAIN_TF)

    return True


# ---------------------------------------------------------------------------
# Orphan cleanup
# ---------------------------------------------------------------------------

def _user_has_active_labs(user_path: str) -> bool:
    """
    Returns True if the user directory contains any lab subdirectories,
    or any unexpected subdirectories that we should not silently delete.
    """
    labs_path = os.path.join(user_path, "labs")
    if os.path.exists(labs_path):
        lab_dirs = [d for d in os.listdir(labs_path) if os.path.isdir(os.path.join(labs_path, d))]
        if lab_dirs:
            print(f"[WARNING] Cannot delete user at '{user_path}': active labs found: {lab_dirs}")
            return True

    unknown_dirs = [
        d for d in os.listdir(user_path)
        if os.path.isdir(os.path.join(user_path, d)) and d not in [".terraform", "labs"]
    ]
    if unknown_dirs:
        print(f"[WARNING] Cannot delete user at '{user_path}': unknown directories found: {unknown_dirs}")
        return True

    return False


def cleanup_orphaned_users(group_name: str, config: dict, plan_only: bool = False) -> bool:
    """
    Removes users from Proxmox and disk if they are no longer in config
    and have no active labs remaining.

    In plan_only mode, runs terraform plan -destroy to show what would be
    removed without actually deleting anything.

    Returns True if any orphans were found (regardless of plan_only mode).
    """
    group_dir = os.path.join("groups", group_name)
    users_base_dir = os.path.join(group_dir, "users")
    if not os.path.exists(users_base_dir):
        return False

    active_users = config[group_name]["members"].keys() if group_name in config else []
    found_any = False

    for user_dir_name in os.listdir(users_base_dir):
        if user_dir_name in active_users:
            continue

        user_path = os.path.join(users_base_dir, user_dir_name)
        if _user_has_active_labs(user_path):
            continue

        found_any = True
        if plan_only:
            print(f"[PLAN] Orphaned user '{user_dir_name}' would be destroyed:")
            run_terraform_destroy_plan(user_path)
        else:
            print(f"[!] Orphaned user '{user_dir_name}' found with no active labs. Removing...")
            if run_terraform_destroy(user_path):
                shutil.rmtree(user_path)
                print(f"[SUCCESS] User '{user_dir_name}' removed.")

    if not plan_only:
        export_csv(group_name, group_dir)

    return found_any


def cleanup_orphaned_groups(config: dict, plan_only: bool = False) -> bool:
    """
    Removes groups from Proxmox and disk if they are no longer in config
    and all their users have been cleaned up.

    In plan_only mode, runs terraform plan -destroy to show what would be
    removed without actually deleting anything.

    Returns True if any orphans were found (regardless of plan_only mode).
    """
    groups_base_dir = "groups"
    if not os.path.exists(groups_base_dir):
        return False

    active_groups = config.keys()
    found_any = False

    for group_name in os.listdir(groups_base_dir):
        if group_name in active_groups:
            continue

        group_path = os.path.join(groups_base_dir, group_name)
        found_any = True
        print(f"[!] Found orphaned group '{group_name}'. Checking for remaining users...")

        cleanup_orphaned_users(group_name, config, plan_only=plan_only)

        # In plan mode we cannot know if users *would* be gone after destruction,
        # so we still show the group plan regardless of remaining user dirs.
        if plan_only:
            print(f"[PLAN] Orphaned group '{group_name}' would be destroyed:")
            run_terraform_destroy_plan(group_path)
            continue

        users_dir = os.path.join(group_path, "users")
        if os.path.exists(users_dir) and os.listdir(users_dir):
            print(f"[WARNING] Cannot delete group '{group_name}': users with labs still exist.")
            continue

        other_dirs = [
            d for d in os.listdir(group_path)
            if os.path.isdir(os.path.join(group_path, d)) and d not in [".terraform", "users"]
        ]
        if other_dirs:
            print(f"[WARNING] Cannot delete group '{group_name}': unexpected subdirectories: {other_dirs}")
            continue

        print(f"[!] Group '{group_name}' is empty. Destroying...")
        if run_terraform_destroy(group_path):
            shutil.rmtree(group_path)

            csv_path = os.path.join("passwords", f"{group_name}.csv")
            if os.path.exists(csv_path):
                os.remove(csv_path)
                print(f"[SUCCESS] Password file '{csv_path}' removed.")

            print(f"[SUCCESS] Group '{group_name}' removed completely.")

    return found_any


# ---------------------------------------------------------------------------
# Main deployment
# ---------------------------------------------------------------------------

def prepare_user_environments(group_name: str, config: dict, plan_only: bool = False):
    """
    Prepares and deploys a group and all its users to Proxmox via Terraform.
    Steps:
      1. Clean up users removed from config (skipped in plan_only mode)
      2. Write group-level Terraform files and apply (or plan)
      3. Write per-user Terraform files and apply (or plan) for each user
      4. Export the group password CSV (skipped in plan_only mode)

    Args:
        plan_only: If True, runs 'terraform plan' instead of 'apply' for all
                   steps. No resources are created and no CSV is written.
    """
    if group_name not in config:
        print(f"[ERROR] Group '{group_name}' not found in configuration.")
        return

    group_data = config[group_name]
    group_dir = os.path.join("groups", group_name)
    os.makedirs(group_dir, exist_ok=True)

    if not plan_only:
        cleanup_orphaned_users(group_name, config)

    # --- Group-level ---
    _write_group_tf_files(group_dir, group_name, group_data.get("comment", ""))
    if plan_only:
        print(f"[*] Planning group '{group_name}'...")
        run_terraform_plan(group_dir)
    else:
        print(f"[*] Deploying group '{group_name}'...")
        if not run_terraform_apply(group_dir):
            print(f"[ERROR] Group '{group_name}' deployment failed. Aborting user deployments.")
            return

    # --- Per-user ---
    for user_name, user_data in group_data['members'].items():
        user_dir = os.path.join(group_dir, "users", user_name)
        os.makedirs(user_dir, exist_ok=True)

        ok = _write_user_tf_files(user_dir, user_name, user_data, group_name)
        if not ok:
            continue

        if plan_only:
            print(f"[*] Planning user '{user_name}' (enabled: {user_data['enabled']})...")
            run_terraform_plan(user_dir)
        else:
            print(f"[*] Deploying user '{user_name}' (enabled: {user_data['enabled']})...")
            run_terraform_apply(user_dir)

    if not plan_only:
        export_csv(group_name, group_dir)


# ---------------------------------------------------------------------------
# Password management
# ---------------------------------------------------------------------------

def change_passwords(group_name: str, config: dict, target_user: str = None):
    """
    Regenerates passwords for one user or all users in a group, applies them
    via Terraform, and rolls back the local file if Terraform fails.
    """
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
            print(f"[WARNING] No tfvars file found for '{user_name}', skipping.")
            continue

        with open(tfvars_path, 'r', encoding='utf-8') as f:
            tfvars = json.load(f)

        old_password = tfvars.get("password")
        new_password = generate_password(group_data['members'][user_name]['password_policy'])
        tfvars["password"] = new_password

        with open(tfvars_path, 'w', encoding='utf-8') as f:
            json.dump(tfvars, f, indent=4)

        print(f"[*] Applying new password for '{user_name}'...")
        if run_terraform_apply(user_dir):
            print(f"[SUCCESS] Password updated in Proxmox for '{user_name}'.")
            any_success = True
        else:
            print(f"[ROLLBACK] Terraform failed. Reverting local password for '{user_name}'...")
            tfvars["password"] = old_password
            with open(tfvars_path, 'w', encoding='utf-8') as f:
                json.dump(tfvars, f, indent=4)
            print(f"[!] Local file for '{user_name}' restored to previous state.")

    if any_success:
        export_csv(group_name, group_dir)
    else:
        print("[*] No passwords were changed in Proxmox. CSV update skipped.")