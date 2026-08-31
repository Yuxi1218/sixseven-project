#!/bin/bash
# 內網 HTTPS 啟動（camera 串流需要安全來源；非 localhost 瀏覽器需 HTTPS）
# 自動處理手機熱點 IP 變動：啟動時呼叫 gen_cert.sh 確認/重生憑證。
#
# 用法：./start_https.sh
# 存取：https://<目前IP>:8000
#   - 手機瀏覽器需「進階 → 繼續前往」接受自簽憑證後才能用相機
#   - 若換了熱點/IP，直接重跑此腳本即可

echo "=== Sixseven Wing Damage Detection System (HTTPS) ==="
echo ""
cd "$(dirname "$0")"

echo "Step 1: 確認/產生 HTTPS 憑證..."
./gen_cert.sh
if [ $? -ne 0 ]; then
    echo "❌ 憑證產生失敗，改用 HTTP 啟動（相機串流可能失效）。" >&2
    python3 main.py
    exit 1
fi
CERT_IP=$(cat certs/current_ip 2>/dev/null)

echo ""
echo "Step 2: 啟動 HTTPS server..."
echo "   存取網址：https://$CERT_IP:8000"
echo "   同 IP 的裝置需先點「進階 → 繼續前往」信任憑證"
echo ""
python3 main.py --ssl
