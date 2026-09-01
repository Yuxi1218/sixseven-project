#!/bin/bash
# 部署 yolo11n 訓練完成的 best.pt 為串流模型
# 用法：./deploy_stream_model.sh [訓練輸出路徑] 
# 預設：runs/detect/yolo11n-stream/weights/best.pt
#
# 會把訓練出的 best.pt 複製到 webUI_workspace/models/yolo11n.pt
# 舊模型備份為 yolo11n.pt.<timestamp>.bak

set -e
cd "$(dirname "$0")"

SRC="${1:-runs/detect/yolo11n-stream/weights/best.pt}"
DST="webUI_workspace/models/yolo11n.pt"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

if [ ! -f "$SRC" ]; then
    echo "❌ 源模型不存在: $SRC"
    exit 1
fi

# 備份舊模型
if [ -f "$DST" ]; then
    BAK="${DST}.${TIMESTAMP}.bak"
    cp "$DST" "$BAK"
    echo "📦 備份舊模型: $BAK"
fi

cp "$SRC" "$DST"
echo "✅ 串流模型已部署: $DST"

# 驗證模型載入
/usr/bin/python3 -c "
from ultralytics import YOLO
m = YOLO('$DST')
print(f'模型 classes: {len(m.names)} 類')
print(f'類別: {list(m.names.values())}')
" && echo "✅ 7 類載入驗證通過" || echo "⚠️ 載入驗證失敗"