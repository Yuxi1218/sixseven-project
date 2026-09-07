# Sixseven 機翼損傷檢測系統 — 交接總手冊（給完全不會寫程式的人）

> 這是「一整份」交接文件，取代之前的 HANDOVER.md / HANDOVER_FOR_NEXT_AI.md / HANDOVER_FOR_BEGINNERS.md / CHECKLIST.md / TRAIN_ON_LAPTOP.md。
> 你只要讀這本就好。
> 這本書預設你**完全不會寫程式**，所有東西都用白話講。
> 寫程式的人（或下一個 AI）則請直接看根目錄的 `AGENTS.md`（幾分鐘就能上手）。

---

## 這本書怎麼用

- **有問題、想調整 → 看《第 1 部》**（寫在最前面，就是要你先看這）。
- 想了解系統在幹嘛 → 看《第 2 部》。
- 比賽/現場要開機 → 照《第 3 部》做。
- 想知道每一行程式碼在幹嘛 → 看《第 5、6 部》。
- 想讓判斷變準 → 看《第 7 部》。
- 名詞看不懂 → 跳《第 9 部詞彙表》。

---

# 第 1 部｜有問題先來這（哪裡要調 / 怎麼修）

## 1.1 現場最常做的事（照順序做）

| 我要做什麼 | 怎麼做 |
|---|---|
| 手機連不上 / 畫面卡 | 手機重開網頁、重連 WiFi `AirCraft67Team`（見 3.3） |
| 網頁開不起來（服務掛了） | 有人 SSH 到主機跑 `bash /tmp/opencode/start_webrtc.sh` |
| 想看主機現在運作正不正常 | `tail -f /tmp/opencode/https_webrtc27.log`，有 log 一直跳=正常 |
| 畫面有但沒框 | 先按「開始診斷」定格確認；再不行 = 模型沒學到，見第 7 部 |
| 熱點 AirCraft67Team 消失了 | 見 4.4「熱點救援」 |
| 想看手機端 debug 訊息 | 網頁**點標題連點 7 下**（開關隱藏除錯區，app.js:52） |

## 1.2 想「調設定 / 改功能」→ 改哪個檔案（速查表）

「哪裡要調」全部列在這裡。改完後**重啟服務**才會生效：
`bash /tmp/opencode/start_webrtc.sh`（在 Jetson 上執行）。

| 想調什麼 | 改哪個檔案 | 大概哪一行的設定 |
|---|---|---|
| 調「多確定才算偵測到」（敏感度） | `webUI_workspace/main.py` | `CONFIG["confidence"]`（目前 0.25 = 25%） |
| 判斷解析度 | `webUI_workspace/main.py` | `CONFIG["img_size"]` 與即時循環的 `imgsz=640` |
| 損傷類型的中文名稱 | `webUI_workspace/main.py` | `CLASS_NAMES_ZH` 那張表 |
| 換 AI 模型（權重檔） | `webUI_workspace/models/` | 放新檔，改 `main.py` 的 `yolo11s_model_path` |
| 即時診斷要用哪顆模型（準/輕） | `webUI_workspace/main.py` | `_web_infer_loop` 的 `use_large=True/False` |
| 哪幾類才算「嚴重」叫文字顧問 | `webUI_workspace/main.py` | `MAJOR_CLASSES`（機身/機翼/引擎/泛 damage） |
| 楞框顏色、粗細 | `webUI_workspace/static/app.js` | `ctx.lineWidth` / `ctx.strokeStyle`（疊框常數） |
| 下游畫面解析度 | `webUI_workspace/webrtc_stream.py` | `AnnotatedFrameTrack` 建構 `out_width/out_height` |
| 畫面顯示邏輯 | `webUI_workspace/static/app.js` | `showLocalCamera / showRemoteStream` |
| 網頁按鈕/面板長相 | `webUI_workspace/templates/index.html` | HTML 標籤 |
| 自動部署檢查頻率 | Jetson 的 cron | `crontab -e`，`*/5 * * * * .../tools/deploy_watcher.py` |
| 偵測框要對準的縮放運算 | `webUI_workspace/static/app.js` | `_coverRect()`（**別亂改**，見 5.4） |

