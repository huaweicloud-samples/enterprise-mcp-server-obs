terraform {
  required_version = ">= 1.5"

  required_providers {
    huaweicloud = {
      source  = "huaweicloud/huaweicloud"
      version = ">= 1.50.0"
    }
  }
}

# 凭据默认从环境变量 HW_ACCESS_KEY / HW_SECRET_KEY 读取（不在此硬编码）。
# 若需显式传入，请通过 -var 或在 CI 中注入，切勿提交真实值。
provider "huaweicloud" {
  region = var.region
  # access_key / secret_key 省略 -> 自动读取环境变量
}
