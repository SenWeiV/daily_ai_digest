# Daily AI Digest 更新与部署计划清单

> 目标：将 `Daily AI Digest` 部署到云端，并在个人网站 `weisen-personal-website` 中新增入口模块，点击后跳转到 Digest UI。

## 1. 目标与范围

- 部署后端（FastAPI + Scheduler）到云端，保证每日任务自动运行。
- 部署前端（React）到云端，提供可访问 UI。
- 在个人网站增加一个功能模块卡片，跳转到 Digest UI。
- 完成基础监控、告警、回滚与验收。

---

## 2. 部署架构决策（先确认）

- [ ] 后端平台：`Render / Railway / Fly.io` 三选一
- [ ] 前端平台：`Vercel / Netlify` 二选一
- [ ] 数据库：先用 `SQLite + 持久盘`，或升级 `PostgreSQL`
- [ ] 定时策略：继续用后端 `APScheduler`，或改平台 `Cron`
- [ ] 访问域名：是否使用子域名（如 `digest.yourdomain.com`）

---

## 3. 代码更新清单（部署前）

### 3.1 配置与环境变量

- [ ] 整理并确认后端环境变量：
  - [ ] `GEMINI_API_KEY`
  - [ ] `GITHUB_TOKEN`
  - [ ] `YOUTUBE_API_KEY`
  - [ ] `GMAIL_SENDER`
  - [ ] `GMAIL_APP_PASSWORD`
  - [ ] `DIGEST_RECIPIENT`
  - [ ] `SCHEDULE_HOUR`
  - [ ] `SCHEDULE_MINUTE`
  - [ ] `TIMEZONE`
  - [ ] `DATABASE_PATH`
- [ ] 检查 `.env.example` 是否与真实部署变量一致
- [ ] 确认生产环境 `TIMEZONE`（建议按目标时区设置）

### 3.2 前后端联调配置

- [ ] 为前端补充 API 基地址配置（如 `VITE_API_BASE_URL`）
- [ ] 前端 `api.ts` 支持本地/生产环境自动切换
- [ ] 配置后端 CORS，允许前端线上域名访问

### 3.3 可运维性增强（建议）

- [ ] 增加健康检查接口（如 `/healthz`）
- [ ] 明确日志路径与日志级别（生产 `INFO`）
- [ ] 增加任务执行失败日志关键字，便于平台告警匹配

### 3.4 前端 UI 风格对齐（个人站风格）

目标：将 `Daily AI Digest` UI 对齐到个人站 `https://senweiv.github.io/weisen-personal-website/` 的视觉语言（深色极简、中性色、Inter 字体、轻量动效）。

- [x] 建立统一主题令牌（颜色/文本/边框/背景）
  - [x] 深色主背景：`neutral-950` 气质
  - [x] 卡片层级：`surface / surface-soft / hover`
  - [x] 文本层级：`main / muted / dim`
  - [x] 统一按钮与 Tab 状态样式
- [x] 全局基础样式改造
  - [x] 统一字体为 `Inter`
  - [x] 统一滚动条、选区、淡入动效
  - [x] 增加可复用样式类：`surface-card`、`btn-ghost`、`btn-solid`、`tab-shell`
- [x] 导航与页面框架改造（`Layout`）
  - [x] 顶部导航改为暗色半透明 + 边框
  - [x] Logo 区改为中性边框风格，移除高饱和渐变
  - [x] 导航激活态与 hover 统一为中性色
- [x] 核心页面改造
  - [x] `Home`：标题、按钮、Tab、Skeleton 风格统一
  - [x] `History`：左侧日期列表与右侧详情暗色化
  - [x] `Settings`：卡片、表格、表单、状态标签暗色化
- [x] 核心组件改造
  - [x] `Dashboard` 统计卡片统一暗色层级
  - [x] `GitHubList` / `YouTubeList` 卡片统一暗色边框与信息层级
  - [x] `DetailModal` 弹窗、遮罩、按钮、标签暗色化
- [ ] 响应式与可用性验收
  - [ ] Desktop（>=1280）视觉检查
  - [ ] Tablet（768-1279）布局检查
  - [ ] Mobile（<=767）卡片与弹窗可读性检查
  - [ ] 对比度检查（文本与背景）

前端改造涉及文件（当前已更新）：
- [x] `frontend/src/index.css`
- [x] `frontend/src/components/Layout.tsx`
- [x] `frontend/src/components/Dashboard.tsx`
- [x] `frontend/src/components/GitHubList.tsx`
- [x] `frontend/src/components/YouTubeList.tsx`
- [x] `frontend/src/components/DetailModal.tsx`
- [x] `frontend/src/pages/Home.tsx`
- [x] `frontend/src/pages/History.tsx`
- [x] `frontend/src/pages/Settings.tsx`

---

## 4. 云端部署执行清单

### 4.1 后端部署

- [ ] 创建后端云服务并连接仓库
- [ ] 配置构建命令（安装 Python 依赖）
- [ ] 配置启动命令（启动 `backend/run.py` 或 ASGI 入口）
- [ ] 注入全部环境变量
- [ ] 挂载持久化存储（若继续使用 SQLite）
- [ ] 部署后验证：
  - [ ] `GET /api/status` 返回正常
  - [ ] `GET /docs` 可访问
  - [ ] 手动触发 `POST /api/digest/trigger` 成功

### 4.2 前端部署

- [ ] 创建前端云服务并连接仓库
- [ ] 配置构建命令（如 `npm ci && npm run build`）
- [ ] 配置环境变量（API 基地址）
- [ ] 部署后验证：
  - [ ] 首页可访问
  - [ ] 数据请求成功
  - [ ] 关键页面（Home/History/Settings）可用

---

## 5. 个人网站接入清单（weisen-personal-website）

- [ ] 在首页 `Selected Work`（或等价模块）新增卡片：`Daily AI Digest`
- [ ] 卡片内容建议：
  - [ ] 标题：`Daily AI Digest`
  - [ ] 描述：`GitHub + YouTube 每日 AI 热点摘要`
  - [ ] 按钮：`Open App`
- [ ] 跳转链接指向已部署 Digest 前端地址
- [ ] 链接策略：
  - [ ] 新标签打开（推荐）`target="_blank" rel="noopener noreferrer"`
- [ ] 本地预览确认样式与移动端布局
- [ ] 发布个人网站并验证线上跳转

---

## 6. 验收清单（Go-Live）

- [ ] 每日定时任务按预期触发（至少连续观察 2-3 天）
- [ ] 邮件发送成功率正常
- [ ] GitHub 与 YouTube 均有有效抓取结果
- [ ] 个人网站入口点击后跳转正常
- [ ] 移动端访问与跳转正常
- [ ] 无高频报错日志

---

## 7. 回滚与应急

- [ ] 保留最近一个稳定版本 Tag
- [ ] 部署失败时可一键回退到上个版本
- [ ] 若定时任务异常：
  - [ ] 临时改为手动触发
  - [ ] 核查 API Key 配额、网络、平台日志
- [ ] 若数据库异常：
  - [ ] 先切只读展示
  - [ ] 进行数据恢复或切换备份

---

## 8. 上线后优化（下一阶段）

- [ ] 将 SQLite 迁移到 PostgreSQL（提升稳定性）
- [ ] 将调度从进程内迁移到平台 Cron（降低耦合）
- [ ] 增加失败告警（邮件/Slack/Telegram）
- [ ] 增加抓取质量评分与“命中偏好规则”可视化
- [ ] 增加多收件人配置与摘要模板版本管理