> 最重要防呆：`webUI_workspace/webrtc_stream.py` 上游收幀那段（`_consume_upstream`）**現在是正確版本**。
> 上一個版本曾在這裡加了轉置與存圖，造成框整個偏移——**不要在這裡加任何轉置或除錯存圖**。

## 1.3 常見「為什麼會這樣」（一句話解答）

1. **為什麼手機一定要用 https？** 瀏覽器政策：非 https 不給開相機。用 `https://10.42.0.1:8000`。
2. **為什麼有時看不到多個損傷？** 兩個模式都用同一個模型，看不到多半是「模型沒偵測到」（小類樣本少），不是顯示 bug。
3. **為什麼定格診斷比較穩？** 同一張圖跑 3 次再合併（main.py:592），漏檢率低很多。
4. **為什麼網頁上掛 `?v=15`？** 強制瀏覽器不舊版快取，現場永遠拿到最新前端。
5. **主機 Wi-Fi 熱點為何特別穩？** 我們關了 rtl8822ce 的省電休眠、固定 2.4GHz 第 1 頻道。設定在 `/etc/modprobe.d/rtl8822ce-ap.conf`，**不要亂改**。

## 1.4 改完程式後要做的檢查

```bash
# 主機上：確定語法沒寫錯
python3 -m py_compile /home/sixseven/sixseven-project/webUI_workspace/main.py
python3 -m py_compile /home/sixseven/sixseven-project/webUI_workspace/webrtc_stream.py

# 重啟服務
bash /tmp/opencode/start_webrtc.sh

# 看 log 有沒有錯誤
tail -f /tmp/opencode/https_webrtc27.log   # Ctrl+C 跳出
```

---

# 第 2 部｜這套系統在做什麼（白話版）

我們做了一個「眼睛 + 大腦」組合，用來檢查飛機表面有沒有損傷：

```
手機相機（眼睛） ──WiFi──> Jetson 主機（大腦） ──> 手機畫出綠色框給你看
                     認出「這是裂縫 / 凹痕 / 掉鉚釘 / ...」
```

- **手機**：負責當鏡頭，把畫面即時傳給主機（也可以上傳照片）。
- **Jetson 主機**：一台手掌大的小電腦，AI 判斷都在這裡。它認出「哪裡有損傷、是 7 類的哪一類」，然後把位置用綠框標出來。
- 不用手動操作：手機連上主機的 WiFi → 開瀏覽器 → 畫面自己開始偵測。

### 手機上有兩個模式

| 按鈕 | 名稱 | 做什麼 | 何時用 |
|---|---|---|---|
| 進網頁自動開始 | 即時診斷（Live） | 鏡頭對哪，框跟著即時移動 | 平時掃描、比對 |
| 開始診斷 | 定格診斷 | 凍結畫面，主機用最高品質再確認，同一張跑 3 次取最穩 | 要給「最終答案」時 |
| 繼續拍攝 | 回到即時模式 | 看完診斷回掃描 | 每次定格後 |

---

# 第 3 部｜現場開機 SOP（比賽 / 展示用）

## 3.1 開機（一次約 3 分鐘）

```
1. 開 Jetson（插電 → 按電源），等 1~2 分鐘開完
2. 手機 WiFi 清單看到 AirCraft67Team = 熱點正常
3. 手機連 AirCraft67Team（密碼見 4.2）
4. 開瀏覽器（Chrome / Safari）→ 網址 https://10.42.0.1:8000
5. 瀏覽器警告「不安全」→ 點「進階 → 繼續前往」（憑證自己做的，正常）
6. 允許使用相機 → 看到畫面 + 綠框 = 完成！
```

> 重點：一定是 **https**（有 s），http 相機打不開。

## 3.2 手機畫面怎麼看

- 左上綠點 = 連線正常；紅燈 = 有問題。
- FPS：畫面每秒幾次的數字，有框有畫面就是正常，大小不重要。
- 偵測數：目前框出幾個損傷。
- 綠框 + 文字 = AI 認為這裡有損傷。文字是類型（例：Crack=裂痕）與信心百分比。

## 3.3 現場突然不能用（3 分鐘排除）

依序做，做完一項回頭試：
1. 手機重新整理網頁（下拉 / 右上角重新整理）。
2. 手機重連 WiFi（關→開→再連 AirCraft67Team）。
3. 檢查熱點在不在（WiFi 清單有沒有 AirCraft67Team）：
   - 有 → 有人 SSH 主機跑 `bash /tmp/opencode/start_webrtc.sh` 通常就回來。
   - 沒有 → 見 4.4「熱點救援」。
