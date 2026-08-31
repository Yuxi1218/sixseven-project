# Sixseven 機翼損傷檢測系統 - 使用說明

## 系統架構

```
webUI_workspace/
├── main.py              # FastAPI 後端
├── start.sh            # 啟動腳本
├── templates/
│   └── index.html     # Web 介面 (PWA 相容)
├── static/
│   ├── app.js       # 前端邏輯
│   ├── style.css    # 樣式
│   └── manifest.json # PWA 清單
└── models/
    └── yolo11s.pt  # 診斷模型
```

## 啟動步驟

### 1. 啟動服務

```bash
cd ~/sixseven-project/webUI_workspace/
python main.py
```

### 2. 訪問系統

- **手機瀏覽器**: http://<Jetson_IP>:8000
- **添加到主螢幕**: Safari > 分享 > 加入主畫面

## 功能說明

| 功能 | 說明 |
|------|------|
| 監視模式 | 即時 YOLO 偵測 |
| 診斷模式 | 點擊診斷使用 YOLO + Ollama |
| 上傳照片 | 上傳圖片進行診斷 |
| 損傷評估 | AI 提供維修建議 |

## API 端點

- `GET /status` - 系統狀態
- `POST /infer` - 圖像推理
- `POST /diagnose` - 完整診斷
- `POST /diagnose_upload` - 上傳診斷

## 常見問題

1. **模型未載入**: 會以演示模式運行
2. **Ollama 未連線**: 會顯示離線訊息
3. **相機無法使用**: 使用「上傳照片」功能