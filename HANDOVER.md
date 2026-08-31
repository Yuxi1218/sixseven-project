# 交接文件 / HANDOVER

> 專案：**Sixseven — 飛機缺陷偵測與診斷系統**
> 硬體：Jetson Orin（7.6GB GPU 記憶體 / IGPU）
> 語言：Python + FastAPI + Ultralytics YOLO11 + Ollama（gemma3）

本文件為完整技術交接：架構、目錄、資料集與類別、模型訓練歷程、網頁 API 與用法、已知問題與待辦。

---

## 1. 系統架構

```
瀏覽器 (Web UI)
   │  GET /  (index.html)
   │  POST /infer             每 ~250ms 送 camera 幀 → yolo11n（串流，輕量）
   │  POST /diagnose          取目前幀 → yolo11s（診斷，較重）+ Ollama 生成報告
   │  POST /diagnose_upload   上傳圖片 → yolo11s + Ollama
   ▼
FastAPI 服務 (webUI_workspace/main.py, port 8000)
   ├─ YOLOManager    載入 yolo11n（串流）與 yolo11s（診斷）；自動偵測 GPU/CPU
   └─ OllamaManager  localhost:11434/api/generate, model=gemma3:1b
```

- 串流採「真串流」：前端 JavaScript 每 250ms 用 `getUserMedia` 抓 camera 幀，base64 送 `/infer`，回傳 annotated 幀後畫回 `<canvas>`，並更新 FPS / 偵測數 / 狀態指示。
- 診斷：`/diagnose`（用最近一幀）或 `/diagnose_upload`（用上傳圖）先做 YOLO，把 detections 摘要餵給 Ollama 產生維修／處置建議。

---

## 2. 目錄結構

```
sixseven-project/
├── webUI_workspace/           # 網頁應用
│   ├── main.py                # FastAPI 後端（已修復）
│   ├── templates/index.html   # 前端頁面
│   ├── static/                # app.js / style.css / icon-{192,512}.png / manifest.json
│   ├── models/                # yolo11n.pt（串流）、yolo11s.pt（診斷）
│   ├── convert_model.py       # .pt → TensorRT engine .
│   ├── start.sh               # 啟動（cd 至本目錄後 python main.py）
│   └── requirements.txt       # 依賴（含 requests）
├── yolo_workspace/             # 舊工作區（train/valid），孤立標籤已移至 labels_orphan/
├── yolo_workspace_v2/          # 舊工作區 v2（train-31 在此訓練）
├── yolo_workspace_v3/         # ⭐ 現行乾淨資料集（7 類，本文件重點）
├── yolo_workspace_raw/        # 5 個原始 zip 重新解壓後的結果（盤點用）
├── runs/detect/train-{n}/     # 過往訓練輸出
├── DATASET_INVENTORY.md       # 5 個 raw dataset 的類別盤點
├── CHECKLIST.md               # 自撿表 / 完成與剩餘風險
├── scripts_inventory.py       # 產生 DATASET_INVENTORY.md
├── scripts_rebuild_v3.py      # raw → v3（初始 10 類）
├── scripts_fix_v3_polygons.py # polygon line → bbox
└── scripts_finalize_v3_7cls.py# 10 類 → 7 類定案（reindex）
```

---

## 3. 資料集與類別

### 3.1 原始資料（5 個 Roboflow zip）
來源：`/home/sixseven/yolo_workspace/temp/*.zip` → 已解至 `yolo_workspace_raw/`。詳見 `DATASET_INVENTORY.md`。

| Raw dataset | 原始類別數 / 類別 |
|---|---|
| Aircraft Damage Detection v5 | 2：crack, dent |
| Aircraft Damage v2 | 4：hole, leak, scratch, stucturaldamage |
| Aircraft Defects v2 | 3：Crack, Dent, Missing Fastener |
| ac_damage_detector v4 | 1：damages |
| ac_damage_detector v5 | 11（詳細見 inventory） |

### 3.2 ⭐ 現行資料集：`yolo_workspace_v3/`（7 類定案）

訓練/驗證/測試拆份：
- train: **8265** images = labels
- valid: **801**
- test:  **311**

`data.yaml` 類別順序與 boxes 分布：
| 新 class id | 名稱 | boxes |
|---|---|---|
| 0 | Crack | 11623 |
| 1 | Dent | 9235 |
| 2 | Missing_Fastener | 7192 |
| 3 | Skin_Cover | 136 |
| 4 | Fuselage_damage | 834 |
| 5 | Wing_damage | 201 |
| 6 | Engine_damage | 136 |

