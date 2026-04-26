variable "node_name" { type = string }

variable "networks_config" {
  type = map(object({
    real_name    = string
    type         = string
    autostart    = bool
    # not yet possible due to bpg limitations
    #vlan_aware   = bool
    #vlan_id      = string
    mtu          = number
    bridge_ports = string
    comment      = string
    ipv4_cidr    = string
    ipv4_gw      = string
    ipv6_cidr    = string
    ipv6_gw      = string
  }))
}

variable "inter_resource_delay" {
  type        = string
  default     = "2s"
  description = "Delay after each bridge creation to prevent API throttling"
}