# sixseven-project — 機翼損傷檢測系統

> 一群飛修人和一個電子人的專題：在 **Jetson Orin Nano** 上用 **AI（YOLO）即時偵測機翼損傷**，
> 手機連上現場熱點、開瀏覽器就能看到「AI 幫你把損傷框起來」。
> 完整白話交接與操作指引在 `MASTER_HANDOVER.md`。

---

## 重要：先看 GitHub 再看實機

**流程請一律：先在 GitHub（本 repo）看懂文件 → 再上 Jetson 實機動手。**

這樣做的好處：
1. 文件永遠是最新、唯一的「版本真相」（比實機記憶可靠）。
2. 避免「實機上改壞了、程式碼變更遺失」的風險——實機 `main.py` / `app.js` 等有改動者，**務必先 commit 到 GitHub**。
3. 下一個接手的人（AI 或隊友）只要開這個 repo 就能無痛接手，不用回去翻實機。

> 實機位置：`/home/sixseven/sixseven-project`（Jetson 本機）。遠端 GitHub 當「文件與程式碼的正式副本」。

---

## 這套系統在做什麼

```
手機相機（眼睛） ──WiFi──> Jetson 主機（大腦） ──> 手機畫出綠色框給你看
                     認出「這是裂痕 / 凹痕 / 缺鉚釘 / ...」
```

- **YOLO11** 找損傷框（7 類：Crack / Dent / Missing_Fastener / Skin_Cover / Fuselage_damage / Wing_damage / Engine_damage）。
- **FastAPI** 當網頁後端（port 8000），手機透過 HTTPS 連上。
- **WebRTC（aiortc）** 把手機相機畫面向 Jetson 傳送、再由 DataChannel 把框座標傳回手機疊框（DMA 式旁路，快又準）。
- **Ollama（gemma3:1b）** 在偵測到嚴重損傷時生成維修建議報告。

---

## 兩個核心入口（先讀這兩個）

| 文件 | 給誰看 | 內容 |
|---|---|---|
| **[MASTER_HANDOVER.md](./docs/MASTER_HANDOVER.md)** | 完全不會寫程式的人 | 唯一的操作交接：現場開機 SOP、帳密、故障排除、哪裡要調速查表、程式逐段解析、詞彙表。**先看這本。** |
| **[AGENTS.md](./AGENTS.md)** | 下一個接手 AI / 工程師 | 作業標準速查：連線、常用指令、防呆規則、程式碼速查、訓練部署工作流、驗收方式。不想看 MASTER 的話看這個。 |

---

## 全部文件索引

### 交接與操作
- **[MASTER_HANDOVER.md](./docs/MASTER_HANDOVER.md)** — 給初學者的總交接，唯一有效操作文件（取代舊 HANDOVER）。
- **[AGENTS.md](./AGENTS.md)** — 給接手 AI/工程師的作業標準（建議新 AI 先讀）。
- **[SPECIAL_TOPIC_REPORT.md](./docs/SPECIAL_TOPIC_REPORT.md)** — 正式專題報告（每章能向老師簡報；§7.2 有「待填入」的模型數據需補）。
- **[DATASET_INVENTORY.md](./docs/DATASET_INVENTORY.md)** — 資料集盤點（5 個 Roboflow 來源、類別對映決策）。

### 資料集與訓練
- **[TRAIN_ON_LAPTOP.md](./docs/TRAIN_ON_LAPTOP.md)** — 在筆電上重訓模型的指引（資訊也併入 MASTER 第 7 部）。

### 程式解析
- **`webUI_workspace/main.py`** — FastAPI 總店長（後端主程式）。
- **`webUI_workspace/webrtc_stream.py`** — WebRTC 串流模組（手機↔Jetson）。
- **`webUI_workspace/static/app.js`** — 手機前台邏輯（開相機、疊框、顯示）。
- **`webUI_workspace/templates/index.html`** — 手機畫面結構。
- 程式逐段白話解析已寫進 **MASTER_HANDOVER.md 第 6 部**。

> 舊版文件（`HANDOVER.md`、`HANDOVER_FOR_NEXT_AI.md`、`HANDOVER_FOR_BEGINNERS.md`、`CHECKLIST.md`、`CODE_EXPLANATION_FOR_BEGINNERS.md`）**已全部併入 MASTER_HANDOVER.md**，保留僅供歷史參考，更新請寫在 MASTER。

---

## 目錄結構

```
sixseven-project/
├── docs/                       # 所有文件（本手冊、報告、資料盤點、舊交接）
├── webUI_workspace/            # 網頁應用（主系統）
│   ├── main.py                 # FastAPI 後端（port 8000）
│   ├── webrtc_stream.py        # WebRTC 串流
│   ├── templates/index.html    # 手機畫面
│   ├── static/app.js           # 前端邏輯
│   ├── models/                 # yolo11s.pt（現役 7 類）+ .bak 備份
│   ├── certs/                  # HTTPS 自簽憑證（10 年效期，gitignore）
│   └── start.sh / start_https.sh / gen_cert.sh / setup_ap.sh / switch_ap_safe.sh
├── tools/                      # 工具
│   ├── deploy_watcher.py       # 自動部署（cron 每 5 分）
│   ├── train_monitor.py        # 訓練進度監控（cron 每 15 分）
│   └── scripts_*.py            # 資料集重建/清理 v3 用
├── pretrained/                 # 原始預訓練模型（yolo11n/s/26n .pt）
├── yolo_workspace_v4_bal/      # 現役訓練資料（train 17,123 / valid 801，已拉回本機）
├── yolo_workspace{,_v2,_v3,_v4,_raw}/   # 資料集舊版（保留供歷史）
└── runs/detect/                # 過往訓練輸出
```

---

## 快速開始（現場開機）

```
1. 開 Jetson → 等 1~2 分鐘
2. 手機連熱點 AirCraft67Team
3. 瀏覽器開 https://10.42.0.1:8000
4. 允許使用相機 → 看到綠框 = 成功
```

細節（含帳密、故障排除、現場熱點救援）全在 **MASTER_HANDOVER.md 第 3、4 部**。

---

## 目前狀態（2026-09-08）

- 7 類模型已重訓並部署（19.1MB，mAP@0.5 ≈ 0.58）。
- 自動部署 watcher 運作中（每 5 分偵測訓練結果）。
- 疊框偏移 bug 已修復。
- **開機自啟已設**：`sixseven-webrtc.service`（systemd），WebUI+HTTPS 開機自動起來、崩潰自拉。
- 完整平衡資料集已拉回本機：`yolo_workspace_v4_bal/`（train 17,123 / valid 801）。
- 詳細狀態與已知限制：見 `MASTER_HANDOVER.md` 第 8 部。

---

## Jetson 開機/環境備註（歷史）

- Jetson Orin Nano 由 NVIDIA 出品的高性能開發板，常被用於邊緣運算與機器人 / AI 伺服器。
- 首次使用需配置語言、網路、使用者、地區等；系統與瀏覽器安裝細節見舊版交接（MASTER 已涵蓋操作層）。
- 更多硬體層說明：見 `runs/detect/` 內訓練紀錄與 `AGENTS.md`。

*與實機同步的正式副本。任何在實機上的程式碼修改，請 commit 回本 repo。*