> ⚠️ 類別極度不平衡：Skin_Cover(136)/Wing(201)/Engine(136) 遠少於前 3 類。少數類召回可能偏低，是後續 tuning 重點。

### 3.3 模糊類別決策（已文件化）
- `ac_damage_detector v4` 泛用類 `damages` → 對映 **Fuselage_damage**
- `Aircraft Damage v2` 的 `stucturaldamage`（拼字錯誤）→ 對映 **Fuselage_damage**
- `ac_damage_detector v5` 只保留 engine/fuselage/wing/skin-cover 4 類進 7 類集；其餘 7 類（burnt, cockpit-glass, faced-with-bird, icing, landing-gear, nose, tail）**丟棄**。
- 原 v3（10 類）中 Hole/Scratch/Leak 3 類被移除（class 3/4/5），再 reindex 成 7 類。
- 完整對映邏輯見 `scripts_finalize_v3_7cls.py`（`KEEP_WEIGHTS = [0,1,2,6,7,8,9]`）。

### 3.4 重建流程（新工作區，未覆寫舊檔）
```
scripts_rebuild_v3.py        ├─ 從 raw 建立 yolo_workspace_v3（10 類）
scripts_fix_v3_polygons.py   └─ 4084 個 polygon line 轉 bbox（0 unparsable / 0 dropped）
scripts_finalize_v3_7cls.py  └─ drop 3 類 → reindex 7 類 + 寫 data.yaml
```
驗證結果：0 bad / 0 out-of-range / 0 non-positive w-h；Ultralytics 可直接讀取（valid 801 張、0 corrupt、0 background）。視覺預覽圖已由使用者確認框選正確。

---

## 4. 模型訓練歷程

- 過往：`runs/detect/train-5 … train-31`，用 `yolo_workspace_v2/data.yaml`（較舊、混類、4 類 vocabulary）。
- **train-31**（舊基準）：`yolo11s.pt, epochs=30, imgsz=640, batch=2, workers=2` → mAP@0.5 ≈ **0.457**、mAP@0.5:0.95 ≈ 0.339。**類別為 4 個：damage, defect, crack, dent**（與新 v3 7 類不一致，為診斷「怪怪」的原因之一）。
- **train-32（現行，已完成）**：以 `yolo_workspace_v3/data.yaml`（**7 類**）重訓。
  - 命令：`yolo11s.pt, epochs=30, imgsz=640, device=0, batch=2, workers=2, project=runs/detect, name=train-32`
  - 注意：**batch 必須 ≤2、workers≤2**；default(batch=16/workers=8) 在 7.6GB Orin 上會 `NvMapMemAlloc error 12`（OOM）。
  - ⚠️ 因傳了 `project="runs/detect"`，實際輸出目錄為**巢狀** `runs/detect/runs/detect/train-32/`（不是單層）。
  - **最終指標（30 epochs）**：Precision ≈ 0.754、Recall ≈ 0.247、**mAP@0.5 ≈ 0.259**、mAP@0.5:0.95 ≈ 0.121。
    > 比 train-31 低的另一主因：**7 類且類別極不平衡**（Skin_Cover/Wing/Engine 各僅 ~130-200 boxes）。屬預期，但為後續 tuning 重點。
  - 產出：`runs/detect/runs/detect/train-32/weights/{best,last}.pt` + `results.csv`。

### ✅ WebUI 模型已更新（train-32 best.pt，7 類）
`webUI_workspace/models/{yolo11n,yolo11s}.pt` 已都換成 train-32 的 7 類 best.pt（同一個 yolo11s 架構）。
- 舊 4 類模型已備份：`webUI_workspace/models/yolo11n.pt.<ts>.bak`、`yolo11s.pt.<ts>.bak`（ts=20260831_165856）。
- 驗證：兩檔皆正確載入 7 類 `['Crack','Dent','Missing_Fastener','Skin_Cover','Fuselage_damage','Wing_damage','Engine_damage']`。
- ⚠️ 取捨：串流用的 `yolo11n.pt` 現在是 **yolo11s 架構**（約 19MB，非原先 5.5MB 輕量模型）→ 串流 FPS 會比原本低。此為換取類別一致性；若需更快串流，日後可另以 v3 資料訓一個真正的 yolo11n 7 類模型。

