terraform {
  required_providers {
    proxmox = { source = "bpg/proxmox" }
    time    = { source = "hashicorp/time" }
  }
}

# Создаем локальные мосты
resource "proxmox_network_linux_bridge" "local_bridges" {
  # Фильтруем только тип local-bridge
  for_each = { for k, v in var.networks_config : k => v if v.type == "local-bridge" }

  node_name = var.node_name
  name      = each.value.real_name

  comment    = each.value.comment
  mtu        = each.value.mtu
  # not yet possible due to bpg limitations
  # vlan_aware = each.value.vlan_aware
  # vlan_id    = each.value.vlan_id
  autostart  = each.value.autostart

  # Превращаем строку "vmbr1, vmbr2" в список ["vmbr1", "vmbr2"]
  ports = each.value.bridge_ports != "" ? split(",", replace(each.value.bridge_ports, " ", "")) : []

  address  = each.value.ipv4_cidr
  gateway  = each.value.ipv4_gw
  address6 = each.value.ipv6_cidr
  gateway6 = each.value.ipv6_gw
}

# Ресурс для создания искусственной задержки
# Он "засыпает" после того, как мосты созданы,
# чтобы следующая стадия (виртуалки) не ломала API
resource "time_sleep" "wait_after_network" {
  depends_on = [proxmox_network_linux_bridge.local_bridges]
  create_duration = var.inter_resource_delay
}

# Заглушка для SDN (появится позже)
# resource "proxmox_virtual_environment_sdn_vnet" "sdn_vnets" {
#   for_each = { for k, v in var.networks_config : k => v if v.type == "sdn-bridge" }
#   ...
# }

output "bridge_names" {
  value = { for k, v in proxmox_network_linux_bridge.local_bridges : k => v.name }
  # Важно: дожидаемся окончания таймера перед тем как отдавать имена
  depends_on = [time_sleep.wait_after_network]
}