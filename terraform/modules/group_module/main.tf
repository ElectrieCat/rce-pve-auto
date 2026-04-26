terraform {
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
    }
  }
}

resource "proxmox_virtual_environment_group" "student_group" {
  group_id = var.group_name
  comment  = var.comment
}