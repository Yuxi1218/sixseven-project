#!/bin/bash
# 重新啟動 WebUI/HTTPS 服務（sixseven-wing damage detection）。
# 正式由 systemd 管理；此腳本供人與 tools/deploy_watcher.py 呼叫（部署新模型後重啟）。
# /tmp/opencode/start_webrtc.sh 會由 systemd-tmpfiles 自動複製一份，重開機後仍在。
set -u

SERVICE="sixseven-webrtc"

# 首選：用 systemd 重啟（需要 /etc/sudoers.d/sixseven-webrtc 的 NOPASSWD）
if sudo -n /usr/bin/systemctl restart "$SERVICE" 2>/dev/null; then
    echo "[start_webrtc] systemd restart $SERVICE OK"
    exit 0
fi

# 備援：直接以背景行程啟動（偵錯用；log 與 systemd 相同路徑）
echo "[start_webrtc] systemd 不可用，改用直接啟動"
pkill -f "webUI_workspace/main.py --ssl" 2>/dev/null
cd /home/sixseven/sixseven-project/webUI_workspace || exit 1
setsid /usr/bin/python3 main.py --ssl \
    >> /tmp/opencode/https_webrtc27.log 2>&1 < /dev/null &
echo "[start_webrtc] 已用 nohup 方式啟動 main.py --ssl"
