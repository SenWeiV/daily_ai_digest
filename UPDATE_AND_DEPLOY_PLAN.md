# Daily AI Digest 更新与部署计划清单

> 目标：将 `Daily AI Digest` 部署到云端，并在个人网站 `weisen-personal-website` 中新增入口模块，点击后跳转到 Digest UI。

---

## 0. 最新进展（2026-02-28 / 服务器：120.48.83.123）

### 0.1 当前部署状态

- [x] 后端已部署到云服务器并可公网访问
  - 服务目录：`/opt/daily_ai_digest/backend`
  - 环境变量：`/opt/daily_ai_digest/backend/.env`
  - systemd 常驻服务：`daily-ai-digest.service`（已 enable + running）
  - 健康检查：`curl http://120.48.83.123:8000/health` → `200 OK`

- [x] 前端已部署到 GitHub Pages
  - 页面：`https://senweiv.github.io/daily_ai_digest/`
  - 通过 Actions 变量注入：`VITE_API_BASE_URL=http://120.48.83.123:8000/api`

- [x] 代码已支持国内大模型 API（Kimi/DeepSeek/通义千问等）
  - 新增 `smoke_test.py` 用于 API 连通性测试
  - 修复 Kimi API `temperature=1` 参数限制问题

### 0.2 当前问题：LLM API 网络不可达

**问题现象：**
```
✅ API Key 已配置: sk-2c6QZMA...
✅ Base URL: http://10.225.31.12
✅ Model: kimi-k2.5
❌ LLM API 网络不可达
```

**问题诊断：**
- 配置的 LLM API 地址 `http://10.225.31.12` 是百度千帆内网地址
- 服务器 IP: `192.168.16.2`（内网） / `120.48.83.123`（公网）
- Ping 测试：`10.225.31.12` → **100% 丢包**
- 结论：**服务器无法访问该内网地址**

**可能原因：**
1. 百度千帆 API 需要在特定的 VPC 环境才能访问
2. 需要配置 VPC 对等连接或专线
3. 该地址可能是其他服务的内网地址

### 0.3 解决方案

#### 方案一：使用公网可访问的 LLM API（推荐）

更换为公网可直接访问的 API：

| 服务商 | BASE_URL | 特点 |
|--------|----------|------|
| Kimi (月之暗面) | `https://api.moonshot.cn/v1` | 长上下文，国内直连 |
| DeepSeek | `https://api.deepseek.com/v1` | 价格便宜，国内直连 |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 阿里云，稳定可靠 |
| 智谱 AI | `https://open.bigmodel.cn/api/paas/v4` | 免费额度多 |

**操作步骤：**

1. 获取对应平台的 API Key：
   - Kimi: https://platform.moonshot.cn/
   - DeepSeek: https://platform.deepseek.com/
   - 通义千问: https://dashscope.console.aliyun.com/

2. 更新服务器 `.env` 配置：
```bash
ssh root@120.48.83.123
# 编辑配置
nano /opt/daily_ai_digest/backend/.env
```

修改为：
```env
# Kimi 官方 API 示例
GEMINI_API_KEY=sk-your-kimi-api-key
GEMINI_BASE_URL=https://api.moonshot.cn/v1
GEMINI_MODEL=moonshot-v1-8k
```

3. 重启服务：
```bash
systemctl restart daily-ai-digest
```

4. 验证：
```bash
cd /opt/daily_ai_digest/backend
source .venv/bin/activate
python smoke_test.py
```

#### 方案二：配置 VPC 对等连接

如果必须使用 `10.225.31.12` 这个内网地址：
1. 在百度云控制台配置 VPC 对等连接
2. 确保服务器所在 VPC 可以访问千帆平台的 VPC
3. 具体配置需参考百度千帆文档

#### 方案三：使用百度千帆官方 SDK

百度千帆提供了官方 SDK，可能支持更灵活的认证方式：
- 文档：https://cloud.baidu.com/doc/WENXINWORKSHOP/index.html

### 0.4 YouTube 功能状态

- YouTube API 在国内环境无法直连 Google
- 已优化代码：无代理时自动跳过，不影响 GitHub 功能
- 如需启用 YouTube，需配置代理：
  ```bash
  # 在 systemd 服务中配置
  Environment="HTTPS_PROXY=http://127.0.0.1:8902"
  ```

---

## 1. 目标与范围

- 部署后端（FastAPI + Scheduler）到云端，保证每日任务自动运行。
- 部署前端（React）到云端，提供可访问 UI。
- 在个人网站增加一个功能模块卡片，跳转到 Digest UI。
- 完成基础监控、告警、回滚与验收。

---

## 2. 部署架构决策

- [x] 后端平台：百度云服务器 `120.48.83.123`
- [x] 前端平台：GitHub Pages `https://senweiv.github.io/daily_ai_digest/`
- [x] 数据库：SQLite + 持久盘
- [x] 定时策略：后端 APScheduler
- [ ] 访问域名：可选子域名（如 `digest.yourdomain.com`）

---

## 3. 代码更新清单

### 3.1 已完成的更新

- [x] 支持国内大模型 API（Kimi/DeepSeek/通义等 OpenAI 兼容接口）
- [x] 修复 Kimi API `temperature=1` 参数限制
- [x] YouTube Agent 无代理时自动跳过
- [x] 新增 `smoke_test.py` 测试脚本
- [x] 更新 `.env.example` 配置模板
- [x] 更新 README 文档

### 3.2 待完成的更新

- [ ] 确认并配置可用的 LLM API
- [ ] 验证完整流程（GitHub 抓取 → LLM 分析 → 邮件发送）

---

## 4. 下一步行动

1. **确认 LLM API 方案**
   - 选择使用公网 API（Kimi/DeepSeek）或配置 VPC

2. **更新服务器配置**
   - 修改 `.env` 文件
   - 重启服务
   - 运行 `smoke_test.py` 验证

3. **手动触发测试**
   ```bash
   curl -X POST "http://120.48.83.123:8000/api/digest/trigger" \
     -H "Content-Type: application/json" \
     -d '{"force": true, "send_email": true}'
   ```

4. **验证邮件发送**
   - 检查邮箱收到摘要邮件
   - 确认 GitHub 项目分析内容正常

---

## 5. 服务器连接信息

| 参数 | 值 |
|------|-----|
| 公网 IP | `120.48.83.123` |
| 登录用户 | `root` |
| SSH 端口 | `22` |
| SSH Key | `~/.ssh/id_ed25519` |
| 连接命令 | `ssh -i ~/.ssh/id_ed25519 root@120.48.83.123` |

---

## 6. 常用命令

```bash
# 查看服务状态
systemctl status daily-ai-digest --no-pager

# 查看日志
journalctl -u daily-ai-digest -f --no-pager

# 重启服务
systemctl restart daily-ai-digest

# 运行测试
cd /opt/daily_ai_digest/backend
source .venv/bin/activate
python smoke_test.py

# 查看配置
cat /opt/daily_ai_digest/backend/.env
```

---

## 7. 更新记录

| 日期 | 更新内容 |
|------|----------|
| 2026-02-28 | 部署最新代码，发现 LLM API 网络问题，整理解决方案 |
| 2026-02-27 | 支持国内大模型 API，优化 YouTube 无代理处理 |
| 2026-02-25 | 初始部署到百度云服务器 |