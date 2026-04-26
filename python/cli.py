import argparse
import json
from python.parser import load_users_config


def setup_cli():
    parser = argparse.ArgumentParser(description="Proxmox Lab Automation Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Command: change-password
    cp_parser = subparsers.add_parser("change-password", help="Change password for a user or entire group")
    cp_parser.add_argument("group", help="Target group")
    cp_parser.add_argument("--user", help="Target user (if not specified, changes for entire group)")

    # Command: parse-test
    test_parser = subparsers.add_parser("parse-test", help="Test parsing of users.yaml config")
    test_parser.add_argument("--config", default="configs/users.yaml", help="Path to the config file")

    # Command: deploy-users
    deploy_parser = subparsers.add_parser("deploy-users", help="Deploy users and resource pools")
    deploy_parser.add_argument("group", help="Target group for deployment")
    deploy_parser.add_argument("--plan", action="store_true", help="Show plan without applying changes")

    # Command: deploy-lab
    lab_parser = subparsers.add_parser("deploy-lab", help="Deploy a specific lab for all permitted users")
    lab_parser.add_argument("lab", help="Lab name (e.g., lab1)")
    lab_parser.add_argument("--plan", action="store_true", help="Show plan without applying changes")

    # Command: destroy-lab
    destroy_lab_parser = subparsers.add_parser("destroy-lab", help="Destroy labs marked with destroy: true in YAML")
    destroy_lab_parser.add_argument("lab", help="Lab name (e.g., lab1)")
    destroy_lab_parser.add_argument("--plan", action="store_true", help="Show what will be destroyed")

    # Command: backup
    subparsers.add_parser("backup", help="Create a system backup archive")

    return parser.parse_args()


def run():
    args = setup_cli()

    if args.command == "parse-test":
        print(f"[*] Attempting to read config: {args.config}")
        parsed_data = load_users_config(args.config)
        if parsed_data is not None:
            print(json.dumps(parsed_data, indent=4, ensure_ascii=False))

    elif args.command == "deploy-users":
        from python.deploy_users import prepare_user_environments, cleanup_orphaned_groups
        print(f"[*] Loading configuration...")
        parsed_data = load_users_config("configs/users.yaml")

        if parsed_data is not None:
            print(f"[*] Checking for orphaned groups...")
            cleanup_orphaned_groups(parsed_data)
            if args.group in parsed_data:
                print(f"[*] Starting deployment preparation for group '{args.group}'...")
                # Примечание: убедись, что prepare_user_environments принимает plan_only
                prepare_user_environments(args.group, parsed_data)
            else:
                print(f"[*] Group '{args.group}' not found in config.")
        else:
            print("[ERROR] Failed to load configuration.")

    elif args.command == "change-password":
        from python.deploy_users import change_passwords
        parsed_data = load_users_config("configs/users.yaml")
        if parsed_data:
            target = args.user if args.user else f"ALL users in group {args.group}"
            confirm = input(f"[!] Are you sure you want to change password for {target}? (yes/no): ")
            if confirm.lower() == 'yes':
                change_passwords(args.group, parsed_data, args.user)
            else:
                print("[*] Operation cancelled.")

    elif args.command == "deploy-lab":
        from python.deploy_labs import deploy_lab
        parsed_data = load_users_config("configs/users.yaml")
        if parsed_data:
            deploy_lab(args.lab, parsed_data, plan_only=args.plan)

    elif args.command == "destroy-lab":
        from python.deploy_labs import destroy_lab # Мы добавили эту функцию в deploy_labs.py
        parsed_data = load_users_config("configs/users.yaml")
        if parsed_data:
            destroy_lab(args.lab, parsed_data, plan_only=args.plan)


    elif args.command == "backup":
        from python.backup_utils import create_system_backup
        create_system_backup()