4. 重開主機（拔電重插），再走 3.1。

---

# 第 4 部｜帳密、網路、熱點（只給自己人）

## 4.1 Jetson 主機

- 使用者 `sixseven` / 密碼 `67`（sudo 同一個）
- 專案位置：`/home/sixseven/sixseven-project`
- 登入：`ssh sixseven@<主機IP>`

## 4.2 訓練用筆電（1050 Ti，負責「練 AI」）

- IP `192.168.0.111`，使用者 `alice` / 密碼 `1`
- 練模型用的 Python 環境：`~/ml`
- 最新權重輸出：`~/runs/train-bal-7cls/weights/best.pt`

## 4.3 現場熱點

- SSID `AirCraft67Team`；主機 IP `10.42.0.1`
- 網頁：`https://10.42.0.1:8000`
- 手機拿到 `10.42.0.x` 開頭的 IP 都算正常（DHCP 分配）

## 4.4 熱點救援（AirCraft67Team 消失時，給做得到的人）

```bash
# 在主機上重建熱點（注意把 <熱點密碼> 換成實際密碼）
sudo nmcli connection delete AirCraft67Team 2>/dev/null
sudo nmcli connection add type wifi ifname wlan0 con-name AirCraft67Team \
  ssid AirCraft67Team mode ap \
  802-11-wireless.band bg 802-11-wireless.channel 1 \
  802-11-wireless.powersave 2 \
  wifi-sec.key-mgmt wpa-psk wifi-sec.psk <熱點密碼> \
  ipv4.method shared ipv4.addresses 10.42.0.1/24
sudo nmcli connection up AirCraft67Team
```
做完後重開網頁服務，手機重連一次。

## 4.5 熱點「回到原本基地台」的小工具

主機有 `/reconnect-wifi` 按鈕（POST），能把 WiFi 從熱點切回一般基地台（現場除錯用）。會回覆最新 IP。

---

# 第 5 部｜程式是怎麼分工的（餐廳比喻）

| 元件 | 比喻 | 真實檔案 |
|---|---|---|
| 網頁（前端） | 服務生：收單、上菜 | `webUI_workspace/static/app.js` + `templates/index.html` |
| 主程式（後端） | 廚房總管：決定先做哪道、出菜 | `webUI_workspace/main.py` |
| 串流處理 | 外送員：接畫面、送畫面 | `webUI_workspace/webrtc_stream.py` |
| AI 模型 | 廚師：認出裂縫還是凹痕 | `webUI_workspace/models/yolo11s.pt` |
| 資料集 | 食譜：廚師是看幾萬張照片學的 | 筆電 `~/yolo_workspace_v4_bal` |
| 自動部署 | 送信兵：每 5 分檢查訓練完沒 | `tools/deploy_watcher.py` |

一秒鐘流程（重複好幾次 = 看起來即時）：

```
手機拍畫面 → 送到 Jetson → AI 認損傷 → 算出框位置 → 傳回手機 → 手機把框畫上
```

原理重點（DMA 式旁路）：手機**不**把每一幀轉成照片上傳重送，而是把「相機水管」直接接到主機；主機傳回的也只有「框的座標」，畫面留在手機自己顯示 → 快、清晰、辨位準。

---

# 第 6 部｜四大程式逐段解析（每一段在做什麼）

> 想改東西才需要看這部。只想操作的人可以跳過。

## 6.1 main.py — 總店長（最重要的主程式）

1. **開頭（main.py:1~41）** 載入工具（OpenCV 影像、FastAPI 網頁伺服器、PyTorch AI）。`CONFIG` 是設定表：模型路徑、信心門檻 0.25、用哪顆 GPU。main.py:8~15 讓新版 PyTorch 允許讀 AI 檢查點（不算浪費的安全手續）。
2. **翻譯表（main.py:43~53）** `CLASS_NAMES_ZH`：英文類別 → 中文。7 類：裂痕/凹痕/缺鉚釘/蒙皮受損/機身損傷/機翼損傷/引擎損傷。
3. **畫中文框（main.py:62~83）** `_draw_zh_boxes()`：OpenCV 不支援中文，借 PIL 來畫。每個框 = 綠框 + 綠底黑字標籤（例「裂痕 87%」）。
4. **模型管家 YOLOManager（main.py:85~276）** 系統心臟：
   - `load_models()`：開機載模型；有 GPU 用 GPU，沒有退回 CPU。**重點（173~175）**：串流用 `model_n` 直接等於診斷用 `model_s` = 兩者都是同一顆最新 7 類模型。
   - `infer()`：吃進一張圖 → 叫 AI 算一次 → 回所有框（座標/信心/類別）。`use_large=True` 用較準的模型。結果存進共用區供前端取用。
