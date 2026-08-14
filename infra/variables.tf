variable "aws_region" {
  description = "Região principal da carga de trabalho."
  type        = string
  default     = "sa-east-1"
}

variable "environment" {
  description = "Ambiente lógico."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "environment deve ser dev, staging ou production."
  }
}

variable "project_name" {
  description = "Prefixo estável usado em nomes e tags."
  type        = string
  default     = "croquitodxf"

  validation {
    condition     = can(regex("^[a-z0-9-]{3,24}$", var.project_name))
    error_message = "project_name deve conter apenas letras minúsculas, números e hífen."
  }
}

variable "artifact_retention_days" {
  description = "Retenção de uploads, renders e exportações efêmeras."
  type        = number
  default     = 7

  validation {
    condition     = var.artifact_retention_days >= 1 && var.artifact_retention_days <= 30
    error_message = "artifact_retention_days deve estar entre 1 e 30."
  }
}

variable "web_origin" {
  description = "Origem única autorizada a enviar uploads assinados diretamente ao bucket."
  type        = string

  validation {
    condition     = can(regex("^https?://[^/]+$", var.web_origin))
    error_message = "web_origin deve ser uma origem HTTP(S), sem caminho."
  }
}
