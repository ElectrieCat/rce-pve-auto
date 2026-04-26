variable "username" {
  description = "The username in Proxmox"
  type        = string
}

variable "password" {
  description = "The password for the user"
  type        = string
  sensitive   = true
}

variable "enabled" {
  description = "Account status"
  type        = bool
  default     = true
}

variable "comment" {
  description = "Optional comment"
  type        = string
  default     = ""
}

variable "groups" {
  description = "List of groups the user belongs to"
  type        = list(string)
  default     = []
}

variable "internal_id" {
  description = "User internal id for network naming"
  type        = number
  default     = 0
}