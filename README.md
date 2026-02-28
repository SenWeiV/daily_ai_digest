# 🤖 Daily AI Digest

> 每日AI情报摘要系统 - 自动从GitHub获取AI领域热点项目，通过大模型深度分析后，以邮件形式发送每日情报摘要。

![Daily AI Digest](https://img.shields.io/badge/version-1.2.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-green.svg)
![React](https://img.shields.io/badge/react-18.x-61dafb.svg)
![License](https://img.shields.io/badge/license-MIT-yellow.svg)

## 🌐 线上部署

- **前端**: https://senweiv.github.io/daily_ai_digest/
- **后端 API**: http://120.48.83.123:8000
- **API 文档**: http://120.48.83.123:8000/docs

## ✨ 功能特性

- 🐙 **GitHub Agent**: 自动检索AI/Agent领域最热门的Top 10项目，深度阅读README和核心代码
- 🧠 **LLM 分析**: 支持多种大模型（Kimi、DeepSeek、通义千问、Gemini等）进行深度分析
- 📧 **邮件推送**: 精美HTML格式的每日摘要邮件，随时随地获取情报
- ⏰ **定时执行**: 每天早上8点自动执行，也支持手动触发
- 🖥️ **可视化看板**: React前端界面，查看历史数据和详细分析
- 🇨🇳 **国内友好**: 支持国内大模型API，无需代理即可运行

> ⚠️ **注意**: YouTube功能在国内环境需要代理才能使用。如无代理，YouTube功能将自动禁用，不影响GitHub分析功能。

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
│  │ GitHub Agent     │  │ YouTube Agent (国内需代理)            │ │
│  │ - 趋势检索       │  │ - 视频检索                           │ │
│  │ - 仓库内容爬取   │  │ - 字幕/转录获取                      │ │
│  │ - 代码文件分析   │  │ - 视频内容理解                       │ │
│  └──────────────────┘  └──────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │               LLM 分析引擎 (Kimi/DeepSeek/通义/Gemini)       ││
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
  - 示例：`http://120.48.83.123:8000/api`

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
# LLM API 配置 (支持 Kimi/DeepSeek/通义千问 等 OpenAI 兼容接口)
GEMINI_API_KEY=your_api_key
GEMINI_BASE_URL=https://api.moonshot.cn/v1  # Kimi API
GEMINI_MODEL=moonshot-v1-8k

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
| Kimi (月之暗面) | `https://api.moonshot.cn/v1` | moonshot-v1-8k | 长上下文 |
| DeepSeek | `https://api.deepseek.com/v1` | deepseek-chat | 价格便宜 |
| 阿里云通义 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | qwen-turbo | 稳定可靠 |
| 智谱 AI | `https://open.bigmodel.cn/api/paas/v4` | glm-4-flash | 免费额度多 |

配置示例：

```env
# Kimi 配置示例
GEMINI_API_KEY=sk-xxx
GEMINI_BASE_URL=https://api.moonshot.cn/v1
GEMINI_MODEL=moonshot-v1-8k

# DeepSeek 配置示例
GEMINI_API_KEY=sk-xxx
GEMINI_BASE_URL=https://api.deepseek.com/v1
GEMINI_MODEL=deepseek-chat

# 私有部署/代理地址示例
GEMINI_API_KEY=sk-xxx
GEMINI_BASE_URL=http://10.225.31.12
GEMINI_MODEL=kimi-k2.5
```

### GitHub Personal Access Token

1. 登录 [GitHub](https://github.com)
2. 点击右上角头像 → **Settings**
3. 左侧菜单最下方 → **Developer settings**
4. **Personal access tokens** → **Tokens (classic)**
5. **Generate new token (classic)**
6. 勾选 `public_repo` 权限
7. 点击 "Generate token" 并复制

### YouTube Data API Key（可选，国内需要代理）

1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建新项目或选择已有项目
3. 左侧菜单 → **APIs & Services** → **Library**
4. 搜索 "YouTube Data API v3" 并启用
5. 左侧菜单 → **APIs & Services** → **Credentials**
6. **Create Credentials** → **API key**
7. 复制生成的API Key

> ⚠️ 国内环境无法直接访问 YouTube API，需要配置代理或在环境变量中设置 `HTTPS_PROXY`。

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
│   │   │   └── youtube_agent.py
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
| POST | `/api/youtube/analyze` | 分析单个 YouTube 视频（URL/ID） |

完整API文档访问：http://localhost:8000/docs

## ⚙️ 配置说明

| 配置项                   | 说明                        | 默认值           |
| ------------------------ | --------------------------- | ---------------- |
| `GEMINI_API_KEY`        | LLM API 密钥               | 空（必填）       |
| `GEMINI_BASE_URL`       | LLM API 地址（OpenAI兼容） | 空               |
| `GEMINI_MODEL`          | 主模型名称                  | kimi-k2.5        |
| `GEMINI_FALLBACK_MODELS`| 回退模型（逗号分隔）        | 空               |
| `GITHUB_TOKEN`          | GitHub Token               | 空（必填）       |
| `YOUTUBE_API_KEY`       | YouTube API Key            | 空（可选）       |
| `SCHEDULE_HOUR`         | 每日执行小时                | 8                |
| `SCHEDULE_MINUTE`       | 每日执行分钟                | 0                |
| `TIMEZONE`              | 时区                        | Asia/Shanghai    |
| `DEBUG`                 | 调试模式                    | false            |
| `LOG_LEVEL`             | 日志级别                    | INFO             |

## 🇨🇳 国内部署说明

### 无需代理即可使用的功能

- ✅ GitHub 项目检索和分析
- ✅ 使用国内大模型进行内容分析（Kimi、DeepSeek、通义千问等）
- ✅ 邮件发送

### 需要代理的功能

- ⚠️ YouTube 视频检索和分析（需配置 `HTTPS_PROXY` 环境变量）

### 推荐配置

使用国内大模型 API（如 Kimi、DeepSeek、通义千问等），无需代理即可完整运行：

```env
# Kimi API 示例（推荐）
GEMINI_API_KEY=sk-xxx
GEMINI_BASE_URL=https://api.moonshot.cn/v1
GEMINI_MODEL=moonshot-v1-8k

# DeepSeek API 示例
GEMINI_API_KEY=sk-xxx
GEMINI_BASE_URL=https://api.deepseek.com/v1
GEMINI_MODEL=deepseek-chat
```

### 部署验证

部署后可运行 smoke test 验证配置：

```bash
cd backend
source venv/bin/activate
python smoke_test.py
```

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