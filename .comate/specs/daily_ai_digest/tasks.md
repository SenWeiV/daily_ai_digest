# Daily AI Digest 开发任务计划

- [x] 任务 1：项目初始化与基础架构搭建
    - 1.1: 创建项目根目录结构，包含 backend/、frontend/、data/ 目录
    - 1.2: 初始化后端 Python 项目，创建 requirements.txt 包含所有依赖（fastapi, uvicorn, apscheduler, google-generativeai, PyGithub, google-api-python-client, youtube-transcript-api, python-dotenv, aiosqlite）
    - 1.3: 创建 backend/app/ 基础模块结构（__init__.py, config.py, database.py, models.py, schemas.py）
    - 1.4: 创建 .env.example 环境变量模板文件，包含所有必需的API密钥占位符
    - 1.5: 实现 config.py 配置管理，从环境变量加载配置

- [x] 任务 2：数据库层实现
    - 2.1: 在 database.py 中实现 SQLite 异步连接管理，使用 aiosqlite
    - 2.2: 创建数据库初始化脚本，包含 digest_records、config、execution_logs 三张表
    - 2.3: 在 models.py 中定义数据库 ORM 模型
    - 2.4: 在 schemas.py 中定义 Pydantic 请求/响应模型（DigestRecord, ConfigItem, ExecutionLog, GitHubDigestItem, YouTubeDigestItem）

- [x] 任务 3：Gemini 分析引擎实现
    - 3.1: 创建 backend/app/agents/gemini_analyzer.py，封装 Gemini API 调用
    - 3.2: 实现 GitHub 项目分析 Prompt 模板和分析方法 analyze_github_repo()
    - 3.3: 实现 YouTube 视频分析 Prompt 模板和分析方法 analyze_youtube_video()
    - 3.4: 添加错误处理、重试机制和 Token 使用量追踪

- [x] 任务 4：GitHub Agent 实现
    - 4.1: 创建 backend/app/agents/github_agent.py，封装 PyGithub 调用
    - 4.2: 实现 search_trending_repos() 方法，搜索 AI/Agent 相关热门仓库
    - 4.3: 实现 fetch_repo_details() 方法，获取仓库详情、README、核心代码文件
    - 4.4: 实现 get_top_repos() 主方法，整合搜索、获取详情、Gemini分析的完整流程
    - 4.5: 添加去重逻辑和结果排序（按Star数和今日新增排序）

- [x] 任务 5：YouTube Agent 实现
    - 5.1: 创建 backend/app/agents/youtube_agent.py，封装 YouTube Data API 调用
    - 5.2: 实现 search_trending_videos() 方法，搜索 AI 领域热门视频
    - 5.3: 实现 fetch_video_transcript() 方法，使用 youtube-transcript-api 获取字幕
    - 5.4: 实现 get_top_videos() 主方法，整合搜索、获取字幕、Gemini分析的完整流程
    - 5.5: 添加无字幕视频的降级处理（使用描述和评论进行分析）

- [x] 任务 6：邮件服务实现
    - 6.1: 创建 backend/app/services/email_service.py，封装 Gmail SMTP 发送
    - 6.2: 实现 HTML 邮件模板，包含 GitHub Top10 和 YouTube Top10 的精美排版
    - 6.3: 实现 send_digest_email() 方法，支持 HTML 和纯文本双格式
    - 6.4: 添加发送状态追踪和错误重试机制

- [x] 任务 7：摘要生成服务与定时任务
    - 7.1: 创建 backend/app/services/digest_service.py，实现摘要生成主逻辑
    - 7.2: 实现 generate_daily_digest() 方法，并行调用 GitHub 和 YouTube Agent
    - 7.3: 创建 backend/app/services/scheduler.py，配置 APScheduler 定时任务（每天8点执行）
    - 7.4: 实现执行日志记录，保存每次执行的状态和耗时

- [x] 任务 8：FastAPI 后端接口实现
    - 8.1: 创建 backend/app/main.py，初始化 FastAPI 应用和生命周期管理
    - 8.2: 创建 backend/app/api/routes.py，实现所有 REST API 接口
    - 8.3: 实现 GET /api/digest/today 和 GET /api/digest/{date} 获取摘要接口
    - 8.4: 实现 POST /api/digest/trigger 手动触发接口
    - 8.5: 实现 GET/PUT /api/config 配置管理接口
    - 8.6: 实现 GET /api/status 和 GET /api/logs 系统状态接口
    - 8.7: 添加 CORS 配置，允许前端跨域访问
    - 8.8: 创建 backend/run.py 启动脚本

- [x] 任务 9：前端项目初始化
    - 9.1: 使用 Vite 创建 React + TypeScript 前端项目
    - 9.2: 配置 Tailwind CSS 样式框架
    - 9.3: 创建 frontend/src/types/index.ts 定义所有 TypeScript 类型
    - 9.4: 创建 frontend/src/services/api.ts 封装后端 API 调用

- [x] 任务 10：前端页面与组件开发
    - 10.1: 创建布局组件 Layout.tsx，包含导航栏和页面容器
    - 10.2: 创建首页 Home.tsx 和数据看板组件 Dashboard.tsx，展示今日统计概览
    - 10.3: 创建 GitHubList.tsx 组件，展示 GitHub Top10 列表
    - 10.4: 创建 YouTubeList.tsx 组件，展示 YouTube Top10 列表
    - 10.5: 创建 DetailModal.tsx 组件，展示项目/视频详细分析结果
    - 10.6: 创建历史记录页面 History.tsx，支持按日期查看历史摘要
    - 10.7: 创建配置页面 Settings.tsx，包含API密钥配置表单和手动触发按钮
    - 10.8: 配置 React Router 路由，整合所有页面

- [x] 任务 11：集成测试与文档完善
    - 11.1: 创建项目 README.md，包含项目介绍、安装步骤、配置指南、使用说明
    - 11.2: 在 README 中详细说明 GitHub Token、YouTube API Key、Gemini API Key、Gmail 应用专用密码的获取步骤
    - 11.3: 测试后端所有 API 接口正常工作
    - 11.4: 测试前后端联调，验证完整流程
    - 11.5: 测试手动触发功能，验证 Agent 和邮件发送正常