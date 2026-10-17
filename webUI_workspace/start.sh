#!/bin/bash

echo "=== Sixseven Wing Damage Detection System ==="
echo ""

cd "$(dirname "$0")"

echo "Step 1: Starting server..."
echo "Access at: http://<jetson-ip>:443  (正式請用 ./start_https.sh，HTTPS 免打埠號)"
echo ""

python main.py