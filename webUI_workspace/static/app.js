document.addEventListener('DOMContentLoaded', function () {
    var app = new WingDetectionApp();
    app.init();
});

class WingDetectionApp {
    constructor() {
        this.video = document.getElementById('camera');
        this.overlay = document.getElementById('overlay');
        this.ctx = this.overlay ? this.overlay.getContext('2d') : null;

        // 串流解析度（輸出給後端偵測用，可隨網速自動降級）
        this.videoWidth = 640;
        this.videoHeight = 480;

        this.streamTimer = null;
        this.streaming = false;
        this.requestInFlight = false;   // 上一幀未回即不送下一幀（避免積幀延遲）
        this.streamInterval = 250;      // 起手 250ms

        // 用於自適應幀率的平滑平均
        this.roundTripSamples = [];
        this.maxInterval = 1000;        // 最慢 1 秒一幀
        this.minInterval = 100;         // 最快 100ms 一幀

        // 重用物件，避免每幀 new（降低 GC / 記憶體抖動）
        this.sendCanvas = document.createElement('canvas');
        this.sendCtx = this.sendCanvas.getContext('2d');
        this.displayImg = new Image();

        // 統計
        this.displayFpsLast = 0;

        this.btnCamera = document.getElementById('btn-camera');
        this.btnDiagnose = document.getElementById('btn-diagnose');
        this.btnUpload = document.getElementById('btn-upload');
        this.btnClose = document.getElementById('btn-close-diagnosis');
        this.fileUpload = document.getElementById('file-upload');
        this.statusIndicator = document.getElementById('status-indicator');
        this.statusText = document.getElementById('status-text');
        this.modeDisplay = document.getElementById('mode-display');
        this.fpsDisplay = document.getElementById('fps-display');
        this.detectionCount = document.getElementById('detection-count');
        this.diagnosisPanel = document.getElementById('diagnosis-result');
        this.diagnosisContent = document.getElementById('diagnosis-content');

        this.bindEvents();
    }

    bindEvents() {
        if (this.btnCamera) {
            this.btnCamera.addEventListener('click', () => {
                if (this.streaming) this.disconnectCamera();
                else this.connectCamera();
            });
        }
        if (this.btnDiagnose) {
            this.btnDiagnose.addEventListener('click', () => this.requestDiagnosis());
        }
        if (this.btnUpload) {
            this.btnUpload.addEventListener('click', () => {
                if (this.fileUpload) this.fileUpload.click();
            });
        }
        if (this.btnClose) {
            this.btnClose.addEventListener('click', () => {
                if (this.diagnosisPanel) this.diagnosisPanel.style.display = 'none';
            });
        }
        if (this.fileUpload) {
            this.fileUpload.addEventListener('change', (e) => this.handleFileUpload(e));
        }
    }

    init() {
        this.updateStatus('就緒');
    }

    updateStatus(text) {
        if (this.statusText) this.statusText.textContent = text;
    }

    setOnlineStatus(online) {
        this.streaming = online;
        if (this.statusIndicator) {
            this.statusIndicator.className = 'status ' + (online ? 'online' : 'offline');
        }
        if (this.btnCamera) {
            this.btnCamera.textContent = online ? '中斷連線' : '連線相機';
            this.btnCamera.className = 'btn ' + (online ? 'danger' : 'primary');
        }
        if (this.btnDiagnose) this.btnDiagnose.disabled = !online;

        if (!online) {
            this.stopStreamLoop();
            this.requestInFlight = false;
            this.roundTripSamples = [];
            this.clearOverlay();
            if (this.fpsDisplay) this.fpsDisplay.textContent = '0';
            if (this.detectionCount) this.detectionCount.textContent = '0';
        }
        this.updateStatus(online ? '已連線' : '已離線');
    }

