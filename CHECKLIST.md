# Code Review 自撿表 / Checklist

> 專案：sixseven-project（飛機缺陷偵測 + 網頁 UI）
> 目的：交付前最後自撿，確認已完成修復、標記剩餘風險。

## ✅ 已完成修復（低級錯誤）

| 項目 | 檔案 | 說明 |
|------|------|------|
| 移除死碼 | `webUI_workspace/main.py` | 移除已失效的 `patch_ultralytics()` 與無用相容碼 |
| 路徑改相對根 | `webUI_workspace/main.py` | 改以 `BASE_DIR` 組出 models/static/templates 絕對路徑，不再依賴 CWD |
| Ollama 模型 | `webUI_workspace/main.py` | `gemma3:270m`（不存在 tag）→ `gemma3:1b`（最小可用） |
| 串流架構 | `webUI_workspace/main.py` | 加入 `_update_fps()` 全路徑更新、`get_annotated_frame()`；`/infer`、`/diagnose`、`/diagnose_upload` 重構並共用 `_decode_image`/`_encode_jpeg` |
| 前端串流 | `webUI_workspace/static/app.js` | 重寫為真實串流：每 250ms 送 camera 幀、繪製 annotated、更新 FPS/偵測數/狀態、綁定 close、上傳/診斷渲染標註圖 |
| 移除未用 CDN | `webUI_workspace/templates/index.html` | 移除未使用 socket.io script、修正 icon 引用、保留 title |
| 依賴 | `webUI_workspace/requirements.txt` | 補 `requests>=2.31.0` |
| Icon | `webUI_workspace/static/icon-{192,512}.png` | 產生占位 icon |
| 孤立標籤 | `yolo_workspace/{train,valid}/labels_orphan/` | 舊工作區 train 145、valid 43 個孤立標籤隔離；現 train/valid 均 1:1（14277/14277、1333/1333） |
| 資料集重建 | `yolo_workspace_v3/` | 以 5 個原始 zip 乾淨重建、非覆寫舊工作區；polygon→bbox、7 類定案 |

## 🔴 已證實的舊 bug（被 v3 取代，勿再使用）

`/home/sixseven/sixseven-project/yolo_workspace/merge_labels.py`：
- `damage_v2 {0:1, 2:2}`：會丟失 dent(class1)
- `v4 {0:2}`：會丟失 class 0
- `v5`：丟棄 11 類中 8 類
- 影響：先前 `yolo_workspace{,.v2}` 的合併標籤可能不完整／混類。
- **對策**：一律改用 `yolo_workspace_v3/`（由 v3 scripts 重建）。

## 📋 驗證已通過

- v3 各 split：train=8265、valid=801、test=311，image/label 1:1。
- 0 bad、0 out-of-range、0 non-positive w/h（FixingLabelBoxes 檢查）。
- Ultralytics `YOLO('yolo11n.pt').val(...)` 可直接讀取 v3：valid 801 張、0 corrupt、0 background。
- 視覺預覽（`/tmp/opencode/v3_preview/`）由使用者確認標框類別正確。
- 診斷 Ollama timeout 修復：`timeout 60→300`、`num_predict 150→130`（原本實測生成需 84~127s，60s 一定 timeout；修復後 `success: True` 並產出結構化報告）。
- 診斷 LLM 介入 gate：僅重大類別（Fuselage/Wing/Engine/damage）才呼叫 Ollama；輕微類別立即回應不等待（`_should_invoke_llm()` 單測 8 案例全數通過）。

## ⚠️ 剩餘風險 / 待辦

- [x] **v3 重新訓練完成**：train-32（yolo11s, 30 epochs, 7 類）best.pt 存在於 `runs/detect/runs/detect/train-32/weights/best.pt`（注意巢狀路徑）。
- [x] **WebUI 模型已更新**：`yolo11n/s.pt` 皆換成 train-32 7 類 best.pt；舊 4 類已備份為 `yolo11n.pt.20260831_165856.bak`、`yolo11s.pt.20260831_165856.bak`。
- [x] model 載入驗證：Jetson 上 `yolo11n.pt` 正確載入 7 類 names（nc=7），val mAP@0.5≈**0.261**。
- [x] **laptop yolov8n 串流模型判定損壞**：`yolov8n-v3/weights/best.pt` 在筆電 val 出 mAP@0.5≈2.5e-06（loss 發散到 nan）。**不部署、不回傳**；最終維持 train-32 yolo11s 作為部署模型。若需輕量串流模型需重訓（`amp=False`）。
- [x] **GitHub 同步**：已把 v3 資料集、runs 權重、WebUI、文件/scripts 補 push 到 `origin/main`；大 zip 與舊資料集（raw/v2/temp）以 `.gitignore` 排除。
- [x] **內網 HTTPS 完成**：`main.py --ssl` + `gen_cert.sh`（動態重生憑證、手機熱點 IP 變動自動處理）+ `start_https.sh`；備援 `setup_ap.sh`（Jetson 自建熱點）。已用 `192.168.0.208:8000` 實測：`/status` 正常、`/infer` 偵測到 `Fuselage_damage`（7 類正確）、`/diagnose_upload` minor 分支立即回應。
- [ ] 端到端手機測試：實際用手機連熱點 → 瀏覽器點「進階→繼續前往」信任憑證 → 用相機串流偵測（需現場確認，因依賴手機熱點環境）。
- [ ] train-32 最終 mAP@0.5≈**0.261**（7 類、類別不平衡），比 v2 的 0.457 低（預期），建議後續改善。
- [ ] 類別不平衡：Skin_Cover(136)、Wing(201)、Engine(136) 明顯少於 Crack(11623)/Dent(9235)/Missing(7192)，可能影響少數類召回，後續可考慮 oversample。
- [ ] 環境 bug：matplotlib 版本衝突導致 ultralytics 結束繪圖中斷（不影響模型存檔），重訓前需修。
- [ ] WebUI device 預設 `cpu`；在 Jetson 上因沒設 `CUDA_VISIBLE_DEVICES`，Ollama 會吃掉部分記憶體，若同時開 GPU 推理需留意。
- [ ] 串流 `yolo11n.pt` 現為 yolo11s 架構（較慢），若要真輕量串流模型需另訓。
- [ ] 測試端到端：啟動 WebUI、接 camera、上傳診斷（需 Ollama 服務運行於 localhost:11434）。

## ✅ Phase 0 自撿（已確認）

- [x] `main.py` 可 compile（語法無誤）
- [x] 孤兒標籤清除後 train/valid 1:1
- [x] raw zip 屬重新解壓（非沿用舊目錄）
- [x] v3 用新工作區、未覆蓋 `yolo_workspace` / `yolo_workspace_v2`
- [x] 模糊類別已文件化（v4 damages→Fuselage_damage、v2 stucturaldamage→Fuselage_damage）