5. **文字顧問 OllamaManager（main.py:279~359）**：偵測到嚴重損傷時，把類別整理成一句話問本地 AI「這是飛修專家：機翼檢查發現裂痕，給嚴重度與維修建議」。只會出現在定格診斷報告。
6. **網頁伺服基礎（main.py:366~447）**：起動載模型；一個中繼閘門禁止所有東西被快取（`no-store`，main.py:384）；首頁自動把 app.js 版號換成最後修改時間（main.py:392）；`/status` 回報健康度；`/stream` 是 MJPEG 備援串流。
7. **即時診斷核心（main.py:450~548）**：
   - `_web_infer_loop()`（465~510）：幕後迴圈。上游幀一到就推理（約每幀 21ms = 每秒約 45 幀），把框**歸一化**（座標除以寬高變成 0~1）後推給手機（491~504），手機不管多大都能對上。
   - `/webrtc/offer`（513~529）：手機按「即時診斷」→ 主機開一把連線、啟動迴圈。
   - `/webrtc/answer`（532~548）：手機回覆信號，正式連線。
8. **上傳與診斷 API（main.py:551~755）**：`/infer` 單張判斷；`/infer_hd` 定格診斷——**同一張跑 3 次合併**（592 行）；`/diagnose` 與 `/diagnose_upload` 走「嚴重的才叫文字顧問」邏輯（641 `MAJOR_CLASSES`，輕微類回傳固定提示）。
9. **入口（main.py:758~781）**：`python main.py --ssl`。`--ssl` = 開 HTTPS（手機相機必備），`--port 8000` = 網頁掛 8000 號埠。

## 6.2 webrtc_stream.py — 水管工（串流模組）

1. **共用區（webrtc_stream.py:19~54）** `_upstream_img`（手機最新一幀）、`_upstream_seq`（幀編號）、`init()`（設定下游畫面來源）、`get_upstream_frame_newest()`（主程式拿幀推理）、`push_detections()`（把框資料廣播給手機）。
2. **下游：推「框好畫面」給手機（56~95）** `AnnotatedFrameTrack.recv()`：每秒約 28 幀節奏；沒圖就黑畫面；解析度小會放大到 1280 寬（畫質提升）。**90 行** `img[:, :, ::-1]` 是 RGB↔BGR 顏色翻轉（OpenCV 慣用 BGR），並確保記憶體連續才好編碼。設好時間戳（pts/time_base），否則瀏覽器解碼全黑。
3. **上游：接手機畫面（98~116）** `_consume_upstream()`：幀轉 ndarray → RGB 翻 BGR → 存共用區 → 序號 +1。**就是這裡不要亂加東西**（見 1.2 防呆）。
4. **建立連線（129~201）** `create_offer()`：建 `RTCPeerConnection`、加下游軌道、建 data channel「detections」（送座標）、登錄斷線清理。等 ICE 收集完回傳 offer。`set_answer()` 收手機回覆。所有 peer 關閉時 `_notify_peer_closed()` 通知主程式停推理釋放 GPU。

## 6.3 app.js — 手機前台（前端邏輯）

