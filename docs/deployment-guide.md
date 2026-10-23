# 部署指导书：对象存储 MCP 服务（OBS MCP Server）

本文档说明如何在华为云环境部署并运行对象存储 MCP 服务。

## 前置条件

- 已开通华为云账号，并在目标区域（默认 `cn-north-4`）开通对象存储（OBS）服务。
- 已创建用于本服务的 IAM 凭据（访问密钥），并具备目标桶的读取权限。
- 本地环境：Python ≥ 3.12、`uv`（推荐）或 `pip`。

## 步骤一：准备凭据

复制环境变量模板并填入占位符对应的真实值（**仅用于本地运行，禁止提交**）：

```bash
cp env.example .env
# 编辑 .env，设置 HW_ACCESS_KEY / HW_SECRET_KEY / OBS_REGION / OBS_BUCKETS
```

## 步骤二：安装依赖

```bash
uv sync
# 或： pip install -e .
```

## 步骤三：创建对象存储资源（可选，使用 Terraform）

仓库 `infra/` 目录下提供了华为云 Terraform 模板，可一键创建：

- 一个 OBS 桶；
- 一个专用于本服务的 IAM 用户、访问密钥与只读策略。

```bash
cd infra
terraform init
terraform apply \
  -var="bucket_name=my-obs-mcp-bucket" \
  -var="hw_access_key=$HW_ACCESS_KEY" \
  -var="hw_secret_key=$HW_SECRET_KEY"
```

执行成功后，`terraform output` 会给出 `access_key_id` 与 `secret_access_key`（敏感输出）。将后者写入本地 `.env` 的 `HW_ACCESS_KEY` / `HW_SECRET_KEY`。

> 费用提示：OBS 桶与 IAM 用户为空闲时近乎零成本；`terraform destroy` 可随时释放，避免持续计费。

## 步骤四：挂载到 MCP 客户端

在客户端配置文件中加入（开发模式）：

```json
{
  "mcpServers": {
    "obs-mcp-server": {
      "command": "uv",
      "args": ["--directory", "/path/to/obs-mcp-server", "run", "obs-mcp-server"]
    }
  }
}
```

## 步骤五：验证

启动客户端后，向模型提问「列出你的对象存储桶」或「读取桶 xxx 中文件 yyy 的内容」，确认服务返回正确结果。也可使用仓库内置调试客户端：

```bash
python src/client.py
```

## 清理

```bash
cd infra && terraform destroy
```
