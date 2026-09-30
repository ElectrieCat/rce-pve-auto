# Minimal lab: required base module (pool + networks + ACL).
# Do not remove this block — it creates the per-user pool and bridges.
module "base" {
  source          = "../../../../../../terraform/modules/base_lab_module"
  pool_id         = var.pool_id
  user_name       = var.user_name
  node_name       = var.pve_locals.node
  networks_config = var.networks
  permit          = var.permit
}

# Single VM from a template (linked clone).
resource "proxmox_virtual_environment_vm" "lab-vm" {
  node_name = var.pve_locals.node
  name      = "LAB-${var.user_name}-${var.group_name}"
  pool_id   = module.base.pool_id

  clone {
    # TODO: replace with the VMID of your template on var.pve_locals.node
    vm_id = 100
    # Linked clones live on the same storage as the template:
    # keep datastore_id commented out.
    #datastore_id = var.pve_locals.storage
  }

  network_device {
    # Key must match a network from main.yaml (here: "lab-net")
    bridge = module.base.bridge_names["lab-net"]
    model  = "virtio"
  }

  serial_device {}
  tags = ["${var.user_name}_${var.lab_name}"]
}

# Snapshots are disabled in main.yaml, so the list is empty.
# When you enable snapshots, put the VM id here:
#   value = [proxmox_virtual_environment_vm.lab-vm.vm_id]
output "vm_snapshot_ids" {
  value = []
}

# Gives the student PVEVMUser on their own pool (console, power mgmt).
resource "proxmox_acl" "acl" {
  path    = "/pool/${var.pool_id}"
  role_id = "PVEVMUser"
  user_id = "${var.user_name}@pve"
}
