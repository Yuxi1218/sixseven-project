# AGENTS.md — 給接手者（AI 或工程師）的專案作業標準

> 這份文件是**給會寫程式的人／下一個 AI 看**的速查規範。
> 完全不會寫程式的人請看 `MASTER_HANDOVER.md`。
> 讀這份之前請先知道：這是台 Jetson Orin Nano 上的即時機翼損傷偵測系統，
> 手機走 WebRTC 把鏡頭畫面送到 Jetson，YOLO 找框，框座標透過 DataChannel 疊回手機。

---

## 1. 環境與連線

| 項目 | 值 |
|---|---|
| 主機（Jetson） | `sixseven` / `67`（sudo 同密碼），專案在 `/home/sixseven/sixseven-project` |
| 訓練筆電 | `alice@192.168.0.111` / `1` |
| 筆電 venv | `~/ml/bin/python`（torch + ultralytics + cv2 5.0.0） |
| 主系統 | FastAPI + Ultralytics YOLO11 + Ollama(gemma3:1b) + WebRTC(aiortc) |
| HTTPS 網頁 | `https://10.42.0.1:8000`（現場熱點 AirCraft67Team） |

SSH 到 Jetson 本機即可作業（本機就是伺服器）。要連筆電用 paramiko（本機無 sshpass，`/tmp/opencode/sshpass` 開機會被清）。

## 1.1 開機自啟動（systemd）

- **`sixseven-webrtc.service`**：開機自動啟動 webUI（HTTPS），崩潰自動重拉（Restart=always）。
- 用現有 10 年有效期證書 `webUI_workspace/certs/cert.pem`，**不會每次重簽**。
- 指令：
  ```bash
  sudo systemctl status sixseven-webrtc   # 看狀態
  sudo systemctl restart sixseven-webrtc  # 重啟服務（新做法）
  sudo systemctl disable sixseven-webrtc  # 關閉開機自啟
  ```
- 舊法 `bash /tmp/opencode/start_webrtc.sh` 仍可用（偵錯 log 不同），但正式用 systemd。

## 2. 常用指令（都在 Jetson 上）

```bash
# 重啟網頁服務【首選】用 systemd
sudo systemctl restart sixseven-webrtc

# 舊法仍可用（但 log 不一定對得上 systemd）
bash /tmp/opencode/start_webrtc.sh

# 看運行 log
tail -f /tmp/opencode/https_webrtc27.log    # Ctrl+C 離開

# 語法檢查（改過 main.py / webrtc_stream.py 後必做）
python3 -m py_compile /home/sixseven/sixseven-project/webUI_workspace/main.py
python3 -m py_compile /home/sixseven/sixseven-project/webUI_workspace/webrtc_stream.py

# 看自動部署狀態
tail -5 /tmp/opencode/deploy_watcher.log        # watcher 每 5 分跑
ls /tmp/opencode/deployed.lock                  # 存在=模型已部署完成

# 看訓練監控記錄（筆電訓練中）
tail -6 /tmp/opencode/train_monitor.log

# 檢查服務健康
curl -k https://10.42.0.1:8000/status          # 回傳 yolo/ollama 狀態 JSON
```

## 3. 目前狀態（2026-09-08）

- 7 類模型已重訓並**已部署**：`webUI_workspace/models/yolo11s.pt`（19.1MB，平衡後資料集，mAP@0.5≈0.58）。
- 服務運行中；`deployed.lock` 已建立（watcher 不會重複部署）。
- 疊框偏移 bug 已修：`webrtc_stream.py` 上游收幀是**正確版**（無轉置、無 debug 存圖）。
- **完整資料集已拉回本機**：`yolo_workspace_v4_bal/`（train 17,123 / valid 801，7 類平衡，2.37GB）＋ 筆電同名資料夾同步。
- **開機自啟已設**：`sixseven-webrtc.service`（systemd），webUI+HTTPS 開機自動起來、崩潰自拉。
- 專案結構已整理：文件在 `docs/`、工具在 `tools/`、原始預訓練模型在 `pretrained/`。

## 4. 防呆規則（改了會出事，勿動）

