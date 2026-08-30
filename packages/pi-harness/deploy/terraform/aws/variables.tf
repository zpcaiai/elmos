variable "account_id" {
  description = "Exact AWS account authorized for this deployment."
  type        = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must contain exactly 12 digits."
  }
}

variable "region" {
  description = "Exact AWS region authorized for this deployment."
  type        = string
  validation {
    condition     = can(regex("^[a-z]{2}(-gov)?-[a-z]+-[0-9]+$", var.region))
    error_message = "region must be an explicit AWS region."
  }
}

variable "environment" {
  type = string
  validation {
    condition     = contains(["staging", "production", "dr"], var.environment)
    error_message = "environment must be staging, production, or dr."
  }
}

variable "release_id" {
  description = "Immutable release UUID used for final snapshots and provenance."
  type        = string
  validation {
    condition     = can(regex("^[0-9a-fA-F-]{36}$", var.release_id))
    error_message = "release_id must be a UUID."
  }
}

variable "vpc_id" {
  type = string
}

variable "database_subnet_ids" {
  type = list(string)
  validation {
    condition     = length(var.database_subnet_ids) >= 2
    error_message = "at least two database subnets are required."
  }
}

variable "application_security_group_id" {
  type = string
}

variable "postgresql_engine_version" {
  description = "Exact approved PostgreSQL engine version, for example 16.6."
  type        = string
  validation {
    condition     = can(regex("^1[6-9]\\.[0-9]+$", var.postgresql_engine_version))
    error_message = "PostgreSQL engine version must be an exact supported 16+ minor."
  }
}

variable "database_instance_class" {
  type = string
}

variable "database_allocated_storage_gib" {
  type = number
  validation {
    condition     = var.database_allocated_storage_gib >= 100
    error_message = "production storage must be at least 100 GiB."
  }
}

variable "backup_retention_days" {
  type    = number
  default = 35
  validation {
    condition     = var.backup_retention_days >= 7 && var.backup_retention_days <= 35
    error_message = "backup retention must be between 7 and 35 days."
  }
}

variable "evidence_retention_days" {
  description = "Immutable external-evidence retention period."
  type        = number
  default     = 365
  validation {
    condition     = var.evidence_retention_days >= 90 && var.evidence_retention_days <= 3650
    error_message = "evidence retention must be between 90 and 3650 days."
  }
}

variable "evidence_retention_mode" {
  description = "S3 Object Lock mode. Production policy should use COMPLIANCE."
  type        = string
  default     = "COMPLIANCE"
  validation {
    condition     = contains(["COMPLIANCE", "GOVERNANCE"], var.evidence_retention_mode)
    error_message = "evidence retention mode must be COMPLIANCE or GOVERNANCE."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}
