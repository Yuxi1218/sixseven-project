#!/bin/bash

echo "=== Sixseven Wing Damage Detection System ==="
echo ""

cd "$(dirname "$0")"

echo "Step 1: Starting server..."
echo "Access at: http://<jetson-ip>:8000"
echo ""

python main.py