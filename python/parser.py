import yaml
import os


def load_auth_config(auth_path="configs/auth.yaml"):
    """Reads auth.yaml and returns the proxmox configuration section."""
    if not os.path.exists(auth_path):
        print(f"[ERROR] Auth file '{auth_path}' not found.")
        return None

    with open(auth_path, 'r', encoding='utf-8') as file:
        data = yaml.safe_load(file) or {}

    return data.get('proxmox', {})


def load_users_config(config_path="configs/users.yaml"):
    """Reads users.yaml and returns a parsed dictionary with inheritance resolved."""
    if not os.path.exists(config_path):
        print(f"[ERROR] Configuration file '{config_path}' not found.")
        return None

    with open(config_path, 'r', encoding='utf-8') as file:
        data = yaml.safe_load(file) or {}

    if not data or 'users' not in data:
        return {}

    # Read default password policy
    defaults = data.get('defaults') or {}
    default_pwd_policy = defaults.get('password-strength') or {}

    parsed_groups = {}

    users_section = data.get('users') or {}
    groups_data = users_section.get('groups') or {}

    for group_name, group_info in groups_data.items():
        group_info = group_info or {}

        group_enabled = group_info.get('enabled', True)
        group_comment = group_info.get('comment', 'Managed by automation tool')

        # Password policy inheritance
        group_pwd_policy = group_info.get('password-strength') or {}
        final_pwd_policy = {**default_pwd_policy, **group_pwd_policy}

        parsed_members = {}
        members_list = group_info.get('members') or []

        for member in members_list:
            if not member or 'name' not in member:
                continue

            member_name = member['name']
            member_enabled = member.get('enabled', group_enabled)

            parsed_members[member_name] = {
                'enabled': member_enabled,
                'internal_id': member.get('internal-id'),
                'comment': member.get('comment', ''),
                'password_policy': final_pwd_policy
            }

        parsed_groups[group_name] = {
            'enabled': group_enabled,
            'comment': group_comment,
            'members': parsed_members
        }

    return parsed_groups

def load_labs_matrix(path="configs/labs.yaml"):
    """Reads labs.yaml to understand who gets which lab."""
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
    return data.get('labs', {})

def load_lab_config(lab_name):
    """Reads main.yaml for a specific lab."""
    path = f"configs/labs/{lab_name}/main.yaml"
    if not os.path.exists(path):
        print(f"[ERROR] Lab config not found for {lab_name}: {path}")
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}