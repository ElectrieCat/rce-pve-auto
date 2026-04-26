import subprocess
import sys
import shutil


def install_package(package_name):
    """Installs a python package using pip."""
    print(f"[*] Installing {package_name}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        return True
    except subprocess.CalledProcessError:
        print(f"[ERROR] Failed to install {package_name}. Please check your internet connection.")
        return False


def check_terraform():
    """Checks if terraform binary is available in the system PATH."""
    print("[*] Checking for Terraform...")
    terraform_path = shutil.which("terraform")
    if terraform_path:
        try:
            version = subprocess.check_output(["terraform", "--version"], text=True).split('\n')[0]
            print(f"[SUCCESS] Found Terraform: {version}")
            return True
        except Exception:
            print("[WARNING] Terraform is found but not working correctly.")
            return False
    else:
        print("[ERROR] Terraform not found in system PATH.")
        print("[HINT] Please install Terraform from: https://www.terraform.io/downloads")
        return False


def main():
    print("=" * 50)
    print("   PVE Automation Tool - Dependency Installer")
    print("=" * 50)

    # 1. Install Python dependencies
    # Only PyYAML is external for our project
    required_packages = ["PyYAML","proxmoxer","requests"]

    all_python_ok = True
    for pkg in required_packages:
        if not install_package(pkg):
            all_python_ok = False

    # 2. Check for system dependencies
    terraform_ok = check_terraform()

    print("=" * 50)
    if all_python_ok and terraform_ok:
        print("[FINISHED] All dependencies are ready. You can now use manager.py")
    else:
        print("[FINISHED] Some dependencies are missing or failed. Please check the log above.")
    print("=" * 50)


if __name__ == "__main__":
    main()
