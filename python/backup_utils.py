import os
import zipfile
from datetime import datetime


def create_system_backup():
    """Creates a timestamped ZIP archive of configs, passwords and groups (excluding .terraform)."""

    # 1. Setup paths
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_dir = "backups"
    backup_filename = f"pve_auto_backup_{timestamp}.zip"
    backup_path = os.path.join(backup_dir, backup_filename)

    # Target directories to backup
    targets = ["configs", "passwords", "groups"]

    # Ensure backup folder exists
    os.makedirs(backup_dir, exist_ok=True)

    print(f"[*] Starting backup to {backup_path}...")

    try:
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for target in targets:
                if not os.path.exists(target):
                    print(f"[WARNING] Directory '{target}' not found, skipping.")
                    continue

                for root, dirs, files in os.walk(target):
                    # SAFETY: Skip .terraform directories to keep backup small
                    if ".terraform" in dirs:
                        dirs.remove(".terraform")
                    if "__pycache__" in dirs:
                        dirs.remove("__pycache__")

                    for file in files:
                        # Skip temporary or backup files if needed
                        if file.endswith(".bak") or file.endswith(".pyc"):
                            continue

                        file_path = os.path.join(root, file)
                        # Add file to zip with relative path
                        zipf.write(file_path, os.path.relpath(file_path, os.path.curdir))

        print(f"[SUCCESS] Backup created: {backup_path}")
        return True

    except Exception as e:
        print(f"[ERROR] Backup failed: {str(e)}")
        return False