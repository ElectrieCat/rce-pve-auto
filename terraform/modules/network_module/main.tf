terraform {
  required_providers {
    proxmox = { source = "bpg/proxmox" }
    time    = { source = "hashicorp/time" }
  }
}

resource "proxmox_network_linux_bridge" "local_bridges" {
  for_each = { for k, v in var.networks_config : k => v if v.type == "local-bridge" }

  node_name  = var.node_name
  name       = each.value.real_name
  comment    = each.value.comment
  mtu        = each.value.mtu
  autostart  = each.value.autostart
  vlan_aware = each.value.vlan_aware

  # vids is only meaningful when vlan_aware is true. When vlan_aware is false
  # the attribute is omitted entirely to avoid sending an empty/irrelevant value.
  vids = each.value.vlan_aware ? each.value.vids : null

  ports = each.value.bridge_ports != "" ? split(",", replace(each.value.bridge_ports, " ", "")) : []

  address  = each.value.ipv4_cidr
  gateway  = each.value.ipv4_gw
  address6 = each.value.ipv6_cidr
  gateway6 = each.value.ipv6_gw
}

# Artificial delay after bridge creation to prevent Proxmox API throttling
# before the VM provisioning stage begins.
resource "time_sleep" "wait_after_network" {
  depends_on      = [proxmox_network_linux_bridge.local_bridges]
  create_duration = var.inter_resource_delay
}

output "bridge_names" {
  value      = { for k, v in proxmox_network_linux_bridge.local_bridges : k => v.name }
  depends_on = [time_sleep.wait_after_network]
}
