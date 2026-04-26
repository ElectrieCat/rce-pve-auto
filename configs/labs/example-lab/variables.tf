variable "user_name" { type = string }
variable "group_name" { type = string }
variable "lab_name" { type = string }
variable "pool_id" { type = string }
variable "permit" { type = bool }

variable "pve_locals" {
  type = object({
    storage = string
    node    = string
  })
}

variable "networks" {
  type = any # Используем any для гибкости, либо опиши структуру подробно
}
