import argparse
import json
import os
import sys
from python.parser import load_users_config


def setup_cli():
    parser = argparse.ArgumentParser(description="Proxmox Lab Automation Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # change-password
    cp_parser = subparsers.add_parser("change-password", help="Change password for a user or entire group")
    cp_parser.add_argument("group", help="Target group")
    cp_parser.add_argument("--user", help="Target user (if omitted, changes password for entire group)")

    # parse-test
    test_parser = subparsers.add_parser("parse-test", help="Test parsing of users.yaml config")
    test_parser.add_argument("--config", default="configs/users.yaml", help="Path to the config file")

    # deploy-users
    deploy_parser = subparsers.add_parser("deploy-users", help="Deploy users and resource pools")
    deploy_parser.add_argument("group", help="Target group for deployment")
    deploy_parser.add_argument(
        "--plan", action="store_true",
        help="Show plan without applying changes (passes --plan to each user's Terraform)"
    )

    # deploy-lab
    lab_parser = subparsers.add_parser("deploy-lab", help="Deploy a specific lab for all permitted users")
    lab_parser.add_argument("lab", help="Lab name (e.g., lab1)")
    lab_parser.add_argument("--plan", action="store_true", help="Show plan without applying changes")

    # destroy-lab
    destroy_lab_parser = subparsers.add_parser("destroy-lab", help="Destroy labs marked with destroy: true in YAML")
    destroy_lab_parser.add_argument("lab", help="Lab name (e.g., lab1)")
    destroy_lab_parser.add_argument("--plan", action="store_true", help="Show what will be destroyed")

    # backup
    subparsers.add_parser("backup", help="Create a system backup archive")

    # terraform-run
    tf_parser = subparsers.add_parser(
        "terraform-run",
        help="Run custom Terraform arguments against a directory or a lab"
    )
    tf_mode = tf_parser.add_mutually_exclusive_group(required=True)
    tf_mode.add_argument(
        "--dir",
        metavar="PATH",
        help=(
            "Explicit path to a Terraform directory. "
            "The tool sets up auth env and runs terraform there directly. "
            "Use this for manual overrides on a specific directory."
        )
    )
    tf_mode.add_argument(
        "--lab",
        metavar="LAB_NAME",
        help=(
            "Lab name to target. Runs the command for every managed user "
            "in that lab. Unmanaged labs are always skipped."
        )
    )
    tf_parser.add_argument(
        "--group",
        metavar="GROUP_NAME",
        help="Limit --lab mode to a specific group (optional)."
    )
    tf_parser.add_argument(
        "--user",
        metavar="USER_NAME",
        help="Limit --lab mode to a specific user (optional, requires --group)."
    )
    tf_parser.add_argument(
        "--force-managed",
        action="store_true",
        dest="force_managed",
        help=(
            "Override managed=false for labs in --lab mode, running the command "
            "even on unmanaged lab directories. Has no effect with --dir. "
            "Use with caution — labs are probably marked unmanaged for a reason."
        )
    )
    tf_parser.add_argument(
        "tf_args",
        nargs=argparse.REMAINDER,
        help=(
            "Arguments passed directly to terraform after 'init'. "
            "Separate them from tool arguments with --. "
            "Example: -- plan -target=proxmox_virtual_environment_vm.example-vm"
        )
    )

    return parser.parse_args()


def _load_users_or_exit(config_path="configs/users.yaml") -> dict:
    """Loads users config and exits with an error message if it fails."""
    parsed = load_users_config(config_path)
    if parsed is None:
        print("[ERROR] Failed to load configuration. Aborting.")
        sys.exit(1)
    return parsed


def run():
    args = setup_cli()

    if args.command == "parse-test":
        print(f"[*] Attempting to read config: {args.config}")
        parsed = load_users_config(args.config)
        if parsed is not None:
            print(json.dumps(parsed, indent=4, ensure_ascii=False))
        else:
            sys.exit(1)

    elif args.command == "deploy-users":
        from python.deploy_users import prepare_user_environments, cleanup_orphaned_groups

        print("[*] Loading configuration...")
        parsed = _load_users_or_exit()

        print("[*] Checking for orphaned groups...")
        cleanup_orphaned_groups(parsed, plan_only=args.plan)

        if args.group not in parsed:
            print(f"[ERROR] Group '{args.group}' not found in config.")
            sys.exit(1)

        print(f"[*] Starting deployment for group '{args.group}'...")
        prepare_user_environments(args.group, parsed, plan_only=args.plan)

    elif args.command == "change-password":
        from python.deploy_users import change_passwords

        parsed = _load_users_or_exit()
        target = args.user if args.user else f"ALL users in group '{args.group}'"
        confirm = input(f"[!] Are you sure you want to change password for {target}? (yes/no): ")
        if confirm.lower() == 'yes':
            change_passwords(args.group, parsed, args.user)
        else:
            print("[*] Operation cancelled.")

    elif args.command == "deploy-lab":
        from python.deploy_labs import deploy_lab

        parsed = _load_users_or_exit()
        deploy_lab(args.lab, parsed, plan_only=args.plan)

    elif args.command == "destroy-lab":
        from python.deploy_labs import destroy_lab

        parsed = _load_users_or_exit()
        destroy_lab(args.lab, parsed, plan_only=args.plan)

    elif args.command == "backup":
        from python.backup_utils import create_system_backup

        success = create_system_backup()
        if not success:
            sys.exit(1)

    elif args.command == "terraform-run":
        from python.terraform_utils import run_terraform_custom
        from python.deploy_labs import terraform_run_lab

        # Strip the '--' separator that users conventionally write before tf args
        tf_args = args.tf_args
        if tf_args and tf_args[0] == "--":
            tf_args = tf_args[1:]

        if not tf_args:
            print("[ERROR] No Terraform arguments provided. Pass them after --.")
            print("  Example: python main.py terraform-run --dir PATH -- plan -target=...")
            sys.exit(1)

        if args.dir:
            if not os.path.isdir(args.dir):
                print(f"[ERROR] Directory not found: '{args.dir}'")
                sys.exit(1)
            run_terraform_custom(args.dir, *tf_args)

        else:
            if args.user and not args.group:
                print("[ERROR] --user requires --group to be specified.")
                sys.exit(1)
            parsed = _load_users_or_exit()
            terraform_run_lab(
                lab_name=args.lab,
                users_config=parsed,
                tf_args=tf_args,
                filter_group=args.group,
                filter_user=args.user,
                force_managed=args.force_managed,
            )