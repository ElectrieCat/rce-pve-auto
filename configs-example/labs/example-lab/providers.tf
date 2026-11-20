terraform {
  required_providers {
    proxmox = {
      source = "bpg/proxmox"
      # Pin to the version you tested against, e.g. version = ">= 0.70.0"
    }
  }
}
# Copy this file as-is into every new lab in configs/labs/<name>/