1. **開機（app.js:1~73）** 網頁載入 → 建 `WingDetectionApp` → `init()` 顯示就緒並自動開相機。
2. **相機管理（88~145）** `openCamera()` 要權限並用後鏡頭（`facingMode:'environment'`）。`showLocalCamera / showRemoteStream` 切換顯示。連線後 `boostUpstream()` 把送出解析度提高成 1920x1440（真 HD）。
3. **即時診斷開關（149~266）** `toggleLive / startStreaming`：把手機相機 track 加進連線（上游）；監聽 `ontrack`（主機推圖）顯示在 remoteVideo；`ondatachannel`（193~...）收到框資料交給 `handleDetections` 畫框。走信令 `/webrtc/offer` → `/webrtc/answer`。
4. **疊框對位（275~326）** 這是「框準」的秘訣：
   - `_activeVideo()`：畫框的對象**恆為本地相機**（手機畫面是原始高畫質，不經壓縮）。
   - `_coverRect()`：依手機畫面尺寸與容器尺寸，算出 `cover` 縮放的座標（`scale = max(寬比, 高比)`、中央對齊）。不管直拍橫拍都對得上。
   - `drawDetections()`：清畫布新畫；把歸一化座標乘回螢幕尺寸；畫 3px 綠框 + 標籤。
5. **資訊顯示（328~362）** `monitorStats()` 每秒抓 FPS，低於 12 顯示警告；`boostUpstream()` 提高上游解析度。
6. **定格診斷（374~463）** `startDiagnosis()`：凍結畫面 → 背景送 `/infer_hd`（主機跑 3 次）→ 顯示框好圖 + 報告。`resumeLive()` 診斷完回原模式。

## 6.4 index.html — 手機牆面（結構）

- 定義畫面上所有元素：兩個 `<video>`（`#camera` 本機相機、`#remote` 主機推圖）、`<img id="stream">`（定格/上傳圖）、`<canvas id="overlay">`（疊 AI 框的透明畫布）、兩個按鈕（即時/診斷）、資訊面板（FPS/模式/偵測數）、診斷報告區。
- `<div id="webrtc-debug">`：**點標題 7 下**打開隱藏除錯區（排錯用，app.js:52）。
- 最後 `<script src="/static/app.js?v=15">` 載入前端程式。

## 6.5 tools/deploy_watcher.py — 自動送信兵

獨立於網頁系統，由 cron **每 5 分鐘**自動跑：
1. 連訓練筆電（192.168.0.111）。
2. 看訓練程式（`train_bal(_fast).py`）還在跑嗎？
   - 在跑 → 印「訓練中」結束。
3. 訓練結束 → 拿筆電 `best.pt`（最佳模型）的資訊。
4. 跟主機現役 `yolo11s.pt` 比大小：
   - 一樣 → 寫 lock 檔，結束（lock 存在 = 已部署，防止重複動作）。
   - 不同 → 下載覆蓋 → 重啟服務 → 寫 lock。
5. 重點：**lock 檔 `/tmp/opencode/deployed.lock`** 存在代表「部署已完成」，之後每 5 分都不會再亂動。

> 歷史教訓：曾有版本誤用 `c.stat()`（paramiko 根本沒有這方法），導致一整天的檢查都誤判「模型不存在」而沒部署。**2026-09-08 已改用正確的 `sftp.stat()`**。若再遇到 watcher 一直印失敗，先看 log `/tmp/opencode/deploy_watcher.log`。

## 6.6 tools/train_monitor.py — 進度記者

每 15 分鐘記錄訓練進度到 `/tmp/opencode/train_monitor.log`（epoch、mAP、權重時間、RUNNING/DONE）。純記錄用，壞了也不影響主系統。

---

# 第 7 部｜讓模型變強（資料 + 訓練 + 自動部署）

## 7.1 先懂「訓練」是什麼

AI 不是發明的，是「餵照片學」的：給它幾萬張「這張是裂縫」「這張是凹痕」的標註照片，它自己找規律。**餵得越多、越平均，它越會認。**

目前系統的小弱點：7 類中 `Skin_Cover`（蒙皮）/`Wing_damage`（機翼）/`Engine_damage`（引擎）/`Fuselage_damage`（機身）照片特別少，學不夠 → 偶爾漏判。**多拍這幾類的照片 = 直接讓系統變強。**

## 7.2 想加照片（任何人做得到）

1. 用同一支手機開「即時診斷」，對準損傷，按「開始診斷」存下的那張就能用。
2. 重點：**多拍最少的那幾類**（蒙皮/機翼/引擎/機身）。每類至少幾十張、上百張更好。
3. 交給會寫程式的人標記（免費 labelImg / CVAT 畫框）。
4. 標好後放訓練資料夾 → 重訓 → 自動部署 → 完成。
5. 口訣：**照片品質 > 數量**；損傷清楚、背景乾淨、盡量一張一種損傷。

