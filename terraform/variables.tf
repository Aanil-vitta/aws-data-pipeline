variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefix used for naming all resources"
  type        = string
  default     = "csv-etl-pipeline"
}

variable "alert_email" {
  description = "Email address to receive CloudWatch alarm notifications"
  type        = string
  default     = "you@example.com"
}

variable "environment" {
  description = "Deployment environment tag"
  type        = string
  default     = "dev"
}
