# Proxmox Lab Automation Manager

A Python + Terraform tool for managing Proxmox VE lab environments for multiple users and groups. Built for sysadmins running cybersecurity labs, training environments, or any setup where you need to provision isolated per-user infrastructure at scale.

> **Note:** This tool was built with AI assistance due to time constraints. If you find a bug or have an improvement, issues and pull requests are welcome.

---

## How it works

The tool manages three layers of objects in Proxmox:

- **Groups** — Proxmox groups with resource pools
- **Users** — Proxmox user accounts assigned to groups
- **Labs** — Per-user Terraform deployments (VMs, networks, snapshots)

Configuration lives in YAML files. Terraform handles the actual Proxmox API calls. The tool generates per-user Terraform workspaces under `groups/`, runs them, and keeps everything in sync with your config.

### Hierarchy and overrides

Both users and labs support a three-level config hierarchy: **Global defaults → Group → User**. Lower levels override higher ones. This means you can set a group-wide `permit: false` and then selectively override it for specific users, or vice versa.

### Filesystem as state

Each user and lab gets its own directory under `groups/`. These directories contain Terraform state, so you can always `cd` into one and run `terraform` commands manually if you need to fix something without going through the tool. The `managed: false` flag formalizes this — marking a lab as unmanaged tells the tool to leave that directory completely alone.

---

## Requirements and configs setup

- Linux (no Windows support planned)
- Python 3
- Terraform in your system PATH

```bash
pip install -r requirements.txt
cp -r configs-example configs
```

---

## Setup

Configure your Proxmox connection in `configs/auth.yaml`:

```yaml
proxmox:
  endpoint: "https://your-proxmox:8006/"

  # Option 1: API token (cannot change user passwords)
  api_token: "user@pam!tokenid=uuid"

  # Option 2: username/password (required for password management)
  username: "root@pam"
  password: "yourpassword"

  insecure: false  # true to skip SSL verification
```

---

## Usage

```
python main.py -h
```

```
positional arguments:
  {change-password,parse-test,deploy-users,deploy-lab,destroy-lab,terraform-run,backup}
```

Every subcommand that makes changes supports `--plan` to preview what would happen without touching anything.

---

### deploy-users

Deploys or updates groups and users defined in `configs/users.yaml`. When you remove/comment a group or user from the config and run this command, the tool will detect the orphan, show you what would be destroyed, ask for confirmation, then remove it from Proxmox.

```bash
# Preview all changes including what orphans would be destroyed
python main.py deploy-users example-group --plan

# Apply changes (shows orphan plan and asks for confirmation before any deletion)
python main.py deploy-users example-group
```

**Important:** When a user or group is removed from the YAML, it will only be deleted from Proxmox if it has no active lab directories or other unknown directories. If labs (or other directories) still exist under `groups/example-group/users/UserEX/labs/`, the user will be protected from deletion.

See `configs/users.yaml` for full config format and options.

---

### deploy-lab

Deploys a lab for all eligible users across all groups. Reads which users get the lab from `configs/labs.yaml`, generates per-user Terraform workspaces, and applies them.

```bash
# Preview what would be created
python main.py deploy-lab example-lab --plan

# Deploy the lab
python main.py deploy-lab example-lab
```

Lab configs live in `configs/labs/<lab-name>/`. Each lab needs:
- `main.tf` — your Terraform resources (VMs, etc.)
- `variables.tf` — variable declarations (copy from example)
- `providers.tf` — provider requirements (copy from example)
- `main.yaml` — lab settings (networks, node, snapshot config)

See `configs/labs/example-lab/` for a fully documented example.

---

### destroy-lab

Destroys labs that have `destroy: true` set in `configs/labs.yaml`. Always shows a plan and asks for confirmation before destroying anything.

```bash
# Preview what would be destroyed
python main.py destroy-lab example-lab --plan

# Destroy (shows plan automatically, then asks: type 'destroy' to confirm)
python main.py destroy-lab example-lab
```

Labs with `managed: false` are always skipped — destroy them manually in their directory if needed.

---

### change-password

Regenerates and applies a new password for a user or all users in a group. If Terraform fails to apply the new password, the local file is automatically rolled back to the previous password.

