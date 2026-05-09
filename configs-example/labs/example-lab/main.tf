# Calling for the basic provision, see yourself what it creates, it is absolutely required for normal functioning
module "base" {
  source          = "../../../../../../terraform/modules/base_lab_module"
  pool_id         = var.pool_id
  user_name       = var.user_name
  node_name       = var.pve_locals.node
  networks_config = var.networks
  permit          = var.permit
}

# Example VM creation, here with linked clone
resource "proxmox_virtual_environment_vm" "example-vm" {
  # Here we call pve-locals node variable
  node_name = var.pve_locals.node
  # VM name format that is being created on proxmox node
  name      = "EX-VM-${var.user_name}-${var.group_name}"
  pool_id   = module.base.pool_id

  # Linked clone VM-ID, just in this example for ease
  clone {
    vm_id = 100
    datastore_id = var.pve_locals.storage
  }

  # Network configuration, here you also should refer to lab specified network variables
  network_device {
    # Binding the bridge on vm
    bridge = module.base.bridge_names["net2"]
    model  = "e1000"
  }

  serial_device {}
  # Example tag with variables
  tags = ["${var.user_name}_${var.lab_name}"]
}

# Here we determine if snapshot will be created for vm, if you want it to be created the add a vm id to output on this specific name of the output
output "vm_snapshot_ids" {
  value = [proxmox_virtual_environment_vm.example-vm.vm_id]
}