1. **`webrtc_stream.py::_consume_upstream`（約 98~116 行）**：上游收幀只做「收→RGB翻BGR→存」。
   不要加轉置（transpose）、不要加 cv2.imwrite/存圖 debug。前一手在此踩雷造成框整體偏移。
2. **`webUI_workspace/models/`**：現役模型是 `yolo11s.pt`。換模型前先 `cp` 留 `.bak`。
3. **`/etc/modprobe.d/rtl8822ce-ap.conf`**：熱點穩定設定（關省電/固定 2.4G 頻道 1），勿改。
4. **cron**：兩條排程不可刪——
   - `*/5 * * * * /usr/bin/python3 /home/sixseven/sixseven-project/tools/deploy_watcher.py`（自動部署）
   - `*/15 * * * * /usr/bin/python3 /home/sixseven/sixseven-project/tools/train_monitor.py >/dev/null 2>&1`（進度監控）
5. **LLM gate**：`MAJOR_CLASSES`（main.py:641）決定何時叫 Ollama；輕微類別直接回應。不要把 `_should_invoke_llm` 拿掉（會讓每次診斷都等 1~2 分鐘）。

## 5. 程式碼速查（改哪看哪）

| 想改 | 檔案:位置 |
|---|---|
| 信心門檻/解析度/模型路徑 | `webUI_workspace/main.py` `CONFIG`（31~41） |
| 類別中文 | `main.py` `CLASS_NAMES_ZH`（45~53） |
| 疊框縮放運算 | `webUI_workspace/static/app.js` `_coverRect()`（284~296）與 `drawDetections()`（298~326） |
| WebRTC 上下游 | `webUI_workspace/webrtc_stream.py` |
| 定格診斷 3 次合併 | `main.py` `infer_hd`（576~622） |
| 網頁結構 | `webUI_workspace/templates/index.html` |

## 6. 訓練與部署工作流（想讓模型變強）

1. 在筆電（`~/ml`）重訓：資料在 `~/yolo_workspace_v4_bal`（train 17,123 / valid 801，7 類已平衡）。
   例：`~/ml/bin/python ~/train_bal_fast.py`（imgsz=512, batch=16, epochs=120, patience=30）。
   產出 `~/runs/train-bal-7cls/weights/best.pt`。
2. **不用手動部署**：Jetson 的 `tools/deploy_watcher.py` 每 5 分偵測訓練結束 → 自動下載覆蓋 → 寫 lock → 重啟。
   若 watcher log 持續出現錯誤，檢查它用的是 `sftp.stat()`（不是 `c.stat()`，paramiko 沒有這方法）。
3. 手動立刻更新：`python3 tools/deploy_watcher.py`？ 不行——有 lock 就不會動。
   正確手動流程：先 `rm /tmp/opencode/deployed.lock`，再跑 `python3 tools/deploy_watcher.py`，或直接
   從筆電 `~/runs/train-bal-7cls/weights/best.pt` sftp 拉到本機覆蓋 `models/yolo11s.pt` 後 `bash /tmp/opencode/start_webrtc.sh`。

## 7. 驗收方式（改完如何確定沒壞）

- `python3 -m py_compile` 通過。
- 服務起來後 `tail -f` log 見到 `Models loaded!` 與 `Uvicorn running on https://0.0.0.0:8000`。
- `curl -k https://10.42.0.1:8000/status` 回 `{"yolo_loaded": true, ...}`。
- 手機連熱點開 https://10.42.0.1:8000 → 允許相機 → 綠框對準物體邊緣 = 疊框正確。
- 定格診斷：按「開始診斷」能出框好圖＋報告，且不會卡超過 2 分鐘。

## 8. 交接文件索引（全部在 `docs/`）

- `MASTER_HANDOVER.md` — 給初學者的總交接（含「哪裡要調」速查表）。這份是唯一有效的操作交接。
- `SPECIAL_TOPIC_REPORT.md` — 正式專題報告（每章需能向老師簡報；§7.2 有「待填入」的模型數據待補）。
- `DATASET_INVENTORY.md` — 資料集盤點（5 個 Roboflow 來源、類別對映決策）。
- 舊交接（HANDOVER*.md、CHECKLIST.md、CODE_EXPLANATION_FOR_BEGINNERS.md）已併入 MASTER，僅供歷史參考，更新請寫在 MASTER。