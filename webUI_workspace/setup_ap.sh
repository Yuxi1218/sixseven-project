#!/bin/bash
# [備援] 把 Jetson 自己設成 WiFi 熱點（AP）
# 用途：當「手機熱點」方案出問題（IP 抓不到、介面衝突）時，
#       讓 Jetson 直接廣播一個熱點，手機連上後用固定 IP 開 HTTPS 網頁。
#
# ⚠️  注意：
#   - 執行後 WiFi 網卡會從「連網」轉為「熱點發送」，可能讓目前 SSH 斷線。
#   - 需要 root（sudo）。
#   - 需有可用的 WiFi 介面（例：wlP1p1s0）且支援 AP 模式。
#
# 用法：sudo ./setup_ap.sh <SSID> [密碼(至少8碼)]
#   例： sudo ./setup_ap.sh sixseven-ap 12345678
# 手機連上後：開 https://10.42.0.1:8000

set -e

SSID="${1:-sixseven-ap}"
PASS="${2:-12345678}"
IFACE="$(iw dev 2>/dev/null | grep Interface | awk '{print $2}' | head -1)"
[ -z "$IFACE" ] && IFACE="wlP1p1s0"

echo "WiFi 介面：$IFACE"
echo "熱點名：$SSID  密碼：$PASS"

# 保留目前 IP（AP 後固定 10.42.0.1）
AP_IP="10.42.0.1"

# 先停用被 NetworkManager 佔用的現有連線
nmcli radio wifi off >/dev/null 2>&1 || true
nmcli device set "$IFACE" managed no >/dev/null 2>&1 || true

# 建立 AP connection（不自動連現有 wifi）
nmcli connection delete "$SSID" >/dev/null 2>&1 || true
nmcli connection add type wifi ifname "$IFACE" \
    con-name "$SSID" \
    ssid "$SSID" \
    wifi.mode ap \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$PASS" \
    ipv4.method shared \
    ipv4.addresses "$AP_IP/24" \
    >/dev/null 2>&1

nmcli connection up "$SSID" >/dev/null 2>&1
echo "✅ 熱點已開啟：SSID=$SSID"
echo "   手機連上後，瀏覽器開 https://$AP_IP:8000"
echo "   （需重跑 ./gen_cert.sh 讓憑證含 10.42.0.1，再 ./start_https.sh）"