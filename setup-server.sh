#!/bin/bash
# Daily AI Digest - 服务器一键安装部署脚本
# 在 Ubuntu 服务器上执行此脚本，自动完成 Docker 安装和项目部署

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo "=========================================="
echo "Daily AI Digest - 服务器部署脚本"
echo "=========================================="
echo ""

# ============================================
# 第1步：安装 Docker
# ============================================
print_info "第1步：检查并安装 Docker..."

if command -v docker &> /dev/null; then
    print_success "Docker 已安装: $(docker --version)"
else
    print_info "正在安装 Docker..."
    
    # 更新包索引
    apt-get update
    
    # 安装必要的依赖
    apt-get install -y ca-certificates curl gnupg lsb-release
    
    # 添加 Docker 官方 GPG 密钥
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    
    # 添加 Docker 软件源
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # 安装 Docker
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    
    # 启动 Docker
    systemctl start docker
    systemctl enable docker
    
    print_success "Docker 安装完成: $(docker --version)"
fi

# 检查 Docker Compose
if docker compose version &> /dev/null; then
    print_success "Docker Compose 已安装: $(docker compose version)"
else
    print_error "Docker Compose 安装失败"
    exit 1
fi

# ============================================
# 第2步：创建项目目录
# ============================================
print_info "第2步：创建项目目录..."

PROJECT_DIR="/opt/daily-ai-digest-docker"
mkdir -p $PROJECT_DIR
cd $PROJECT_DIR

print_success "项目目录已创建: $PROJECT_DIR"

# ============================================
# 第3步：等待用户上传代码或从 git 拉取
# ============================================
print_info "第3步：准备项目文件..."

# 检查是否已有代码
if [ ! -f "docker-compose.yml" ]; then
    print_warning "未检测到项目文件，请确保已将代码上传到 $PROJECT_DIR"
    print_info "你可以在本机运行以下命令上传代码:"
    echo "  scp -r news_from_github_youtube/* root@$(curl -s ifconfig.me):$PROJECT_DIR/"
    echo ""
    read -p "按回车键继续（确认已上传代码）..."
fi

# ============================================
# 第4步：初始化环境配置
# ============================================
print_info "第4步：初始化环境配置..."

if [ ! -f ".env" ]; then
    if [ -f ".env.example.docker" ]; then
        cp .env.example.docker .env
        print_warning "已创建 .env 文件，请在下一步编辑它"
    else
        # 创建默认的 .env 文件
        cat > .env << 'EOF'
# Daily AI Digest - 环境变量配置
# 请修改以下配置为你的实际值

# LLM API 配置（推荐 Kimi）
GEMINI_API_KEY=your_api_key_here
GEMINI_BASE_URL=https://api.moonshot.cn/v1
GEMINI_MODEL=moonshot-v1-8k
GEMINI_FALLBACK_MODELS=

# GitHub Token
GITHUB_TOKEN=your_github_token_here

# YouTube API（可选）
YOUTUBE_API_KEY=

# Gmail SMTP（用于发送邮件）
GMAIL_SENDER=your_email@gmail.com
GMAIL_APP_PASSWORD=your_app_password
DIGEST_RECIPIENT=your_email@gmail.com

# 定时任务配置
SCHEDULE_HOUR=8
SCHEDULE_MINUTE=0
TIMEZONE=Asia/Shanghai

# 应用配置
DEBUG=false
LOG_LEVEL=INFO
CORS_ALLOW_ORIGINS=https://senweiv.github.io,http://localhost:3000
EOF
        print_warning "已创建默认 .env 文件"
    fi
    
    print_info "=============================================="
    print_info "请编辑 .env 文件填入你的 API 密钥:"
    print_info "  nano $PROJECT_DIR/.env"
    print_info ""
    print_info "必须配置的项目:"
    print_info "  1. GEMINI_API_KEY - LLM API 密钥"
    print_info "  2. GITHUB_TOKEN - GitHub Token"
    print_info "  3. GMAIL_SENDER/GMAIL_APP_PASSWORD - 邮件配置"
    print_info "=============================================="
    
    read -p "编辑完成后按回车键继续..."
fi

# ============================================
# 第5步：构建并启动服务
# ============================================
print_info "第5步：构建并启动 Docker 服务..."

# 创建数据目录
mkdir -p data/runtime

# 构建镜像
print_info "正在构建 Docker 镜像（这可能需要几分钟）..."
docker compose build --no-cache

# 启动服务
print_info "正在启动服务..."
docker compose up -d

# 等待服务启动
print_info "等待服务就绪..."
sleep 10

# ============================================
# 第6步：验证部署
# ============================================
print_info "第6步：验证部署..."

# 检查容器状态
if docker ps | grep -q daily-ai-digest-backend; then
    print_success "容器正在运行"
else
    print_error "容器启动失败"
    docker compose logs
    exit 1
fi

# 健康检查
HEALTH_STATUS=$(curl -s http://localhost:8000/health 2>/dev/null || echo "failed")

if [ "$HEALTH_STATUS" != "failed" ]; then
    print_success "健康检查通过！"
    echo "响应: $HEALTH_STATUS"
else
    print_warning "健康检查未通过，服务可能还在启动中"
    print_info "请稍后手动检查: curl http://localhost:8000/health"
fi

# ============================================
# 部署完成
# ============================================
echo ""
echo "=========================================="
echo "🎉 部署完成！"
echo "=========================================="
echo ""
echo "服务信息:"
echo "  • 本地访问: http://localhost:8000"
echo "  • API 文档: http://localhost:8000/docs"
echo "  • 健康检查: http://localhost:8000/health"
echo ""
echo "公网访问地址:"
echo "  http://$(curl -s ifconfig.me):8000"
echo ""
echo "常用命令:"
echo "  查看日志:   docker compose logs -f"
echo "  停止服务:   docker compose down"
echo "  重启服务:   docker compose restart"
echo "  进入容器:   docker exec -it daily-ai-digest-backend bash"
echo ""
echo "项目目录: $PROJECT_DIR"
echo "=========================================="