## 7.3 讓會寫程式的人重訓（速記）

筆電環境：
- venv：`~/ml/bin/python`（有 torch + cv2 5.0.0）
- 平衡資料集：`~/yolo_workspace_v4_bal`（train 17,123 圖 / valid 801；小類補到 2,500 張邊線翻轉）
- 訓練腳本：`~/train_bal_fast.py`（imgsz=512, batch=16, epochs=120, patience=30）
- 產出：`~/runs/train-bal-7cls/weights/{best,last}.pt` + `results.csv`

重訓後只要你**什麼都不做**，Jetson 的 watcher 每 5 分鐘就會自動把新的 `best.pt` 部署上去並重啟。（如果訓練中斷或想立刻換，也可以用 1.4 手動。）

## 7.4 目前模型成績（截至 2026-09-08）

| 項目 | 數值 |
|---|---|
| 訓練資料集 | `yolo_workspace_v4_bal`（已平衡 7 類） |
| 模型 | yolo11s（`models/yolo11s.pt`，19.1MB 正式版） |
| 訓練結果 | 31 輪早停；mAP@0.5 ≈ **0.58**、Recall ≈ 0.74（與舊版持平） |
| 限制 | 小類驗證樣本少（各 8~9 張），per-class 數值有雜訊 |

如果之後還是不夠準：下一招是「用隊友的 5080 重練」或「補小類照片」。

---

# 第 8 部｜目前狀態與已知問題（交接時請更新）

## 已完成

- 7 類資料集定案與平衡（`v3` → `v4_bal`）。
- 7 類模型完成重訓並**已自動部署**（2026-09-08，19.1MB 正式版生效，服務運行中）。
- 即時疊框偏移 bug 修復（webrtc 上游不再亂轉置；使用者確認位置正確）。
- 前端 no-store 快取 + 動態版號（現場不會拿到舊頁面）。
- 內網 HTTPS（`--ssl` + gen_cert.sh 動態憑證）+ Jetson 自建熱點備援（setup_ap.sh）。
- 自動部署 watcher 修正並驗證（`deploy_watcher.py`，cron 每 5 分）。
- Ollama 診斷 timeout 修復（60→300 秒），輕微損傷不叫文字顧問直接回應。

## 已知限制（讀到這本時請確認是否已解決並更新）

- [ ] 小類（Skin_Cover/Wing/Engine）樣本偏少，偶爾漏判。
- [ ] 筆電 matplotlib 環境曾壞（會中斷訓練完的繪圖，不影響權重存檔）——重訓前先修。
- [ ] 串流 yolo11n 實際是 yolo11s 大模型（較慢）；要更快需另訓真 yolo11n。
- [ ] Ollama 吃 GPU/系統記憶體，若同時開 GPU 推理要留意。
- [ ] `SPECIAL_TOPIC_REPORT.md` §7.2 新版數據仍是「待填入」，接手者要用 `results.csv` 補齊。

---

# 第 9 部｜詞彙表（看不懂就來翻）

| 詞 | 白話解釋 |
|---|---|
| AI 模型 / YOLO | 被大量照片訓練過的程式，能在圖裡找出物件框。yolo11s 較準。 |
| 權重檔（.pt） | AI 訓練完的「記憶檔」，存著所有學到的判斷。 |
| 推理 / infer | AI 拿一張圖「算一次」找損傷的動作。 |
| 偵測框（bbox） | AI 找到損傷位置回傳的矩形座標 [x1,y1,x2,y2]。 |
| 信心值 | AI 相信自己找到的程度（0~1），0.87 = 87%。 |
| 歸一化座標 | 座標除以畫面寬高變成 0~1，手機顯示時乘回螢幕尺寸，不怕解析度不同。 |
| FPS | 每秒幾張畫面，越高越順；低於 12 會警告。 |
| WebRTC / PeerConnection | 網頁即時影音技術，手機與主機直連水管。 |
| DataChannel | WebRTC 裡傳「文字資料」（我們傳框座標）的通道。 |
| 上游 / 下游 | 上游 = 手機→主機；下游 = 主機→手機。 |
| 後端 / 前端 | 後端 = 主機程式；前端 = 手機瀏覽器程式。 |
| HTTPS / SSL | 加密傳輸；手機開相機時瀏覽器要求安全來源，所以要用。 |
| API | 程式與程式約定的「服務窗口」。 |
| GPU | 顯示卡；AI 計算靠它加速（遠快於 CPU）。 |
| cron / 排程器 | 定時自動跑程式的工具（如每 5 分鐘跑 watcher）。 |
| Lock 檔 | 「記號」檔，存在代表某動作已完成，防止重複執行。 |
| DMA 旁路 | 不層層拷貝直接把來源資料送往目的地的手法 → 畫面更順。 |
| MJPEG | 連續 JPEG 組成的影片串流，另一種較慢的視訊方式。 |
| Ollama / LLM | 本機執行的文字型 AI，負責生成維修建議報告。 |

