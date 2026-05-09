terraform {
  required_providers {
    proxmox = {
      source = "bpg/proxmox"
    }
  }
}

resource "proxmox_virtual_environment_user" "student_user" {
  user_id  = "${var.username}@pve"
  password = var.password
  enabled  = var.enabled
  comment  = var.comment != "" ? var.comment : "Managed by automation tool"
  groups   = var.groups

  lifecycle {
    # ACL entries on this user are managed by base_lab_module (via proxmox_acl).
    # Ignoring them here prevents deploy-users from stripping lab pool permissions
    # every time it runs.
    ignore_changes = [acl]
  }
}
