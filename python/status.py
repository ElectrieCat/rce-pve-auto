"""Read-only status overview: which labs are deployed for whom.

Only reads configs/*.yaml and the local groups/ directories.
Never calls Proxmox API or Terraform, so it is safe to run anytime.
"""
import os

from python.parser import load_labs_matrix
from python.deploy_labs import get_user_lab_status


def show_status(users_config: dict, filter_group: str = None, filter_lab: str = None):
    """Prints group/user/lab matrix with on-disk state.

    For every (group, user, lab) shows the effective
    permit/managed/destroy flags plus whether the lab directory
    (and its terraform.tfvars.json) exists on disk.
    """
    labs_matrix = load_labs_matrix()
    if filter_lab and filter_lab not in labs_matrix:
        print(f"[ERROR] Lab '{filter_lab}' not found in labs.yaml.")
        return

    lab_names = [filter_lab] if filter_lab else sorted(labs_matrix.keys())
    if not lab_names:
        print("[WARNING] No labs defined in labs.yaml.")
        lab_names = []

    n_users = n_deployed = 0
    for group_name in sorted(users_config.keys()):
        if filter_group and group_name != filter_group:
            continue
        group_info = users_config[group_name]
        members = group_info.get('members', {})
        print(f"\n== {group_name} ({len(members)} users) ==")
        for user_name in sorted(members.keys()):
            user_data = members[user_name]
            user_dir = os.path.join("groups", group_name, "users", user_name)
            on_disk = "yes" if os.path.isdir(user_dir) else "no"
            print(
                f"  {user_name} [id={user_data.get('internal_id')} "
                f"enabled={user_data.get('enabled')} dir={on_disk}]"
            )
            n_users += 1
            for lab_name in lab_names:
                lab_info = labs_matrix.get(lab_name) or {}
                permit, managed, destroy = get_user_lab_status(
                    lab_info, group_name, user_name
                )
                lab_dir = os.path.join(user_dir, "labs", lab_name)
                tfvars = os.path.join(lab_dir, "terraform.tfvars.json")
                if os.path.isdir(lab_dir):
                    state = "deployed" if os.path.exists(tfvars) else "dir-no-tfvars"
                    n_deployed += 1
                elif not managed:
                    state = "skipped-unmanaged"
                elif destroy:
                    state = "marked-destroy"
                else:
                    state = "not-deployed"
                print(
                    f"    - {lab_name}: {state} "
                    f"(permit={permit} managed={managed} destroy={destroy})"
                )

    print(f"\n[*] {n_users} users, {n_deployed} deployed lab dirs shown.")