    async connectCamera() {
        if (!this.video) { alert('找不到影片元素'); return; }
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            alert('需要 HTTPS 才能使用相機'); return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } },
                audio: false
            });
            this.video.srcObject = stream;
            await this.video.play();
            this.setOnlineStatus(true);
            this.startStreamLoop();
        } catch (error) {
            alert('無法開啟相機: ' + error.message);
        }
    }

    disconnectCamera() {
        if (this.video && this.video.srcObject) {
            const tracks = this.video.srcObject.getTracks();
            tracks.forEach((t) => t.stop());
            this.video.srcObject = null;
        }
        this.setOnlineStatus(false);
    }

    startStreamLoop() {
        this.stopStreamLoop();
        this.requestInFlight = false;
        this.roundTripSamples = [];
        this.tick();
    }

    stopStreamLoop() {
        if (this.streamTimer) {
            clearTimeout(this.streamTimer);
            this.streamTimer = null;
        }
    }

    /**
     * 自適應串流：每送完一幀並收到回應後，才排下一幀。
     * 優點：不積幀、不爆 queue；根據 round-trip 時間動態調整頻率。
     */
    tick() {
        if (!this.streaming || this.requestInFlight) return;
        this.sendFrame().finally(() => this.scheduleNext());
    }

    scheduleNext() {
        if (!this.streaming) return;
        // 依平滑 round-trip 決定下一幀延遲（稍微給餘裕，避免一直貼著極限）
        const avg = this.averageRt();
        let delay = this.streamInterval;
        if (avg > 0) delay = Math.min(Math.max(avg + 60, this.minInterval), this.maxInterval);
        this.streamTimer = setTimeout(() => this.tick(), delay);
    }

    averageRt() {
        if (this.roundTripSamples.length === 0) return 0;
        const sum = this.roundTripSamples.reduce((a, b) => a + b, 0);
        return sum / this.roundTripSamples.length;
    }

    async sendFrame() {
        if (!this.video || this.video.readyState < 2 || !this.streaming) return;
        this.requestInFlight = true;

        const start = performance.now();
        try {
            // 重用送件 canvas
            this.sendCanvas.width = this.videoWidth;
            this.sendCanvas.height = this.videoHeight;
            this.sendCtx.drawImage(this.video, 0, 0, this.videoWidth, this.videoHeight);
            const imageB64 = this.sendCanvas.toDataURL('image/jpeg', 0.7).split(',')[1];

            const resp = await fetch('/infer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image: imageB64 })
            });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const data = await resp.json();

            // 記錄 round-trip，供自適應
            this.roundTripSamples.push(performance.now() - start);
            if (this.roundTripSamples.length > 30) this.roundTripSamples.shift();

            if (this.fpsDisplay) this.fpsDisplay.textContent = data.fps || 0;
            if (this.detectionCount) {
                this.detectionCount.textContent = data.detections ? data.detections.length : 0;
            }
            if (data.image && this.ctx) {
                // 重用 Image 物件，僅更新 src
                this.displayImg.onload = () => {
                    if (!this.streaming) return;
                    this.overlay.width = this.displayImg.width;
                    this.overlay.height = this.displayImg.height;
                    this.ctx.drawImage(this.displayImg, 0, 0);
                };
                this.displayImg.src = 'data:image/jpeg;base64,' + data.image;
            }
        } catch (error) {
            // 暫態錯誤：略過本幀，稍微延後再試，避免連續快速失敗
            this.roundTripSamples.push(performance.now() - start);
            if (this.roundTripSamples.length > 30) this.roundTripSamples.shift();
        } finally {
            this.requestInFlight = false;
        }
    }

    clearOverlay() {
        if (this.ctx && this.overlay) {
            this.ctx.clearRect(0, 0, this.overlay.width, this.overlay.height);
        }
    }

    renderDiagnosis(data) {
        let content = '';
        const llmInvoked = data.llm_invoked !== false;
        content += '## 偵測到的損傷\n\n';
        if (data.detections && data.detections.length > 0) {
            for (const det of data.detections) {
                content += '- ' + det.class + ': ' + (det.confidence * 100).toFixed(1) + '%\n';
            }
        } else {
            content += '未偵測到缺陷\n';
        }
        content += llmInvoked ? '\n---\n\n## 維修建議 (LLM)\n\n' : '\n---\n\n## 狀態\n\n';
        content += data.diagnosis || '無建議';
        return content;
    }

    async requestDiagnosis() {
        if (!this.streaming) { alert('請先連線相機'); return; }

        if (this.diagnosisPanel) this.diagnosisPanel.style.display = 'block';
        if (this.diagnosisContent) this.diagnosisContent.textContent = '正在處理診斷...';
        if (this.modeDisplay) this.modeDisplay.textContent = '診斷中...';

        try {
            const resp = await fetch('/diagnose', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
            const data = await resp.json();
            if (data.success) {
                if (this.diagnosisContent) this.diagnosisContent.textContent = this.renderDiagnosis(data);
                if (data.annotated_image && this.ctx) {
                    const img = new Image();
                    img.onload = () => {
                        this.overlay.width = img.width;
                        this.overlay.height = img.height;
                        this.ctx.drawImage(img, 0, 0);
                    };
                    img.src = 'data:image/jpeg;base64,' + data.annotated_image;
                }
                if (this.modeDisplay) this.modeDisplay.textContent = '診斷完成';
            } else {
                if (this.diagnosisContent) this.diagnosisContent.textContent = '診斷失敗: ' + (data.message || '未知錯誤');
                if (this.modeDisplay) this.modeDisplay.textContent = '監視模式';
            }
        } catch (error) {
            if (this.diagnosisContent) this.diagnosisContent.textContent = '錯誤: ' + error.message;
            if (this.modeDisplay) this.modeDisplay.textContent = '監視模式';
        }
    }

    handleFileUpload(event) {
        const file = event.target.files ? event.target.files[0] : null;
        if (!file) return;

        if (this.diagnosisPanel) this.diagnosisPanel.style.display = 'block';
        if (this.diagnosisContent) this.diagnosisContent.textContent = '正在處理...';

        const reader = new FileReader();
        reader.onload = async (e) => {
            const base64 = e.target.result.split(',')[1];
            if (!base64) {
                if (this.diagnosisContent) this.diagnosisContent.textContent = '讀取圖片失敗';
                return;
            }
            try {
                const resp = await fetch('/diagnose_upload', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ image: base64 }) });
                const data = await resp.json();
                if (data.success) {
                    if (this.diagnosisContent) this.diagnosisContent.textContent = this.renderDiagnosis(data);
                    if (data.annotated_image && this.ctx) {
                        const img = new Image();
                        img.onload = () => {
                            this.overlay.width = img.width;
                            this.overlay.height = img.height;
                            this.ctx.drawImage(img, 0, 0);
                        };
                        img.src = 'data:image/jpeg;base64,' + data.annotated_image;
                    }
                } else {
                    if (this.diagnosisContent) this.diagnosisContent.textContent = '診斷失敗: ' + (data.message || '未知錯誤');
                }
            } catch (error) {
                if (this.diagnosisContent) this.diagnosisContent.textContent = '錯誤: ' + error.message;
            }
        };
        reader.readAsDataURL(file);
    }
}