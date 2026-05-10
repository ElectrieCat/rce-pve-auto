import yaml
import os


def _safe_yaml_load(path):
    """
    Opens and parses a YAML file at the given path.
    Returns parsed data on success, None on any failure (missing file, bad syntax, etc.).
    """
    if not os.path.exists(path):
        print(f"[ERROR] File not found: '{path}'")
        return None

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"[ERROR] Failed to parse YAML file '{path}': {e}")
        return None
    except OSError as e:
        print(f"[ERROR] Could not read file '{path}': {e}")
        return None

    if data is None:
        print(f"[WARNING] File '{path}' is empty.")

    return data


def load_auth_config(auth_path="configs/auth.yaml"):
    """Reads auth.yaml and returns the proxmox configuration section."""
    data = _safe_yaml_load(auth_path)
    if data is None:
        return None

    proxmox_cfg = data.get('proxmox')
    if not proxmox_cfg:
        print(f"[ERROR] 'proxmox' section is missing in '{auth_path}'.")
        return None

    return proxmox_cfg


def load_users_config(config_path="configs/users.yaml"):
    """
    Reads users.yaml and returns a parsed dictionary with inheritance resolved.
    Returns an empty dict if the file has no groups defined.
    Returns None on any read or parse error.
    """
    data = _safe_yaml_load(config_path)
    if data is None:
        return None

    if 'users' not in data:
        print(f"[WARNING] No 'users' section found in '{config_path}'. Nothing to process.")
        return {}

    defaults = data.get('defaults') or {}
    default_pwd_policy = defaults.get('password-strength') or {}

    parsed_groups = {}

    users_section = data.get('users') or {}
    groups_data = users_section.get('groups') or {}

    for group_name, group_info in groups_data.items():
        group_info = group_info or {}

        group_enabled = group_info.get('enabled', True)
        group_comment = group_info.get('comment', 'Managed by automation tool')

        # Password policy: group settings override global defaults
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

    # Validate that internal-id values are unique across ALL users in ALL groups.
    # Duplicate IDs cause bridge name collisions (u{id}l{lab}n{net}) which silently
    # breaks network isolation between users.
    seen_ids = {}  # internal_id -> "group/username" for clear error reporting
    valid = True
    for group_name, group_data in parsed_groups.items():
        for member_name, member_data in group_data['members'].items():
            uid = member_data.get('internal_id')
            if uid is None:
                print(f"[WARNING] {member_name} has no internal-id")
                continue
            key = f"{group_name}/{member_name}"
            if uid in seen_ids:
                print(
                    f"[ERROR] Duplicate internal-id '{uid}' found: "
                    f"'{key}' and '{seen_ids[uid]}' share the same ID. "
                    f"This will cause bridge name collisions. Fix users.yaml before deploying."
                )
                valid = False
            else:
                seen_ids[uid] = key

    if not valid:
        return None

    return parsed_groups


def load_labs_matrix(path="configs/labs.yaml"):
    """Reads labs.yaml and returns the full labs dictionary."""
    data = _safe_yaml_load(path)
    if data is None:
        return {}

    labs = data.get('labs')
    if not labs:
        print(f"[WARNING] No 'labs' section found in '{path}'.")
        return {}

    # Validate that lab internal-ids are unique. They combine with user internal-ids
    # to form bridge names, so a collision would corrupt network naming.
    seen_ids = {}
    valid = True
    for lab_name, lab_info in labs.items():
        if not lab_info:
            continue
        lid = lab_info.get('internal-id')
        if lid is None:
            print(f"[WARNING] {lab_name} has no internal-id")
            continue
        if lid in seen_ids:
            print(
                f"[ERROR] Duplicate internal-id '{lid}' found in labs.yaml: "
                f"'{lab_name}' and '{seen_ids[lid]}' share the same ID. "
                f"This will cause bridge name collisions. Fix labs.yaml before deploying."
            )
            valid = False
        else:
            seen_ids[lid] = lab_name

    if not valid:
        return {}

    return labs


def load_lab_config(lab_name):
    """Reads main.yaml for a specific lab and returns its contents."""
    path = f"configs/labs/{lab_name}/main.yaml"
    data = _safe_yaml_load(path)
    if data is None:
        return {}

    return data