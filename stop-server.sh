#!/usr/bin/env bash
set -euo pipefail

PORT=8765
PIDS=$(fuser "${PORT}/tcp" 2>/dev/null || true)

if [[ -n "$PIDS" ]]; then
    echo "正在停止端口 ${PORT} 上的服务 (PID: ${PIDS})..."
    kill $PIDS 2>/dev/null || true
    sleep 0.5
    echo "服务已停止。"
else
    echo "端口 ${PORT} 上未发现运行中的服务。"
fi
