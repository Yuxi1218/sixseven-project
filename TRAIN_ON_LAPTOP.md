# 在 RTX 3050 Laptop 上訓練 yolov8n（7 類）串流模型

本資料夾為 **yolov8n 7 類串流模型訓練包**，資料來自 `yolo_workspace_v3/`（416MB）。

## 1. 環境準備（在 3050 筆電，一次性）

需 NVIDIA 驅動 + Python 3.8+ 環境，安裝 ultralytics（Pytorch 版會自動帶 CUDA torch）：

```bash
pip install ultralytics
python -c "import torch; print(torch.cuda.is_available())"   # 應回 True
```

> 若 torch 未綁 CUDA，重裝：`pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121`

## 2. 訓練命令（30 epochs）

在**本資料夾內**執行（data.yaml 用相對路徑 train/val/images，所以要在這裡跑）：

```bash
cd <解壓後的資料夾>/yolo_workspace_v3
python -c "
from ultralytics import YOLO
m = YOLO('yolov8n.pt')          # 自動下載官方 pretrained yolov8n
m.train(data='data.yaml', epochs=30, imgsz=640, batch=8,
        device=0, amp=True, project='runs', name='yolov8n-v3')
"
```

- 3050 Laptop **4GB VRAM**：用 `batch=8`（安全值，AMP 混合精度省記憶體；`train.py` 已設好，直接跑即可）。
- 若 `torch.cuda.OutOfMemoryError`，把 `batch` 改 `4`；還是不行就 `imgsz=512`。
- 預估 **30 epochs ≈ 1~2 小時**（遠快於 Jetson 的 8 小時）。
- 產出：`runs/yolov8n-v3/weights/best.pt`

## 3. 驗證

```bash
python -c "
from ultralytics import YOLO
m=YOLO('runs/yolov8n-v3/weights/best.pt')
print(m.model.nc, list(m.names.values()))   # 應為 7 類
"
```

## 4. 把 best.pt 帶回 Jetson

把 `runs/yolov8n-v3/weights/best.pt` 複製到 Jetson 的
`webUI_workspace/models/yolo11n.pt`（串流模型），取代目前的 yolo11s 大模型：

```bash
cp best.pt /home/sixseven/sixseven-project/webUI_workspace/models/yolo11n.pt
```

> `yolo11s.pt`（診斷模型）沿用 Jetson 上的 7 類大模型，不用動。
> 原串流模型已有備份 `webUI_workspace/models/yolo11n.pt.*.bak`，可回滾。

## 5. 確認類別順序（重要）

新模型類別順序與現有 v3 data.yaml 一致：
`Crack, Dent, Missing_Fastener, Skin_Cover, Fuselage_damage, Wing_damage, Engine_damage`
（索引 0~6）。只要用本包 data.yaml 訓練，順序即正確，可直接用於 WebUI。
