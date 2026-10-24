#!/usr/bin/env bash
# 把本机工作树同步到服务器的 /opt/daily_ai_digest。
#
# 用 rsync 而不是 git pull：服务器直连 GitHub 会超时（这也是当初采用
# 打包上传方案的原因），而 rsync 走 SSH，是这台机器上唯一可靠的通路。
#
# --delete 是刻意的：不删除就会让上一版留下的文件继续被 import，
# 出现"改了代码但行为没变"这种最难查的现象。代价是排除列表必须完整，
# 漏一项就会删掉服务器上唯一的一份东西，所以每一条排除都写了理由。
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 主机地址只放在本机 .env.local（已 gitignore），不写进公开仓库。
if [[ -f "$SRC_DIR/.env.local" ]]; then set -a; source "$SRC_DIR/.env.local"; set +a; fi
HOST="${DIGEST_DEPLOY_HOST:-${DIGEST_DEPLOY_SSH_USER:-root}@${DIGEST_DEPLOY_SSH_HOST:?请在 .env.local 里设置 DIGEST_DEPLOY_SSH_HOST}}"
KEY="${DIGEST_DEPLOY_KEY:-$HOME/.ssh/id_ed25519}"
DEST="${DIGEST_DEPLOY_PATH:-/opt/daily_ai_digest}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/"

# macOS copyfile 会把扩展属性编码成远端的 ._AppleDouble 文件；关闭它，避免
# 仅靠 exclude 挡住新文件，却让旧元数据永久留在服务器与 Docker context 中。
COPYFILE_DISABLE=1 rsync -az --delete "$@" \
  --exclude='.git/' \
  `# 凭据只存在于服务器上，同步会用本机的空文件覆盖掉它。` \
  --exclude='.env' \
  --exclude='.env.local' \
  --exclude='backend/.env' \
  --exclude='backend/.env.local' \
  `# 备份不能被 --delete 顺手删掉：那正是回滚要用的东西。用 protect 而不是` \
  `# exclude 是因为 exclude 会连"不要传过去"一起生效，而这里只想禁止删除。` \
  `# 不能写成 --exclude='.env*'：那会一并排除 .env.example，模板于是永远不更新。` \
  --filter='protect .env.bak*' \
  --filter='protect .env.*.bak' \
  `# 数据库是唯一一份历史摘要，删了就没了` \
  --exclude='data/' \
  `# 虚拟环境是按平台编译的，把 macOS 的 .venv 送到 Linux 只会得到跑不起来的二进制` \
  --exclude='backend/.venv/' \
  --exclude='backend/venv/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache/' \
  `# macOS 在非 HFS 卷上留下的 AppleDouble 边角文件，服务器上是纯噪声` \
  --exclude='.DS_Store' \
  --exclude='._*' \
  --exclude='node_modules/' \
  --exclude='frontend/dist/' \
  `# 服务器接入文档含公网 IP 与部署路径，只存在于服务器上` \
  --exclude='百度云服务器接入参数.md' \
  -e "ssh -o ConnectTimeout=10 -o BatchMode=yes -i $KEY" \
  "$SRC" "$HOST:$DEST/"

echo "同步完成 → $HOST:$DEST"