---

# 附錄 A｜檔案地圖

```
sixseven-project/
├── docs/                       # 所有文件（本手冊、報告、資料盤點、舊交接）
├── tools/                      # 工具
│   ├── deploy_watcher.py       # 自動部署送信兵（cron 每 5 分）
│   ├── train_monitor.py        # 進度記者（cron 每 15 分）
│   └── scripts_*.py            # 資料集重建/清理 v3 用
├── pretrained/                 # 原始預訓練模型（yolo11n/s/26n .pt）
├── webUI_workspace/            # 網頁應用（主系統）
│   ├── main.py                 # 總店長（FastAPI 後端，port 8000）
│   ├── webrtc_stream.py        # 水管工（WebRTC 串流）
│   ├── templates/index.html    # 手機牆面
│   ├── static/app.js           # 手機前台邏輯
│   ├── static/style.css        # 手機樣式
│   ├── models/                 # yolo11s.pt（現役 7 類）、備份 .bak
│   ├── certs/                  # HTTPS 自簽憑證（10 年效期，開機直接用）
│   └── start.sh / start_https.sh / gen_cert.sh / setup_ap.sh
├── yolo_workspace_v4_bal/      # 現役訓練資料（train 17,123 / valid 801，已拉回本機）
└── yolo_workspace{,_v2,_v3}/   # 資料集舊版（保留供歷史）
```

# 附錄 B｜資料集與類別

- 現役訓練資料：`yolo_workspace_v4_bal`（**本機** `/home/sixseven/sixseven-project/yolo_workspace_v4_bal` 與筆電 `~/yolo_workspace_v4_bal` 同步，train 17,123 / valid 801）。
- 類別順序（與 data.yaml 一致，索引 0~6）：
  `Crack(0) / Dent(1) / Missing_Fastener(2) / Skin_Cover(3) / Fuselage_damage(4) / Wing_damage(5) / Engine_damage(6)`
- 原始來源：5 個 Roboflow zip（Aircraft Damage Detection v5 / Aircraft Damage v2 / Aircraft Defects v2 / ac_damage_detector v4 / ac_damage_detector v5）。模糊類別決策已文件化在舊 `DATASET_INVENTORY.md`。

# 附錄 C｜回滾與備份

- 現役模型備份：`models/yolo11s.pt.bak_20260907`（舊版 56.9MB）。要回滾直接 `cp` 回 `yolo11s.pt` 再重啟服務。
- 過往權重：`runs/detect/train-31/`、`runs/detect/runs/detect/train-32/`（Jetson）；筆電 `~/runs/train-bal-7cls/weights/`。
- 資料集數版都保留：`yolo_workspace/`（舊）、`yolo_workspace_v2/`、`yolo_workspace_v3/`（乾淨 7 類）、`yolo_workspace_v4/`、`yolo_workspace_v4_bal/`（現役平衡版）。
- 規則：任何新的合併/清理類別需求，一律用 `tools/scripts_*.py` 重跑，不要再碰舊 `merge_labels.py`。

---

> 一句話總結：**開機 → 手機連 AirCraft67Team → Chrome 開 https://10.42.0.1:8000 → 允許相機 → 看到綠框就是成功。**
> 連不上就重開網頁服務（`sudo systemctl restart sixseven-webrtc`，或舊法 `bash /tmp/opencode/start_webrtc.sh`）或重開機。
> 想變準，多拍那幾種「少見」的損傷照片。
> 想改東西，照《第 1 部》的速查表找到檔案，改完重啟服務。

*交接人：Sixseven 專題小組 · 2026-09-08 彙整*