---

## 5. 網頁 API

| 方法 | 路徑 | 輸入 | 輸出 | 模型 |
|---|---|---|---|---|
| GET | `/` | — | index.html | — |
| GET | `/status` | — | `{yolo_loaded, ollama_available, model_available}` | — |
| POST | `/infer` | `{"image": <base64>}` | `{image: annotated b64, fps, detections}` | yolo11n（串流） |
| POST | `/diagnose` | —（用最近一幀） | `{annotated_image b64, detections, diagnosis}` | yolo11s + Ollama |
| POST | `/diagnose_upload` | `{"image": <base64>}` | 同上 | yolo11s + Ollama |

- 串流 /infer 用輕量 yolo11n（速度優先）；診斷用 yolo11s（準確優先）。
- 弱點：/infer 需先 `getUserMedia`（HTTPS 或 localhost 才可用 camera）。

### 5.1 診斷的 LLM 介入邏輯（重要）
`/diagnose` 與 `/diagnose_upload` **並非每次都呼叫 Ollama**。會先跑 YOLO，再依偵測類別判定是否為「重大/結構性損傷」：

- **呼叫 LLM（重大）**：偵測到任一 `MAJOR_CLASSES = {Fuselage_damage, Wing_damage, Engine_damage, damage}`
  → 回應含 `llm_invoked: true` 與完整 `diagnosis`（severity/repair/urgency）。
- **不呼叫 LLM（輕微/無）**：僅偵測到 Crack / Dent / Missing_Fastener / Skin_Cover，或無偵測
  → 回應 `llm_invoked: false`，`diagnosis` 為固定提示 `MINOR_MESSAGE`，**不佔用 Ollama、不等待**（立即回應）。

> 用意：避免每次診斷都等 ~1.5 分鐘的 LLM 生成；只有真正嚴重的結構損傷才需要詳細 LLM 建議。判定函數 `_should_invoke_llm()` 在 `main.py`。

### 啟動方式
```bash
cd webUI_workspace
# 先確保 Ollama 服務在 localhost:11434 且已有 gemma3:1b
./start.sh            # 純 HTTP（僅 localhost 可用相機）
./start_https.sh      # ⭐ 內網 HTTPS（手機熱點/遠端相機必須）
# 瀏覽器開 http://<jetson-ip>:8000   (HTTP) 或  https://<jetson-ip>:8000  (HTTPS)
```
依賴：見 `requirements.txt`。若在無外網環境，確保已安裝 `ultralytics`、`torch`、`opencv-python`、`fastapi`、`uvicorn`、`requests`。

### ⭐ 內網 HTTPS（手機相機串流專用，2026-09 新增）

瀏覽器 `getUserMedia`（camera）**在非 localhost 的 IP 上必須是 HTTPS** 才能用相機。比賽用手機連熱點時，Jetson 的 IP 是內網 IP（非 localhost），故需要 HTTPS。

- **動態憑證**：手機熱點會讓 Jetson 的 IP 變動，`gen_cert.sh` 啟動時自動抓目前 IP，若 IP 變了就重生含該 IP 的自簽憑證（SAN 含 `IP:<目前IP>, DNS:localhost`）。
- **啟動**：`./start_https.sh`（內部會先跑 gen_cert.sh 再以 HTTPS 起服務）。
- **手機體驗**：手機瀏覽器開 `https://<jetson-ip>:8000` 後，需點「進階 → 繼續前往」接受自簽憑證才能用相機。
- **相關檔案**：
  - `webUI_workspace/gen_cert.sh`    動態重生憑證（IP 變更自動處理）
  - `webUI_workspace/start_https.sh`  HTTPS 啟動（含 gen_cert）
  - `webUI_workspace/certs/`          憑證輸出（cert.pem / key.pem / current_ip）
  - `webUI_workspace/setup_ap.sh`     [備援] 把 Jetson 設成自身熱點（AP）
  - `main.py --ssl`                   由 `--ssl`/`--certfile`/`--keyfile` 參數控制

**手機熱點出問題時的備援（Jetson 當 AP）**：
```bash
cd webUI_workspace
sudo ./setup_ap.sh sixseven-ap 12345678   # 自建熱點，手機連它
./gen_cert.sh                              # 重生含 10.42.0.1 的憑證
./start_https.sh                           # 手機開 https://10.42.0.1:8000
```
> ⚠️ setup_ap.sh 會把 WiFi 介面改為 AP 模式，執行時可能使目前的 SSH/WiFi 連線中斷，僅在現場需要時才跑。

