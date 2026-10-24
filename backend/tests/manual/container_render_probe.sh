#!/usr/bin/env sh
# 在一个干净的 python:3.11-slim 容器里验证渲染链路的每一环。
#
# 为什么需要它：渲染路径在测试里全是假的（Playwright 被 fake 掉），
# 本机 darwin 连 fontconfig 都没有，preflight() 按设计直接拒绝渲染。
# 也就是说"改完 Dockerfile 应该能跑"在容器真跑一遍之前只是推断。
# 这个脚本先于镜像构建执行，把三个已知会静默失败的点各钉死一次：
#   1. 装依赖必须走内网源 —— 公网 PyPI 上 google-auth 报 from versions: none，
#      公网 deb.debian.org 实测 23KB/s（apt 那一层跑了 8296 秒）。
#   2. 运行库必须显式写 Debian trixie 的包名 —— playwright install --with-deps
#      探测不到 trixie，回落到 ubuntu20.04 包名，9 个包 Unable to locate，
#      然后**以退出码 0 结束**。构建照常成功，缺库要到 launch() 才炸。
#   3. Chromium 下载超时硬编码 30 秒，169MB 的包必然超时。
#      PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT 是唯一的旁路。
# 最后真的启动一次浏览器渲染中文加 emoji，因为字体装上了不等于画得出来。
set -e

MIRROR_DEB="${MIRROR_DEB:-http://mirrors.baidubce.com/debian}"
MIRROR_PYPI="${MIRROR_PYPI:-http://mirrors.baidubce.com/pypi/simple/}"
PYPI_HOST="${PYPI_HOST:-mirrors.baidubce.com}"

cat > /etc/apt/sources.list.d/debian.sources <<EOF
Types: deb
URIs: $MIRROR_DEB
Suites: trixie trixie-updates
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.pgp
EOF

echo "=== apt update ==="
apt-get update -qq

echo "=== 字体与 Chromium 运行库（trixie 真实包名，t64 后缀） ==="
apt-get install -y -qq --no-install-recommends \
  fontconfig fonts-noto-cjk fonts-noto-color-emoji \
  libasound2t64 libatk-bridge2.0-0t64 libatk1.0-0t64 libatspi2.0-0t64 \
  libcairo2 libcups2t64 libdbus-1-3 libdrm2 libexpat1 libgbm1 \
  libglib2.0-0t64 libgtk-3-0t64 libnspr4 libnss3 libpango-1.0-0 \
  libx11-6 libxcb1 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
  libxkbcommon0 libxrandr2 libudev1 zlib1g > /dev/null
fc-cache -f > /dev/null

echo "=== pip 装 playwright 与 Pillow ==="
pip install -q --no-cache-dir -i "$MIRROR_PYPI" --trusted-host "$PYPI_HOST" \
  playwright==1.49.1 Pillow==11.1.0 2>&1 | grep -vE "notice|WARNING" || true

echo "=== playwright install chromium ==="
start=$(date +%s)
playwright install chromium 2>&1 | grep -vE "^[[:space:]]*at " | tail -6
echo "chromium 安装耗时=$(($(date +%s)-start))s"
du -sh /root/.cache/ms-playwright/

echo "=== fc-list 中文族 ==="
fc-list :lang=zh-cn family | head -3
echo "=== fc-list emoji 族 ==="
fc-list :lang=und-zsye family | head -3

echo "=== 真实启动浏览器渲染中文与 emoji ==="
# 复用生产代码的 font_stack()：探针里另写一份字体栈就只能证明"探针能渲染"，
# 证明不了生产那一份能渲染。PYTHONPATH 指向挂载进来的 backend。
PYTHONPATH=/app/backend python /app/backend/tests/manual/probe_render.py
