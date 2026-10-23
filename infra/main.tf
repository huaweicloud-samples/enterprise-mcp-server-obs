# ---------------------------------------------------------------------------
# 对象存储桶
# ---------------------------------------------------------------------------
resource "huaweicloud_obs_bucket" "this" {
  bucket = var.bucket_name

  # 运行期常被外部工具 / 控制台改写的字段，交给运行期管理，
  # 避免下一次 apply 静默回滚线上状态（对应 C10）。
  lifecycle {
    ignore_changes = [
      tags,
      lifecycle_rule,
      versioning,
    ]
  }
}

# ---------------------------------------------------------------------------
# 专用于 MCP 服务的 IAM 身份与只读策略
# ---------------------------------------------------------------------------
resource "huaweicloud_iam_user" "mcp" {
  name     = "${var.bucket_name}-mcp-user"
  enabled  = true
  password = "" # 仅用于编程访问（AK/SK），不设置控制台登录密码
}

data "huaweicloud_identity_info" "current" {}

resource "huaweicloud_iam_policy" "obs_readonly" {
  name        = "${var.bucket_name}-obs-readonly"
  description = "只读访问指定 OBS 桶，供对象存储 MCP 服务使用"
  policy = jsonencode({
    Version = "1.1"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "obs:bucket:ListBucket",
          "obs:bucket:GetBucket",
          "obs:object:GetObject",
          "obs:object:ListObjects",
        ]
        Resource = [
          "obs:*:*:*:<bucket_name>",
          "obs:*:*:*:<bucket_name>/*",
        ]
      }
    ]
  })
}

resource "huaweicloud_iam_user_policy_attachment" "attach" {
  user      = huaweicloud_iam_user.mcp.name
  policy_id = huaweicloud_iam_policy.obs_readonly.id
}

# 访问密钥（secret 为敏感输出，请在本地 .env 中引用，切勿提交）
resource "huaweicloud_iam_access_key" "mcp" {
  user_id = huaweicloud_iam_user.mcp.id
}
