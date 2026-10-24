#!/usr/bin/env bash
# daily_ai_digest 百度云服务器连接 / 运维助手
# 用法：./scripts/baidu-server.sh <check|ssh|status|logs|health|pull|deploy> [rsync 额外参数，如 --dry-run]
# 主机配置读取项目根目录 .env.local（已 gitignore）：
#   DIGEST_DEPLOY_SSH_HOST / DIGEST_DEPLOY_SSH_USER / DIGEST_DEPLOY_SSH_PORT
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$ROOT/.env.local" ]]; then set -a; source "$ROOT/.env.local"; set +a; fi

HOST="${DIGEST_DEPLOY_SSH_HOST:?请在 .env.local 里设置 DIGEST_DEPLOY_SSH_HOST}"
USER_="${DIGEST_DEPLOY_SSH_USER:-root}"
PORT="${DIGEST_DEPLOY_SSH_PORT:-22}"
KEY="${DIGEST_DEPLOY_KEY:-$HOME/.ssh/id_ed25519}"
DEST="${DIGEST_DEPLOY_PATH:-/opt/daily_ai_digest}"
TARGET="$USER_@$HOST"
SSH_OPTS=(-o ConnectTimeout=10 -o ServerAliveInterval=15 -i "$KEY" -p "$PORT")
RSH="ssh -o ConnectTimeout=10 -o BatchMode=yes -i $KEY -p $PORT"

# 与 8 月 sync-to-server.sh 相同的排除规则：凭据、数据、平台相关依赖永远不同步
EXCLUDES=(
  --exclude='.git/' --exclude='.env' --exclude='.env.local'
  --exclude='backend/.env' --exclude='backend/.env.local'
  --filter='protect .env.bak*' --filter='protect .env.*.bak'
  --exclude='data/' --exclude='backend/.venv/' --exclude='backend/venv/' --exclude='.venv/'
  --exclude='__pycache__/' --exclude='*.pyc' --exclude='.pytest_cache/'
  --exclude='.DS_Store' --exclude='._*' --exclude='node_modules/' --exclude='frontend/dist/'
  --exclude='docs/private/' --exclude='百度云服务器接入参数.md' --exclude='百度云服务器连接指南.md'
  --exclude='资料索引.md' --exclude='.claude/worktrees/'
  --exclude='.agents/'
)

remote() { ssh "${SSH_OPTS[@]}" "$TARGET" "$@"; }

cmd="${1:-check}"; shift || true
case "$cmd" in
  check)
    echo "→ SSH $TARGET:$PORT (key: $KEY)"
    ssh "${SSH_OPTS[@]}" -o BatchMode=yes "$TARGET" 'echo "SSH OK: $(hostname)  $(uptime -p)"'
    echo "→ health"
    curl -sS -m 10 "http://$HOST:8000/health"; echo ;;
  ssh)
    exec ssh "${SSH_OPTS[@]}" -t "$TARGET" "cd $DEST && exec bash -l" ;;
  status)
    remote "cd $DEST && docker compose ps && echo && echo '--- git HEAD on server' && git log -1 --oneline && echo '--- uncommitted files on server:' && git status --short | wc -l" ;;
  logs)
    remote "cd $DEST && docker compose logs --tail=${LINES:-200} backend" ;;
  health)
    curl -sS -i -m 10 "http://$HOST:8000/health"; echo ;;
  pull)
    # 服务器 → 本机：把服务器上的代码（含 8 月未推送的改动）拉回来，不带 .env / data / .git
    COPYFILE_DISABLE=1 rsync -az --itemize-changes "$@" "${EXCLUDES[@]}" -e "$RSH" "$TARGET:$DEST/" "$ROOT/"
    echo "已从 $TARGET:$DEST 拉取到 $ROOT（用 git status / git diff 查看改动）" ;;
  deploy)
    # 本机 → 服务器。带 --delete，所以先做防呆检查，防止用旧代码覆盖服务器上的新代码
    if [[ ! -d "$ROOT/backend/app/publishers" ]]; then
      echo "✋ 本地没有 backend/app/publishers/，说明还没把服务器上的 8 月代码拉回来。"
      echo "   先运行：$0 pull --dry-run  然后  $0 pull"; exit 1
    fi
    if [[ " $* " == *" --dry-run "* || " $* " == *" -n "* ]]; then
      COPYFILE_DISABLE=1 rsync -az --delete --itemize-changes "$@" "${EXCLUDES[@]}" -e "$RSH" "$ROOT/" "$TARGET:$DEST/"
      echo "（dry-run，未备份或重建容器）"; exit 0
    fi
    STAMP="$(date +%Y%m%d-%H%M%S)"
    echo "→ 服务器备份到 /root/digest-backups/$STAMP"
    remote "set -e; cd $DEST; mkdir -p /root/digest-backups/$STAMP; python3 -c \"import sqlite3; s=sqlite3.connect('file:data/digest.db?mode=ro', uri=True); d=sqlite3.connect('/root/digest-backups/$STAMP/digest.db'); s.backup(d); d.close(); s.close()\"; cp .env /root/digest-backups/$STAMP/env.bak; docker inspect --format='{{.Image}}' daily-ai-digest-backend > /root/digest-backups/$STAMP/image-id.txt; tar czf /root/digest-backups/$STAMP/repo-tree.tgz --exclude=data --exclude=.git . 2>/dev/null; git diff > /root/digest-backups/$STAMP/server-local.patch"
    echo "→ rsync（--delete）到 $TARGET:$DEST"
    COPYFILE_DISABLE=1 rsync -az --delete --itemize-changes "$@" "${EXCLUDES[@]}" -e "$RSH" "$ROOT/" "$TARGET:$DEST/"
    echo "→ 重建容器"
    remote "cd $DEST && docker compose up -d --build && sleep 15 && docker compose ps"
    curl -sS -m 10 "http://$HOST:8000/health"; echo ;;
  *)
    sed -n '2,6p' "$0"; exit 1 ;;
esac
