#!/bin/bash
# 動態內網 HTTPS 憑證產生器
# 用途：手機連熱點時網址是 https://10.42.0.1（固定），但其他網路下 IP 會變。
#       此腳本產生「同時包含熱點固定 IP 10.42.0.1 與目前所有內網 IP」的自簽憑證，
#       SAN 清單有變時才重生，避免每次啟動都重做。
#
# 用法：./gen_cert.sh   （在 webUI_workspace/ 目錄下執行；可由 tools/setup_env.sh 呼叫）
# 產出：certs/cert.pem, certs/key.pem, certs/san.txt, certs/current_ip

cd "$(dirname "$0")"
mkdir -p certs

AP_IP="${AP_IP:-10.42.0.1}"
HOSTNAME_SHORT=$(hostname 2>/dev/null | sed 's/\..*//' || echo jetson)

# 熱點固定 IP 一律排第一
IPS="$AP_IP"
# 再加入目前所有對外 IPv4（排除 loopback / docker）
for ip in $(hostname -I 2>/dev/null); do
    case "$ip" in
        127.*|172.17.*|172.18.*) continue ;;
    esac
    [ "$ip" = "$AP_IP" ] && continue
    IPS="$IPS $ip"
done

# SAN 清單：先所有 IP，再 DNS 名稱（順序固定，方便比對）
# 含短主機名 sixseven-project 與 mDNS 名 sixseven-project.local
SAN=""
for ip in $IPS; do
    SAN="${SAN:+$SAN,}IP:$ip"
done
SAN="$SAN,DNS:localhost,DNS:$HOSTNAME_SHORT,DNS:$HOSTNAME_SHORT.local"

# 第一個非熱點 IP（若無則用熱點 IP）寫入 current_ip，供 start_https.sh 顯示
FIRST_IP=$(echo "$IPS" | awk '{print ($2!="" ? $2 : $1)}')

# SAN 沒變且憑證已存在 → 沿用
if [ -f certs/cert.pem ] && [ -f certs/key.pem ] \
   && [ -f certs/san.txt ] && [ "$(cat certs/san.txt)" = "$SAN" ]; then
    echo "憑證已是最新（SAN 未變），沿用。"
    echo "$FIRST_IP" > certs/current_ip
    exit 0
fi

echo "產生新憑證（host IP：$IPS）..."
openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
    -keyout certs/key.pem -out certs/cert.pem \
    -subj "/CN=$AP_IP" \
    -addext "subjectAltName=$SAN" \
    -addext "basicConstraints=critical,CA:TRUE" \
    >/dev/null 2>&1

if [ -f certs/cert.pem ] && [ -f certs/key.pem ]; then
    echo "$SAN" > certs/san.txt
    echo "$FIRST_IP" > certs/current_ip
    echo "✅ 憑證已產生（CN=$AP_IP；SAN=$SAN）"
else
    echo "❌ 憑證產生失敗" >&2
    exit 1
fi
