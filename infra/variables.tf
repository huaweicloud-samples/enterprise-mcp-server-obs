variable "region" {
  description = "华为云目标区域"
  type        = string
  default     = "cn-north-4"
}

variable "bucket_name" {
  description = "要创建的对象存储桶名称（全局唯一）"
  type        = string
}

variable "hw_access_key" {
  description = "访问密钥 ID（建议留空，由环境变量 HW_ACCESS_KEY 注入）"
  type        = string
  default     = ""
  sensitive   = false
}

variable "hw_secret_key" {
  description = "私密访问密钥（建议留空，由环境变量 HW_SECRET_KEY 注入）"
  type        = string
  default     = ""
  sensitive   = true
}
