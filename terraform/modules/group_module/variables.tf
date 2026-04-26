variable "group_name" {
  description = "The name of the group in Proxmox"
  type        = string
}

variable "comment" {
  description = "Optional comment for the group"
  type        = string
  default     = "Managed by automation tool"
}