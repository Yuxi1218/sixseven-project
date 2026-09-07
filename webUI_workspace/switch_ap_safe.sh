#!/bin/bash
# =============================================================
# sixseven AP 安全切換（v2 改用 nmcli hotspot）
# 用途：把 Jetson WiFi 切成熱點（手機直連），手機沒連上時自動回滾。
#
# 用法：sudo ./switch_ap_safe.sh [SSID] [密碼]
# 例：  sudo ./switch_ap_safe.sh AirCraft67Team 67676767
# 手機連上後： https://10.42.0.1:8000
# =============================================================
set -e

SSID="${1:-AirCraft67Team}"
PASS="${2:-67676767}"
IFACE="wlP1p1s0"
AP_IP="10.42.0.1"

echo "=== sixseven AP 安全切換 v2 ==="
echo "介面: $IFACE   熱點: $SSID / $PASS    AP IP: $AP_IP"

# 0. 先確保介面 managed + radio on
nmcli radio wifi on || true
nmcli device set "$IFACE" managed yes || true
nmcli device disconnect "$IFACE" || true
sleep 2

# 1. 產生含 AP IP 的憑證
echo "[1/4] 更新憑證（含 $AP_IP）..."
cd /home/sixseven/sixseven-project/webUI_workspace
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
    -keyout certs/key.pem -out certs/cert.pem \
    -subj "/CN=$AP_IP" \
    -addext "subjectAltName=IP:$AP_IP,DNS:localhost" \
    >/dev/null 2>&1
echo "  憑證 OK"

# 2. 用 hotspot 模式建立 AP（nmcli 自動處理 DHCP）
echo "[2/4] 建立熱點 $SSID ..."
nmcli device wifi hotspot ifname "$IFACE" ssid "$SSID" password "$PASS" 2>&1 || {
    echo "  hotspot 失敗，改用手動 AP profile..."
    nmcli con delete "$SSID" >/dev/null 2>&1 || true
    nmcli con add type wifi ifname "$IFACE" con-name "$SSID" ssid "$SSID" \
        wifi.mode ap wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PASS" \
        ipv4.method shared ipv4.addresses "$AP_IP/24" >/dev/null 2>&1
    nmcli con up "$SSID" 2>&1
}
echo "  熱點已開啟"

# 3. 啟動反映 AP IP 的 HTTPS
echo "[3/4] 確保 HTTPS 服務運行中..."
pgrep -f "webUI_workspace/main.py --ssl" >/dev/null || {
    setsid /usr/bin/python3 /home/sixseven/sixseven-project/webUI_workspace/main.py --ssl \
        > /tmp/opencode/https_ap.log 2>&1 < /dev/null &
    echo "  服務啟動"
}

# 4. 回滾監視（2 分鐘手機沒連上 AP 就重返原 WiFi）
echo "[4/4] 啟動回滾監視（120s 無裝置連入即復原）..."
setsid bash -c '
    AP_START=$(date +%s)
    while true; do
        HAS=$(iw dev wlP1p1s0 station dump 2>/dev/null | grep -c Station || true)
        if [ "$HAS" -gt 0 ]; then
            sleep 30; continue
        fi
        NOW=$(date +%s)
        if [ $((NOW - AP_START)) -gt 120 ]; then
            echo "[rollback] 120s 無裝置連上，復原 WiFi" >> /tmp/opencode/rollback.log
            nmcli radio wifi on >/dev/null 2>&1 || true
            nmcli device set wlP1p1s0 managed yes >/dev/null 2>&1 || true
            nmcli device wifi connect "Yuxi'"'"'s Room" >/dev/null 2>&1 || true
            break
        fi
        sleep 10
    done
' > /dev/null 2>&1 < /dev/null &
echo "  回滾監視已啟動"

echo ""
echo "=== 完成 ==="
echo "手機連上 $SSID → https://$AP_IP:8000"
echo "120 秒內手機沒連上 → 自動回復 Yuxi's Room WiFi"