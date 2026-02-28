# Daily AI Digest - Docker 容器化部署指南

> 本文档介绍如何使用 Docker 将 Daily AI Digest 后端服务部署到云服务器中，实现环境隔离。

## 🎯 目标

- **环境隔离**：将此工具与其他工具完全隔离，避免依赖冲突
- **独立运行**：每个工具有自己的容器、网络和存储空间
- **易于管理**：使用 Docker Compose 统一管理服务的启动、停止和更新

## 📁 新增文件说明

```
news_from_github_youtube/
├── Dockerfile.backend          # 后端服务 Docker 镜像定义
├── docker-compose.yml          # Docker Compose 编排配置
├── .env.example.docker         # Docker 部署环境变量模板
├── deploy-docker.sh            # 一键部署脚本（已添加执行权限）
└── DOCKER_DEPLOY_GUIDE.md      # 本指南
```

## 🚀 快速开始

### 1. 上传代码到云服务器

将 `news_from_github_youtube` 目录上传到云服务器的 `/opt/` 目录：

```bash
# 在本地执行，将代码上传到服务器
scp -r news_from_github_youtube ${DIGEST_DEPLOY_SSH_USER}@${DIGEST_DEPLOY_SSH_HOST}:/opt/
```

### 2. 登录服务器并进入目录

```bash
ssh ${DIGEST_DEPLOY_SSH_USER}@${DIGEST_DEPLOY_SSH_HOST}
cd /opt/news_from_github_youtube
```

### 3. 初始化环境配置

```bash
./deploy-docker.sh setup
```

这会创建 `.env` 文件和数据目录。然后编辑 `.env` 文件填入你的 API 密钥：

```bash
nano .env
```

**关键配置项：**

```env
# LLM API 配置（推荐 Kimi，国内直连）
GEMINI_API_KEY=sk-your-kimi-api-key
GEMINI_BASE_URL=https://api.moonshot.cn/v1
GEMINI_MODEL=moonshot-v1-8k

# GitHub Token
GITHUB_TOKEN=ghp_your_github_token

# Gmail SMTP（用于发送邮件摘要）
GMAIL_SENDER=your_email@gmail.com
GMAIL_APP_PASSWORD=your_16_char_app_password
DIGEST_RECIPIENT=your_email@gmail.com
```

### 4. 构建并启动服务

```bash
# 构建 Docker 镜像
./deploy-docker.sh build

# 启动服务
./deploy-docker.sh start
```

### 5. 验证部署

```bash
# 查看服务状态
./deploy-docker.sh status

# 测试健康检查
./deploy-docker.sh test

# 查看日志
./deploy-docker.sh logs
```

访问以下地址验证：
- 健康检查：`${DIGEST_HEALTHCHECK_URL}`
- API 文档：`${DIGEST_API_DOCS_URL}`

## 📋 常用命令

| 命令 | 说明 |
|------|------|
| `./deploy-docker.sh setup` | 初始化环境配置 |
| `./deploy-docker.sh build` | 构建 Docker 镜像 |
| `./deploy-docker.sh start` | 启动服务 |
| `./deploy-docker.sh stop` | 停止服务 |
| `./deploy-docker.sh restart` | 重启服务 |
| `./deploy-docker.sh status` | 查看服务状态 |
| `./deploy-docker.sh logs` | 查看实时日志 |
| `./deploy-docker.sh update` | 更新代码并重新部署 |
| `./deploy-docker.sh clean` | 清理所有 Docker 资源 |
| `./deploy-docker.sh test` | 运行健康检查测试 |

## 🔧 直接 Docker 命令（可选）

如果你更喜欢直接使用 Docker 命令：

```bash
# 构建并启动
docker-compose up -d --build

# 查看日志
docker-compose logs -f backend

# 停止服务
docker-compose down

# 进入容器内部调试
docker exec -it daily-ai-digest-backend bash

# 查看容器状态
docker ps | grep daily-ai-digest
```

## 📂 数据持久化

- **SQLite 数据库**：`./data/digest.db` → 容器内的 `/app/data/digest.db`
- **日志文件**：自动写入 `./data/runtime/` 目录
- **备份建议**：定期备份 `data/` 目录

## 🌐 端口映射

- 容器内端口：`8000`
- 宿主机映射：`8000:8000`
- 如需修改，编辑 `docker-compose.yml` 中的 `ports` 配置

## 🔒 环境隔离优势

1. **依赖隔离**：Python 包、系统库都在容器内，不影响宿主机
2. **网络隔离**：独立的 Docker 网络，可与其他工具完全隔离
3. **资源限制**：可通过 Docker 限制 CPU/内存使用
4. **快速回滚**：有问题时快速重建容器即可

## 🔄 更新部署

当代码有更新时：

```bash
# 方式一：使用脚本（会自动拉取代码并重建）
./deploy-docker.sh update

# 方式二：手动步骤
git pull                    # 拉取最新代码
./deploy-docker.sh build    # 重新构建镜像
./deploy-docker.sh restart  # 重启服务
```

## 🛠️ 故障排查

### 问题1：容器无法启动

```bash
# 查看详细错误日志
docker-compose logs backend

# 检查环境变量是否正确加载
docker exec daily-ai-digest-backend env | grep GEMINI
```

### 问题2：API 无法访问

```bash
# 检查端口是否被占用
netstat -tlnp | grep 8000

# 检查防火墙设置
ufw status

# 检查容器状态
docker ps -a
```

### 问题3：LLM API 连接失败

进入容器内测试：

```bash
docker exec -it daily-ai-digest-backend bash
python -c "
import httpx
response = httpx.get('https://api.moonshot.cn/v1')
print(response.status_code)
"
```

## 📊 与现有 systemd 方案对比

| 特性 | Docker 方案 | systemd 方案 |
|------|-------------|--------------|
| 环境隔离 | ✅ 完全隔离 | ❌ 共享环境 |
| 依赖管理 | ✅ 容器内自包含 | ⚠️ 需虚拟环境 |
| 多工具共存 | ✅ 互不干扰 | ⚠️ 可能冲突 |
| 资源占用 | ⚠️ 略高 | ✅ 较低 |
| 学习成本 | ⚠️ 需要 Docker 知识 | ✅ 简单 |
| 快速回滚 | ✅ 重建容器即可 | ⚠️ 需手动恢复 |

## 📝 注意事项

1. **首次部署**：必须先运行 `./deploy-docker.sh setup` 创建 `.env` 文件
2. **API 密钥**：确保使用公网可访问的 LLM API（如 Kimi、DeepSeek），不要使用内网地址
3. **数据备份**：定期备份 `data/` 目录，防止数据丢失
4. **端口冲突**：如果 8000 端口被占用，修改 `docker-compose.yml` 中的端口映射

## 🎉 完成！

现在你的 Daily AI Digest 服务已经运行在独立的 Docker 容器中，与其他工具完全隔离。你可以在同一台服务器上部署其他工具，它们之间不会相互影响。
