# 交接文檔（給下一個 AI）

> 本文件由前一 AI 在**狀態不穩**時撰寫，用於讓下一個 AI 快速接手。
> 請先完整讀取以下文件以建立脈絡：
> - `README.md`
> - `HANDOVER.md`（舊版交接，內容仍有效）
> - `CHECKLIST.md`
> - `TRAIN_ON_LAPTOP.md`
> - `DATASET_INVENTORY.md`
> - `webUI_workspace/main.py`、`webUI_workspace/static/app.js`

---

## 1. 任務目標
完成「sixseven-project」飛機缺陷偵測系統的最終交付：
1. 在 Jetson（本機 `/home/sixseven/sixseven-project`）把 7 類模型部署到 WebUI 串流模型。
2. 用筆電訓練好的 `best.pt`（7 類、yolov8n）取代目前 WebUI 使用的 `yolo11s`。
3. 驗證 7 類載入與推論正常。
4. 更新交接/自檢文件。

## 2. 目前狀態（截至交接時）

### 已完成
- v3 資料集定案（7 類）：`[Crack(0), Dent(1), Missing_Fastener(2), Skin_Cover(3), Fuselage_damage(4), Wing_damage(5), Engine_damage(6)]`
  - train=8265 / valid=801 / test=311，兩兩互斥、無壞圖。
- 筆電 GPU 驅動問題處置：
  - 原 `nvidia-open-dkms` 對 RTX 3050 不穩，造成隨機 `CUDA error: illegal memory access`。
  - **已更換為專有 `nvidia` 驅動並重開機**，`nvidia-smi` 顯示 `NVIDIA-SMI 610.57.04, KMD 610.57.04, CUDA UMD 13.3`。
  - 驅動層問題已改善：錯誤從「illegal memory access」轉為「cuDNN `CUDNN_STATUS_EXECUTION_FAILED`」。
- 筆電訓練環境（**重開機後 /tmp 被清空，已重建到 home**）：
  - venv：`~/yolo-venv`（Python 3.12 + torch 2.13.0+cu126 + torchvision 0.28.0 + ultralytics 8.4.136）。
- **7 類 yolov8n 訓練已完成**：

  ```
  /home/alice/yolo_workspace_v3/runs/detect/runs/yolov8n-v3/weights/
      best.pt   (6229162 bytes)
      last.pt   (6229162 bytes)
  ```
  - 手動驗證：`best.pt` 可被 ultralytics 載入，`model.names` 為上述 7 類，對一張 valid 圖 predict 成功回傳 1 個 bbox。

### ⚠️ 待確認的疑點
- `results.csv` 最後一行（epoch 30）metrics 顯示 `nan`（loss nan、mAP50=0），但 **best.pt 存在、大小正確、可正常載入與推論**。
- **下一個 AI 必須驗證**：best.pt 的實際品質是不是真的正常。若 loss 曾發散到 nan，建議檢查 best epoch 對應的 mAP；必要時重訓。
  - 檢查指令：在筆電 `~/yolo_workspace_v3` 下
    ```
    ~/yolo-venv/bin/python -c "from ultralytics import YOLO
    m=YOLO('runs/detect/runs/yolov8n-v3/weights/best.pt')
    print(m.val(data='data.yaml'))"
    ```

## 3. 連線資訊（SSH 到筆電）
- 筆電：`alice@192.168.0.39`（注意：正確網段是 `192.168.x.x`，**不是** `192.169`）。
- 密碼：`1`。本機無 `sshpass`，已在使用者空間編譯一份：
  ```
  P=/tmp/opencode/sshpass/bin/sshpass
  $P -p '1' ssh -o StrictHostKeyChecking=no alice@192.168.0.39 "..."
  ```
  - ⚠️ `/tmp` 每次重開機會被清空，sshpass 也須重編才可用。

## 4. 下一步（下一個 AI 請依序執行）
1. **驗證 best.pt 品質**（見第 2 節疑點）。若正常，繼續；若發散，判斷是否需重訓（用 `~/yolo-venv` + amp=False，epochs 可調，再套同一路徑）。
2. **把 best.pt 帶回 Jetson**：
   ```
   P=/tmp/opencode/sshpass/bin/sshpass
   $P -p '1' scp alice@192.168.0.39:/home/alice/yolo_workspace_v3/runs/detect/runs/yolov8n-v3/weights/best.pt \
     /home/sixseven/sixseven-project/yolov8n_v3_best.pt
   ```
3. **部署到 WebUI**：看 `webUI_workspace/main.py` 如何載入串流模型，把路徑從 `yolo11s` 換成 `yolov8n_v3_best.pt`（保留 `.bak` 備份原模型）。
4. **驗證 7 類載入**：啟動 WebUI，確認 model names 為 7 類、串流推論正常。
5. **更新文件**：`CHECKLIST.md`、`HANDOVER.md` 反映「驅動已換專有版、best.pt 已部署、7 類生效」。

## 5. Jetson 相關路徑
- 專案根：`/home/sixseven/sixseven-project/`
- WebUI：`webUI_workspace/main.py` + `webUI_workspace/static/app.js`
- 現有模型：`webUI_workspace/models/{yolo11n,yolo11s,yolo26n}.pt`
- 舊 7 類 train-32：`runs/detect/runs/detect/train-32/weights/{best,last}.pt`
- 訓練包：`yolov8n_v3_training_pack.zip`

## 6. 給接手 AI 的提醒
- 本交接作者前一階段發生**輸出迴圈故障**（重複文字但不執行工具）。若你接手後也看到類似異狀，請中斷並以最小、乾淨的指令逐步執行。
- 筆電 GPU 仍可能出現 cuDNN 偶發失敗（`CUDNN_STATUS_EXECUTION_FAILED`），這是 cuDNN 對 RTX 3050 的相容性問題，不是資料/模型問題；可用 `amp=False` 或換 torch build 緩解。
