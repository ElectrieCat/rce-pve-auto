import json
import subprocess
from urllib.parse import urlparse  # <-- Добавь этот импорт!
from proxmoxer import ProxmoxAPI
from python.parser import load_auth_config


def get_proxmox_api():
    """Инициализируем клиент Proxmox API, используя auth.yaml"""
    auth = load_auth_config()
    if not auth:
        print("[ERROR] Auth config not found or invalid.")
        return None

    endpoint = auth.get("endpoint", "")

    # Добавляем схему, если её нет, чтобы urlparse отработал корректно
    if "://" not in endpoint:
        endpoint = "https://" + endpoint

    # Парсим URL надежным системным методом
    parsed_url = urlparse(endpoint)
    host = parsed_url.hostname
    port = parsed_url.port or 443  # Если порт не указан в auth.yaml, берем 8006

    insecure = auth.get("insecure", True)
    api_token = auth.get("api_token")
    username = auth.get("username")
    password = auth.get("password")

    if not host:
        print("[ERROR] PVE endpoint not specified or invalid in auth config.")
        return None

    try:
        if api_token:
            # Ожидаем формат: user@realm!token_name=token_value
            user_and_name, token_value = api_token.split('=')
            user, token_name = user_and_name.split('!')

            proxmox = ProxmoxAPI(
                host,
                port=port,  # <-- Теперь явно передаем правильный порт
                user=user,
                token_name=token_name,
                token_value=token_value,
                verify_ssl=not insecure
            )
        elif username and password:
            # Используем классический логин/пароль
            proxmox = ProxmoxAPI(
                host,
                port=port,  # <-- И здесь тоже
                user=username,
                password=password,
                verify_ssl=not insecure
            )
        else:
            print("[ERROR] Neither API token nor username/password found in auth config.")
            return None

        return proxmox
    except Exception as e:
        print(f"[ERROR] Failed to initialize Proxmox API: {e}")
        return None


def get_terraform_vm_ids(lab_dir):
    """Выполняет terraform output -json и достает ID виртуалок"""
    try:
        # Важно: прокидываем PATH и базовые ENV, чтобы subprocess нашел terraform
        cmd = ["terraform", f"-chdir={lab_dir}", "output", "-json"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        outputs = json.loads(result.stdout)

        if "vm_snapshot_ids" in outputs:
            vm_data = outputs["vm_snapshot_ids"].get("value")

            if isinstance(vm_data, dict):
                return list(vm_data.values())
            elif isinstance(vm_data, list):
                return vm_data
            elif isinstance(vm_data, (int, str)):
                return [vm_data]

        print(f"[WARNING] No valid 'vm_ids' output found in {lab_dir}. Cannot create snapshots.")
        return []
    except Exception as e:
        print(f"[ERROR] Failed to get Terraform outputs from {lab_dir}: {e}")
        return []


def create_initial_snapshot(lab_dir, node_name, snap_name="CLEAR", description="Auto Snapshot", include_ram=False):
    """Основная функция: проверяет и создает снапшот для всех ВМ в папке"""
    vm_snapshot_ids = get_terraform_vm_ids(lab_dir)
    if not vm_snapshot_ids:
        return
    proxmox = get_proxmox_api()
    if not proxmox:
        return

    # Принудительно преобразуем include_ram в bool,
    # чтобы избежать передачи строки 'False' или 'True'
    include_ram = bool(include_ram)

    for vm_snapshot_id in vm_snapshot_ids:
        try:
            snapshots = proxmox.nodes(node_name).qemu(vm_snapshot_id).snapshot.get()
            existing_snaps = [s['name'] for s in snapshots]
            if snap_name in existing_snaps:
                print(f"[SKIP] Snapshot '{snap_name}' already exists for VM {vm_snapshot_id}")
            else:
                print(f"[*] Creating snapshot '{snap_name}' for VM {vm_snapshot_id}. RAM included: {include_ram}. Please wait...")
                proxmox.nodes(node_name).qemu(vm_snapshot_id).snapshot.post(
                    snapname=snap_name,
                    description=description,
                    vmstate=int(include_ram)   # теперь точно bool
                )
                print(f"[SUCCESS] Snapshot created for VM {vm_snapshot_id}")
        except Exception as e:
            print(f"[ERROR] Could not create snapshot for VM {vm_snapshot_id}: {e}")