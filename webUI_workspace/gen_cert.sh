#!/bin/bash
# 動態內網 HTTPS 憑證產生器
# 用途：手機熱點下 IP 會變。此腳本抓取目前主機 IP，產生含該 IP 的自簽憑證，
#       IP 有變時才重生，避免每次啟動都重做。
#
# 用法：./gen_cert.sh   （在 webUI_workspace/ 目錄下執行）
# 產出：certs/cert.pem, certs/key.pem, certs/current_ip

cd "$(dirname "$0")"
mkdir -p certs

# 取得主機 IP（排除 docker/veth/loopback；wifi/乙太優先，取第一個）
IP=""
for ip in $(hostname -I 2>/dev/null); do
    case "$ip" in
        127.*|172.17.*|172.18.*) continue ;;
    esac
    IP="$ip"
    break
done

if [ -z "$IP" ]; then
    echo "⚠️  抓不到內網 IP，使用 localhost" >&2
    IP="127.0.0.1"
fi

echo "目前 IP：$IP"

# 若 IP 沒變且憑證已存在，直接沿用
if [ -f certs/cert.pem ] && [ -f certs/key.pem ]; then
    if [ -f certs/current_ip ] && [ "$(cat certs/current_ip)" = "$IP" ]; then
        echo "憑證已是最新（含 $IP），沿用。"
        exit 0
    fi
    echo "IP 已變更（$IP），重新產生憑證..."
else
    echo "產生新憑證..."
fi

HOSTNAME_SHORT=$(hostname 2>/dev/null | sed 's/\..*//' || echo jetson)
openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
    -keyout certs/key.pem -out certs/cert.pem \
    -subj "/CN=$IP" \
    -addext "subjectAltName=IP:$IP,DNS:localhost,DNS:$HOSTNAME_SHORT.local" \
    -addext "basicConstraints=critical,CA:TRUE" \
    >/dev/null 2>&1

if [ -f certs/cert.pem ] && [ -f certs/key.pem ]; then
    echo "$IP" > certs/current_ip
    echo "✅ 憑證已產生（CN/SAN: $IP）"
else
    echo "❌ 憑證產生失敗" >&2
    exit 1
fi
