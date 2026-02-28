#!/bin/bash
# Daily AI Digest - Docker 部署脚本
# 用于在云服务器中快速部署和启动容器化服务

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 显示帮助信息
show_help() {
    cat << EOF
Daily AI Digest - Docker 部署脚本

用法: $0 [命令]

命令:
    setup       初始化环境（创建 .env 文件和数据目录）
    build       构建 Docker 镜像
    start       启动服务
    stop        停止服务
    restart     重启服务
    status      查看服务状态
    logs        查看日志
    update      更新代码并重新部署
    clean       清理 Docker 资源
    test        运行健康检查测试
    help        显示此帮助信息

示例:
    $0 setup    # 首次部署时运行
    $0 start    # 启动服务
    $0 logs     # 查看实时日志
EOF
}

# 检查 Docker 是否安装
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安装，请先安装 Docker"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        print_error "Docker Compose 未安装，请先安装 Docker Compose"
        exit 1
    fi
    
    print_success "Docker 环境检查通过"
}

# 设置环境
setup_env() {
    print_info "正在初始化环境..."
    
    # 检查 .env 文件是否存在
    if [ ! -f ".env" ]; then
        if [ -f ".env.example.docker" ]; then
            cp .env.example.docker .env
            print_warning "已创建 .env 文件，请编辑它填入你的实际配置"
            print_info "配置文件路径: $(pwd)/.env"
            print_info "请使用以下命令编辑: nano .env 或 vim .env"
        else
            print_error "找不到 .env.example.docker 模板文件"
            exit 1
        fi
    else
        print_info ".env 文件已存在"
    fi
    
    # 创建数据目录
    mkdir -p data/runtime
    print_success "数据目录已创建"
    
    print_info "环境初始化完成！"
    print_info "下一步：编辑 .env 文件后，运行 '$0 build' 构建镜像"
}

# 构建镜像
build_image() {
    print_info "正在构建 Docker 镜像..."
    
    check_docker
    
    # 使用 docker compose 或 docker-compose
    if docker compose version &> /dev/null; then
        docker compose build --no-cache
    else
        docker-compose build --no-cache
    fi
    
    print_success "Docker 镜像构建完成"
}

# 启动服务
start_service() {
    print_info "正在启动 Daily AI Digest 服务..."
    
    check_docker
    
    # 检查 .env 文件
    if [ ! -f ".env" ]; then
        print_error "找不到 .env 文件，请先运行 '$0 setup'"
        exit 1
    fi
    
    # 启动服务
    if docker compose version &> /dev/null; then
        docker compose up -d
    else
        docker-compose up -d
    fi
    
    print_success "服务已启动"
    print_info "等待服务就绪..."
    sleep 5
    
    # 检查健康状态
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        print_success "服务健康检查通过！"
        print_info "API 地址: http://localhost:8000"
        print_info "API 文档: http://localhost:8000/docs"
    else
        print_warning "服务可能还在启动中，请稍后检查状态"
    fi
}

# 停止服务
stop_service() {
    print_info "正在停止服务..."
    
    if docker compose version &> /dev/null; then
        docker compose down
    else
        docker-compose down
    fi
    
    print_success "服务已停止"
}

# 重启服务
restart_service() {
    print_info "正在重启服务..."
    stop_service
    start_service
}

# 查看状态
show_status() {
    print_info "服务状态："
    
    if docker compose version &> /dev/null; then
        docker compose ps
    else
        docker-compose ps
    fi
    
    echo ""
    print_info "尝试访问健康检查接口..."
    if curl -s http://localhost:8000/health 2>/dev/null | python3 -m json.tool 2>/dev/null || \
       curl -s http://localhost:8000/health 2>/dev/null; then
        echo ""
        print_success "健康检查通过"
    else
        print_error "健康检查失败，服务可能未正常运行"
    fi
}

# 查看日志
show_logs() {
    print_info "显示日志（按 Ctrl+C 退出）..."
    
    if docker compose version &> /dev/null; then
        docker compose logs -f backend
    else
        docker-compose logs -f backend
    fi
}

# 更新服务
update_service() {
    print_info "正在更新服务..."
    
    # 拉取最新代码（如果在 git 仓库中）
    if [ -d ".git" ]; then
        print_info "拉取最新代码..."
        git pull origin main || git pull origin master || print_warning "无法自动拉取代码，请手动更新"
    fi
    
    # 重新构建并启动
    build_image
    
    # 如果服务在运行，先停止
    if docker ps | grep -q daily-ai-digest-backend; then
        stop_service
    fi
    
    start_service
    
    print_success "服务更新完成"
}

# 清理资源
clean_resources() {
    print_warning "这将删除所有相关的 Docker 容器、镜像和卷"
    read -p "确定要继续吗？(y/N): " confirm
    
    if [[ $confirm =~ ^[Yy]$ ]]; then
        print_info "正在清理资源..."
        
        # 停止并删除容器
        if docker compose version &> /dev/null; then
            docker compose down -v --rmi all
        else
            docker-compose down -v --rmi all
        fi
        
        print_success "清理完成"
    else
        print_info "操作已取消"
    fi
}

# 运行测试
run_test() {
    print_info "运行健康检查测试..."
    
    # 后端健康检查
    print_info "测试后端 API..."
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        response=$(curl -s http://localhost:8000/health)
        print_success "后端服务正常"
        echo "响应: $response"
    else
        print_error "后端服务异常"
        return 1
    fi
    
    # 检查 API 文档
    print_info "测试 API 文档..."
    if curl -s http://localhost:8000/docs > /dev/null 2>&1; then
        print_success "API 文档可访问: http://localhost:8000/docs"
    else
        print_warning "API 文档可能无法访问"
    fi
    
    print_success "所有测试完成"
}

# 主函数
main() {
    case "${1:-help}" in
        setup)
            setup_env
            ;;
        build)
            build_image
            ;;
        start)
            start_service
            ;;
        stop)
            stop_service
            ;;
        restart)
            restart_service
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs
            ;;
        update)
            update_service
            ;;
        clean)
            clean_resources
            ;;
        test)
            run_test
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_error "未知命令: $1"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
