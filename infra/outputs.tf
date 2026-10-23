output "bucket_name" {
  description = "创建的对象存储桶名称"
  value       = huaweicloud_obs_bucket.this.bucket
}

output "access_key_id" {
  description = "MCP 服务使用的访问密钥 ID"
  value       = huaweicloud_iam_access_key.mcp.access_key
}

output "secret_access_key" {
  description = "MCP 服务使用的私密访问密钥（敏感，请写入本地 .env）"
  value       = huaweicloud_iam_access_key.mcp.secret_key
  sensitive   = true
}
