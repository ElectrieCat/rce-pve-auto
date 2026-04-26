terraform {
  required_providers {
    proxmox = { source = "bpg/proxmox" }
  }
}

# Создаем пул ресурсов
resource "proxmox_virtual_environment_pool" "pool" {
  pool_id = var.pool_id
  comment = "Lab managed by automation for ${var.user_name}"
}

# Вызываем сетевой модуль
module "network" {
  source          = "../network_module"
  node_name       = var.node_name
  networks_config = var.networks_config
}

resource "proxmox_acl" "pool_access" {
  user_id = "${var.user_name}@pve"
  path    = "/pool/${proxmox_virtual_environment_pool.pool.pool_id}"

  # Если permit=true, даем права пользователя ВМ, иначе - NoAccess
  role_id = var.permit ? "PVEPoolUser" : "NoAccess"

  # Ждем, когда создастся пул, прежде чем вешать на него права
  depends_on = [proxmox_virtual_environment_pool.pool]
}

output "bridge_names" { value = module.network.bridge_names }
output "pool_id"      { value = proxmox_virtual_environment_pool.pool.pool_id }