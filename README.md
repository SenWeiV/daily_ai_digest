# 🤖 Daily AI Digest

> 每日AI情报摘要系统 - 自动从 GitHub 和 arXiv 获取 AI 领域热点内容，通过大模型深度分析后，以邮件形式发送每日情报摘要。

![Daily AI Digest](https://img.shields.io/badge/version-1.2.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-green.svg)
![React](https://img.shields.io/badge/react-18.x-61dafb.svg)
![License](https://img.shields.io/badge/license-MIT-yellow.svg)

## 🌐 线上部署

- **前端**: https://senweiv.github.io/daily_ai_digest/
- **后端 API**: 通过 `VITE_API_BASE_URL` 指向你的部署地址
- **API 文档**: `http://<your-server-host>:8000/docs`

## ✨ 功能特性

- 🐙 **GitHub Agent**: 自动检索AI/Agent领域最热门的Top 10项目，深度阅读README和核心代码
- 🧠 **LLM 分析**: 默认 DeepSeek V4 Flash，也支持 Kimi、通义千问、Gemini 等 OpenAI 兼容接口
- 📧 **邮件推送**: 精美HTML格式的每日摘要邮件，随时随地获取情报
- ⏰ **定时执行**: 每天 08:30 整理前一天的内容，09:00 发送，也支持手动触发
- 🖥️ **可视化看板**: React前端界面，查看历史数据和详细分析
- 🇨🇳 **国内友好**: 支持国内大模型API，无需代理即可运行

> 当前来源为 GitHub 和 arXiv。YouTube 已停用；历史兼容字段和部分旧依赖仍保留。

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端展示层 (React)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  数据看板   │  │  历史记录   │  │   配置管理/手动触发     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │ REST API
┌─────────────────────────────────────────────────────────────────┐
│                      后端服务层 (FastAPI)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ 调度服务    │  │ API接口     │  │   邮件服务              │  │
│  │ APScheduler │  │ /api/*      │  │   Gmail SMTP            │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                       AI Agent 核心层                            │
│  ┌──────────────────┐  ┌──────────────────────────────────────┐ │
│  │ GitHub Agent     │  │ arXiv Agent (官方论文源)            │ │
│  │ - 趋势检索       │  │ - 论文检索                           │ │
│  │ - 仓库内容爬取   │  │ - 分类聚合与去重                      │ │
│  │ - 代码文件分析   │  │ - 论文方法与结果分析                       │ │
│  └──────────────────┘  └──────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │            LLM 分析引擎 (DeepSeek/Kimi/通义/Gemini)          ││
│  └──────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

## 📋 前置要求

- Python 3.11+
- Node.js 18+
- pnpm / npm / yarn

## 🚀 快速开始

## 🌐 线上部署（GitHub Pages + 云服务器）

### 前端（GitHub Pages）

- Pages 地址：`https://senweiv.github.io/daily_ai_digest/`
- 本仓库已内置 GitHub Actions 工作流，会在 `frontend/**` 更新时自动构建并发布。

#### 配置前端访问后端（必须）

在仓库 `Settings → Secrets and variables → Actions → Variables` 新增：

- `VITE_API_BASE_URL`：后端 API 根路径（包含 `/api`）
  - 示例：`https://your-api-host.example/api`

如需在本地保存部署相关变量，可复制仓库根目录的 `.env.local.example` 为 `.env.local`。

设置变量后，重新跑一次 Actions（Re-run jobs）即可让前端构建时带上该变量。

### 后端（云服务器）

后端建议部署在云服务器并开放 8000 端口。

- 健康检查：`http://<server-ip>:8000/health`
- API 文档：`http://<server-ip>:8000/docs`

### 1. 克隆项目

```bash
cd daily_ai_digest
```

### 2. 配置API密钥

复制环境变量模板并填入你的API密钥：

```bash
cd backend
cp .env.example .env
```

编辑 `.env` 文件，填入以下配置（详细获取步骤见下文）：

```env
# LLM API 配置 (默认 DeepSeek V4 Flash，也支持 Kimi/通义千问 等 OpenAI 兼容接口)
TEXT_API_KEY=your_deepseek_api_key
TEXT_BASE_URL=https://api.deepseek.com
TEXT_MODEL=deepseek-v4-flash

# GitHub Token
GITHUB_TOKEN=your_github_token

# 邮件配置
GMAIL_SENDER=your_email@gmail.com
GMAIL_APP_PASSWORD=your_16_char_app_password
DIGEST_RECIPIENT=your_email@gmail.com
```

### 3. 启动后端服务

```bash
# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# 或 .\venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 启动服务
python run.py
```

后端将在 http://localhost:8000 启动，API文档访问 http://localhost:8000/docs

### 4. 启动前端服务

```bash
cd frontend

# 安装依赖
npm install
# 或 pnpm install

# 启动开发服务器
npm run dev
```

前端将在 http://localhost:3000 启动

### 5. 访问应用

打开浏览器访问 http://localhost:3000 即可看到数据看板。

### 6. 一键启动/停止（推荐）

在项目根目录执行：

```bash
bash ./start.sh
```

查看状态：

```bash
bash ./status.sh
```

停止服务：

```bash
bash ./stop.sh
```

日志文件位于：`data/runtime/backend.log`、`data/runtime/frontend.log`。

> 定时邮件发送依赖后端调度器，`backend` 需要持续运行；`frontend` 仅用于查看和手动操作，不需要一直开着。

## 🔑 API密钥获取指南

### LLM API 配置（支持多种大模型）

本项目支持 OpenAI 兼容接口，可使用以下国内大模型：

| 服务商 | BASE_URL | 模型示例 | 特点 |
|--------|----------|---------|------|
| **DeepSeek（默认）** | `https://api.deepseek.com` | deepseek-v4-flash | OpenAI 兼容接口；旧模型名由服务端兼容路由 |
| Kimi (月之暗面) | `https://api.moonshot.cn/v1` | kimi-k3 | 支持文本与多模态；本文示例使用 K3 |
| 阿里云通义 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | qwen-turbo | 稳定可靠 |
| 智谱 AI | `https://open.bigmodel.cn/api/paas/v4` | glm-4-flash | 免费额度多 |

API 密钥必须与 BASE_URL 属于同一家服务商，跨家使用会认证失败。

配置示例：

```env
# DeepSeek 配置示例（默认）
TEXT_API_KEY=<your-deepseek-api-key>
TEXT_BASE_URL=https://api.deepseek.com
TEXT_MODEL=deepseek-v4-flash
# 没有 temperature / max_tokens 配置项：请求只发 model + messages，
# 其余全用 provider 默认值（思考模式保持开启，长度按各家上限）。

# Kimi 配置示例
TEXT_API_KEY=<your-kimi-api-key>
TEXT_BASE_URL=https://api.moonshot.cn/v1
TEXT_MODEL=kimi-k3

# 私有部署/代理地址示例
TEXT_API_KEY=<your-private-api-key>
TEXT_BASE_URL=http://<your-private-gateway>:<port>
TEXT_MODEL=<your-model-name>
```

### GitHub Personal Access Token

1. 登录 [GitHub](https://github.com)
2. 点击右上角头像 → **Settings**
3. 左侧菜单最下方 → **Developer settings**
4. **Personal access tokens** → **Tokens (classic)**
5. **Generate new token (classic)**
6. 勾选 `public_repo` 权限
7. 点击 "Generate token" 并复制

### Gmail 应用专用密码

> ⚠️ 需要先开启Google账号的两步验证

1. 访问 [Google账号安全设置](https://myaccount.google.com/security)
2. 确保 **两步验证** 已开启
3. 访问 [应用专用密码](https://myaccount.google.com/apppasswords)
4. 选择应用类型为 "邮件"，设备为 "其他"
5. 输入名称（如 "Daily AI Digest"）
6. 点击 "生成"
7. 复制16位密码（格式如：`xxxx xxxx xxxx xxxx`，使用时去掉空格）

## 📁 项目结构

```
daily_ai_digest/
├── backend/                    # 后端服务
│   ├── app/
│   │   ├── agents/            # AI Agent模块
│   │   │   ├── gemini_analyzer.py  # LLM分析引擎
│   │   │   ├── github_agent.py
│   │   │   └── arxiv_agent.py
│   │   ├── api/               # API路由
│   │   │   └── routes.py
│   │   ├── services/          # 业务服务
│   │   │   ├── digest_service.py
│   │   │   ├── email_service.py
│   │   │   └── scheduler.py
│   │   ├── config.py          # 配置管理
│   │   ├── database.py        # 数据库
│   │   ├── main.py            # FastAPI入口
│   │   ├── models.py          # 数据模型
│   │   └── schemas.py         # Pydantic模型
│   ├── requirements.txt
│   ├── .env.example
│   └── run.py                 # 启动脚本
│
├── frontend/                   # 前端应用
│   ├── src/
│   │   ├── components/        # React组件
│   │   ├── pages/             # 页面
│   │   ├── services/          # API服务
│   │   └── types/             # TypeScript类型
│   ├── package.json
│   └── vite.config.ts
│
├── data/                       # 数据存储
│   └── digest.db              # SQLite数据库
│
└── README.md
```

## 📡 API接口

| 方法 | 路径                   | 描述                            |
| ---- | ---------------------- | ------------------------------- |
| GET  | `/api/digest/today`    | 获取今日摘要                    |
| GET  | `/api/digest/latest`   | 获取最新摘要                    |
| GET  | `/api/digest/history`  | 获取历史摘要列表                |
| GET  | `/api/digest/{date}`   | 获取指定日期摘要                |
| POST | `/api/digest/trigger`  | 手动触发生成                    |
| GET  | `/api/config`          | 获取配置                        |
| GET  | `/api/status`          | 获取系统状态                    |
| GET  | `/api/logs`            | 获取执行日志                    |
| POST | `/api/email/test`      | 发送测试邮件                    |

完整API文档访问：http://localhost:8000/docs

## ⚙️ 配置说明

| 配置项                   | 说明                        | 默认值           |
| ------------------------ | --------------------------- | ---------------- |
| `TEXT_API_KEY`        | LLM API 密钥               | 空（必填）       |
| `TEXT_BASE_URL`       | LLM API 地址（OpenAI兼容） | https://api.deepseek.com |
| `TEXT_MODEL`          | 主模型名称                  | deepseek-v4-flash |
| `TEXT_FALLBACK_MODELS`| 回退模型（逗号分隔）        | 空               |
| `VISION_API_KEY`        | 视觉质检密钥（Moonshot .cn）| 空（可选）       |
| `IMAGE_GEN_API_KEY`     | 生图密钥（火山方舟 Ark）    | 空（可选）       |
| `GITHUB_TOKEN`          | GitHub Token               | 空（必填）       |
| `SCHEDULE_HOUR`         | 日报送达小时                | 9                |
| `SCHEDULE_MINUTE`       | 每日执行分钟                | 0                |
| `TIMEZONE`              | 时区                        | Asia/Shanghai    |
| `DEBUG`                 | 调试模式                    | false            |
| `LOG_LEVEL`             | 日志级别                    | INFO             |

## 当前运行与验收

- 日报按 `Asia/Shanghai` 的前一天建立时间窗口。GitHub 查询窗口内最后推送的项目；arXiv 查询窗口内首次提交的论文。Trending 是当前滚动榜单，不是历史涨星快照。
- 日报 08:30 开始整理，09:00 开始投递；超过约定时间则完成后立即发送。周报周日 20:30，月报月末 21:00。
- 手动生成、修改设置、发送测试邮件需要 `ADMIN_API_KEY`。网页首次管理操作时输入密钥，仅保存在当前浏览器会话；读取摘要无需密钥。留空则禁用管理操作。
- 六平台文案可开启。图片渲染、生图和视觉质检分别受独立开关控制，目前生产常驻状态仍关闭图片相关功能。
- 已发送记录不会重复发送。明确失败可复用原内容再次投递；部分收件或结果不确定时需要先核对邮箱，再决定是否强制重发。
- GitHub Pages 使用 `https://digest-api.vincentws.com/api` 访问后端。边缘代理配置见 `infra/cloudflare/README.md`。
- 网络可达性以部署环境实测为准。Trending 总时间预算由 `GITHUB_TRENDING_TOTAL_TIMEOUT_SECONDS` 控制，默认 60 秒，超时后使用 API 搜索补充。

运行一次真实采集、分析、投递和收件验证（只在明确需要发送测试邮件时执行）：

```bash
docker exec -w /app/backend daily-ai-digest-backend \
  python tests/manual/e2e_delivery.py --send --report-dir /app/data/e2e/manual-run
```

测试使用临时数据库，不写正常日报记录。报告和实际收到的邮件保存在指定目录。只重查同一封邮件而不重新发送：

```bash
docker exec -w /app/backend daily-ai-digest-backend \
  python tests/manual/e2e_delivery.py --verify-only --report-dir /app/data/e2e/manual-run
```

收件验证需要发送账号也是收件人，且支持使用现有凭据登录 IMAP。对其余收件人，只能确认 SMTP 接受和 To 地址正确，不能代替其实际收件箱验证。

## 📧 Gmail 限制说明

- 每日发送上限：500封（普通账户）/ 2000封（Workspace账户）
- 每封收件人上限：500人
- 附件大小限制：25MB

对于本项目的使用场景（每天1封邮件），Gmail完全足够。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 License

MIT License

---

Made with ❤️ by Daily AI Digest
