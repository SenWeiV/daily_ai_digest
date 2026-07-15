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

如需在本地保留部署变量，可复制仓库根目录的 `.env.local.example` 为 `.env.local`，然后在执行命令前加载：

```bash
set -a
source .env.local
set +a
```

### 1. 上传代码到云服务器

将 `news_from_github_youtube` 目录上传到云服务器的 `/opt/` 目录：

```bash
# 在本地执行，将代码上传到服务器
scp -P "${DIGEST_DEPLOY_SSH_PORT:-22}" -r news_from_github_youtube \
  "${DIGEST_DEPLOY_SSH_USER}@${DIGEST_DEPLOY_SSH_HOST}:/opt/"
```

### 2. 登录服务器并进入目录

```bash
ssh -p "${DIGEST_DEPLOY_SSH_PORT:-22}" \
  "${DIGEST_DEPLOY_SSH_USER}@${DIGEST_DEPLOY_SSH_HOST}"
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
GEMINI_API_KEY=<your-kimi-api-key>
GEMINI_BASE_URL=https://api.moonshot.cn/v1
GEMINI_MODEL=moonshot-v1-8k

# GitHub Token 与研究内容发现
GITHUB_TOKEN=<your-github-token>
GITHUB_CANDIDATE_LIMIT=24
GITHUB_NEW_PROJECT_DAYS=14
GITHUB_SEARCH_QUERIES=

# arXiv 与动态选择（A 优先，B 仅补足目标，不使用 C 填充）
ARXIV_CATEGORIES=cs.AI,cs.CL,cs.CV,cs.LG,cs.IR
ARXIV_CANDIDATE_LIMIT=24
ARXIV_TIMEOUT_SECONDS=20
TARGET_ITEMS=10
MAX_ITEMS=24

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
- 健康检查：`http://<your-server-host>:8000/health`
- API 文档：`http://<your-server-host>:8000/docs`

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
# 通用方式：使用脚本（会自动拉取代码并重建）
./deploy-docker.sh update

# 生产小范围更新：只重建并替换 backend，保留 data volume
git rev-parse HEAD
git pull --ff-only
docker compose up -d --build --no-deps backend

docker compose ps backend
curl --fail http://127.0.0.1:8000/health
docker compose logs --since=10m backend | grep -E '数据库初始化完成|定时任务调度器启动|摘要生成完成'
```

发布前先用 `docker ps --filter name=daily-ai-digest-backend` 确认权威运行时确实是 Compose 容器；如果生产机实际由 `daily-ai-digest.service` 管理，不要同时启动容器，应按 systemd 流程更新。日志验证应出现 GitHub、arXiv、YouTube 三源计数，且定时任务的下一次执行时间符合 `TIMEZONE`、`SCHEDULE_HOUR` 和 `SCHEDULE_MINUTE`。

## 🛠️ 故障排查

### 问题1：容器无法启动

```bash
# 查看详细错误日志
docker-compose logs backend

# 只检查必要变量是否存在，不输出密钥值
docker exec daily-ai-digest-backend python -c "import os; print({k: bool(os.getenv(k)) for k in ('GEMINI_API_KEY', 'GITHUB_TOKEN', 'EMAIL_PASSWORD')})"
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
