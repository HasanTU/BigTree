variable "aws_region" {
  description = "AWS region for deployment (Bangkok/Singapore is lowest latency)"
  type        = string
  default     = "ap-southeast-1"
}

variable "project_name" {
  description = "Base project identifier"
  type        = string
  default     = "dubaimai"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "default_start_date" {
  description = "Default start date for weather queries (YYYY-MM-DD)"
  type        = string
  default     = "2023-04-01"
}

variable "default_end_date" {
  description = "Default end date for weather queries (YYYY-MM-DD)"
  type        = string
  default     = "2023-04-30"
}

variable "schedule_cron" {
  description = "Optional EventBridge cron expression to trigger weather ingestion automatically"
  type        = string
  default     = "" # Empty means manual trigger only
}
