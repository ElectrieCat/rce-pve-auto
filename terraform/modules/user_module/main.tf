terraform {
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
    }
  }
}

resource "proxmox_virtual_environment_user" "student_user" {
  user_id  = "${var.username}@pve"
  password = var.password
  enabled  = var.enabled
  comment  = var.comment != "" ? var.comment : "Managed by automation tool"
  groups   = var.groups
}