---

## 6. Deploy / 轉換（選用）
`convert_model.py <model.pt> [name]` 可把 .pt 轉 TensorRT engine（Jetson 加速），失敗會 fallback ONNX。

---

## 7. 已知問題 / 待辦

1. [x] **train-32 已完成 + WebUI 模型已更新**（7 類 best.pt；舊 4 類已備份 `.bak`）。mAP@0.5≈0.261（7 類、不平衡，預期較 v2 低）。
2. [x] **laptop yolov8n（7 類串流）訓練驗證失敗**：`~/yolo_workspace_v3/runs/detect/runs/yolov8n-v3/weights/best.pt` 最後一輪 loss 發散到 **nan**，實際 val mAP@0.5 ≈ 2.5e-06（幾乎全 0）。**已判定損壞、不可部署**，最終維持 Jetson 上的 train-32 yolo11s 作為部署模型（串流+診斷均用同一個 yolo11s 7 類）。
   - ⚠️ 若日後要真．yolo11n 輕量串流模型，需在筆電**重訓**（`amp=False`，見 `TRAIN_ON_LAPTOP.md`）。
3. [ ] 類別不平衡（Skin_Cover/Wing/Engine 過少）→ 之後可 oversample 或收集更多樣本，以提升少數類 mAP/recall。
4. [ ] **環境 bug：matplotlib 壞掉**（`from matplotlib import docstring` 找不到）。
   - 原因：`~/.local/.../matplotlib`（3.8.0）+ 系統 `/usr/lib/python3/dist-packages/mpl_toolkits` 版本衝突。
   - 影響：ultralytics 訓練結束的 final_eval 繪圖（PR_curve/results.png/confusion matrix）會 `ImportError` 中斷。**不影響** best.pt/last.pt/results.csv 存檔。
   - 修法（之後重訓前）：`pip install --upgrade mpl_toolkits` 或 `python -c "import matplotlib; matplotlib.use('Agg')"`，或統一用 pip 版 matplotlib。
5. [ ] WebUI CONFIG `device="cpu"` 是 fallback；實際在 Jetson 上會因 torch.cuda.is_available() 自動切 GPU。但若同時跑 Ollama，GPU/系統記憶體會被吃，需留意效能。
6. [ ] camera 串流需安全來源（localhost/HTTPS），部署到遠端需處理。
7. [ ] **串流與診斷皆用同一個 yolo11s 7 類模型**（`yolo11n.pt` 實為 yolo11s 架構），FPS 會較低；若需更快的真 yolo11n，另行重訓。
8. [ ] 端到端測試：啟動服務 → 接 camera → 上傳診斷，確認 7 類模型 + Ollama 皆正常。

## 7a. GitHub 同步狀態（2026-09-01）

- 本機 repo 已補上傳至 `origin/main`（Yuxi1218/sixseven-project）：
  - `yolo_workspace_v3/`（現行 7 類資料集，約 416MB）
  - `runs/detect/`（各 train-N 權重，含 train-32 7 類 best/last.pt）
  - `webUI_workspace/`（WebUI 程式+模型）
  - 根目錄 `yolo11n/s/yolo26n.pt`、`.md` 文件、`scripts_*.py`
- **明確排除**（`.gitignore`）：`yolo_workspace/temp/`、`yolo_workspace_raw/`、`yolo_workspace_v2/`、`yolov8n_v3_training_pack.zip`、`yolo_workspace/sixseven-project-main.zip`（皆 >100MB 或為舊/臨時資料集）。
- ⚠️ `yolo_workspace/`（舊資料集）維持 git 原本已追蹤的狀態，孤立標籤隔離的 local 修改**未** commit。

---

## 8. 回滾 / 安全網
- 資料集：`yolo_workspace/`、`yolo_workspace_v2/`、`yolo_workspace_raw/` 均保留，未覆寫。
- 模型：train-31 best.pt 保留於 `runs/detect/train-31/`；舊 `yolo11n/s.pt`（原始預訓練）在專案根與 `webUI_workspace/models/`。
- 任何合併類別需求，**務必**以 v3 的 `.py` scripts 重跑，勿再改 `merge_labels.py`。