```bash
# Change password for a single user
python main.py change-password example-group --user UserEX

# Change passwords for all users in a group
python main.py change-password example-group
```

> Requires username/password auth in `auth.yaml` — API tokens cannot change Proxmox user passwords.

---

### terraform-run

Runs arbitrary Terraform commands with auth already set up. Useful for manual operations like importing resources, removing state entries, or targeting specific resources.

Pass Terraform arguments after `--`.

**Mode 1: explicit directory**

Runs terraform directly in the given path. No config checks, no managed flag — you're pointing at a specific directory yourself.

```bash
python main.py terraform-run --dir groups/example-group/users/UserEX/labs/example-lab -- state list

python main.py terraform-run --dir groups/example-group/users/UserEX/labs/example-lab -- import proxmox_virtual_environment_vm.my-vm 47
```

**Mode 2: lab name (runs across all eligible users)**

Respects the `managed` flag — unmanaged labs are skipped unless `--force-managed` is specified.

```bash
# Run for all users in a lab
python main.py terraform-run --lab example-lab -- state list

# Scope to a specific group
python main.py terraform-run --lab example-lab --group example-group -- plan -target=proxmox_virtual_environment_vm.example-vm

# Scope to a specific user
python main.py terraform-run --lab example-lab --group example-group --user UserEX -- apply -auto-approve

# Override managed=false (use with caution)
python main.py terraform-run --lab example-lab --force-managed -- state list
```

---

### backup

Creates a timestamped ZIP archive of `configs/`, `passwords/`, and `groups/` (excluding `.terraform` provider caches).

```bash
python main.py backup
```

Archives are saved to `backups/`. Always run a backup before making large config changes.

---

### parse-test

Validates and prints the parsed `users.yaml` config. Useful for checking that inheritance, password policies, and internal-id uniqueness are all correct before deploying.

```bash
python main.py parse-test
python main.py parse-test --config configs/users.yaml
```

---

## Config files

| File | Purpose |
|------|---------|
| `configs/auth.yaml` | Proxmox connection and credentials |
| `configs/users.yaml` | Groups, users, password policies |
| `configs/labs.yaml` | Lab definitions, per-group/user access control |
| `configs/labs/<name>/main.yaml` | Network, node, and snapshot settings for a lab |
| `configs/labs/<name>/main.tf` | Terraform resources for the lab |

All config files contain inline documentation explaining every option.

---

## Internal IDs

Both users and labs require a unique `internal-id` integer. These IDs are used to generate network bridge names (`u{user_id}l{lab_id}n{net_index}`), which ensures each user gets isolated bridges that don't collide with other users.

**The tool validates ID uniqueness at startup and will refuse to run if duplicates are detected.**

- User IDs must be unique across all users in all groups
- Lab IDs must be unique across all labs
- IDs are safe to start from 1 (starting from 0 works but is not recommended)
- Once assigned, do not change an ID while a lab is deployed — it will change the bridge names and break the existing deployment

---

## Safety features

- **`--plan` on everything** — preview any operation before it runs
- **Destroy confirmation** — destructive operations show a plan first, then require typing `destroy` to confirm
- **`managed: false`** — tells the tool to never touch a specific lab directory, for manual overrides
- **`destroy: false`** (default) — protects labs from the destroy-lab command until explicitly set to true
- **Orphan protection** — users with active labs cannot be deleted; groups with active users cannot be deleted
- **Password rollback** — if a password change fails in Proxmox, the local file is restored to the previous value
- **Internal-id validation** — duplicate IDs are caught at config load time before any Terraform runs

---

## Workflow example

```bash
# 1. Configure auth
vim configs/auth.yaml

# 2. Define your groups and users
vim configs/users.yaml

# 3. Preview user deployment
python main.py deploy-users my-group --plan

# 4. Deploy users
python main.py deploy-users my-group

# 5. Configure your lab
vim configs/labs.yaml
vim configs/labs/my-lab/main.yaml
vim configs/labs/my-lab/main.tf

# 6. Preview lab deployment
python main.py deploy-lab my-lab --plan

# 7. Deploy lab
python main.py deploy-lab my-lab

# 8. Back up everything
python main.py backup
```

### TODO
- Add role creation module and role configuration through main.yaml config
- Add vars support to network comments in main.yaml of the lab
