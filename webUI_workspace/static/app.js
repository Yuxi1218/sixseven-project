document.addEventListener('DOMContentLoaded', function () {
    var app = new WingDetectionApp();
    app.init();
});

class WingDetectionApp {
    constructor() {
        this.video = document.getElementById('camera');
        this.remoteVideo = document.getElementById('remote');
        this.streamImg = document.getElementById('stream');
        this.overlay = document.getElementById('overlay');
        this.ctx = this.overlay ? this.overlay.getContext('2d') : null;

        this.streamTimer = null;
        this.streaming = false;       // true = 即時診斷 ON（WebRTC 串流）
        this.requestInFlight = 0;
        this.pc = null;               // RTCPeerConnection

        this.btnLive = document.getElementById('btn-live');
        this.btnDiagnose = document.getElementById('btn-diagnose');
        this.btnClose = document.getElementById('btn-close-diagnosis');
        this.statusIndicator = document.getElementById('status-indicator');
        this.statusText = document.getElementById('status-text');
        this.modeDisplay = document.getElementById('mode-display');
        this.fpsDisplay = document.getElementById('fps-display');
        this.detectionCount = document.getElementById('detection-count');
        this.diagnosisPanel = document.getElementById('diagnosis-result');
        this.diagnosisContent = document.getElementById('diagnosis-content');
        this.fpsWarning = document.getElementById('fps-warning');

        this.cameraActive = false;    // 相機是否已開啟（不管哪種模式）

        this.bindEvents();
    }

    dbg(msg) {
        // 直接在裝置螢幕上顯示診斷（免 DevTools）
        const el = document.getElementById('webrtc-debug');
        if (el) el.textContent = (el.textContent ? el.textContent + '\n' : '') + msg;
    }

    bindEvents() {
        if (this.btnLive) {
            this.btnLive.addEventListener('click', () => this.toggleLive());
        }
        if (this.btnDiagnose) {
            this.btnDiagnose.addEventListener('click', () => this.startDiagnosis());
        }
        if (this.btnClose) {
            this.btnClose.addEventListener('click', () => this.resumeLive());
        }
        // 連續點擊標題 7 次切換顯示/隱藏 偵錯區
        const title = document.getElementById('title');
        if (title) {
            let clicks = 0, timer = null;
            title.addEventListener('click', () => {
                clicks++;
                clearTimeout(timer);
                timer = setTimeout(() => { clicks = 0; }, 1500);
                if (clicks >= 7) {
                    clicks = 0;
                    const el = document.getElementById('webrtc-debug');
                    if (el) el.style.display = (el.style.display === 'none') ? 'block' : 'none';
                }
            });
        }
    }

    init() {
        this.updateStatus('就緒');
        this.dbg('app v15 已載入（點標題7次開關偵錯）');
        this.openCamera();  // 自動開相機（預設 OFF 模式，顯示 raw video）
    }

    updateStatus(text) {
        if (this.statusText) this.statusText.textContent = text;
    }

    setOnlineStatus(online) {
        if (this.statusIndicator) {
            this.statusIndicator.className = 'status ' + (online ? 'online' : 'offline');
        }
        this.updateStatus(online ? '已連線' : '已離線');
    }

    // ---- 相機管理 ----

    async openCamera() {
        if (!this.video) return;
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            alert('需要 HTTPS 才能使用相機');
            return;
        }
        try {
            let stream;
            try {
                stream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1440 }, aspectRatio: { ideal: 4 / 3 } },
                    audio: false
                });
            } catch (e1) {
                stream = await navigator.mediaDevices.getUserMedia({
                    video: { width: { ideal: 1920 }, height: { ideal: 1440 }, aspectRatio: { ideal: 4 / 3 } },
                    audio: false
                });
            }
            this.video.srcObject = stream;
            await this.video.play();
            this.cameraActive = true;
            this.showLocalCamera();
            this.setOnlineStatus(false);
        } catch (error) {
            alert('無法開啟相機: ' + error.message);
        }
    }

    showLocalCamera() {
        if (this.video) this.video.style.display = '';
        if (this.remoteVideo) { this.remoteVideo.srcObject = null; this.remoteVideo.style.display = 'none'; }
        if (this.streamImg) { this.streamImg.src = ''; this.streamImg.style.display = 'none'; }
        if (this.overlay) this.overlay.style.display = 'none';
        if (this.btnLive) {
            this.btnLive.textContent = '啟用即時診斷';
            this.btnLive.className = 'btn primary';
        }
        if (this.btnDiagnose) this.btnDiagnose.disabled = false;
        if (this.modeDisplay) this.modeDisplay.textContent = '手機相機';
    }

    showRemoteStream() {
        // 做法A：顯示本地相機 raw 畫面 + 透明 canvas 疊偵測框
        if (this.video) this.video.style.display = 'block';
        if (this.streamImg) { this.streamImg.src = ''; this.streamImg.style.display = 'none'; }
        if (this.overlay) this.overlay.style.display = 'block';
        if (this.remoteVideo) { this.remoteVideo.srcObject = null; this.remoteVideo.style.display = 'none'; }
        this.dbg('camera size=' + (this.video ? (this.video.videoWidth + 'x' + this.video.videoHeight) : 'null') +
                 ' section=' + (this.overlay ? (this.overlay.clientWidth + 'x' + this.overlay.clientHeight) : 'null'));
        if (this.btnLive) {
            this.btnLive.textContent = '關閉即時診斷';
            this.btnLive.className = 'btn danger';
        }
        if (this.btnDiagnose) this.btnDiagnose.disabled = false;
        if (this.modeDisplay) this.modeDisplay.textContent = '即時診斷';
        this.setOnlineStatus(true);
    }

    // ---- 即時診斷 開/關（WebRTC DMA 式串流）----

    async toggleLive() {
        if (!this.cameraActive) return;
        if (this.streaming) {
            // 關閉即時診斷 → 停 WebRTC、顯示 raw camera
            await this.stopStreaming();
            this.streaming = false;
            this.showLocalCamera();
            if (this.fpsDisplay) this.fpsDisplay.textContent = '0';
            if (this.detectionCount) this.detectionCount.textContent = '0';
            if (this.fpsWarning) this.fpsWarning.style.display = 'none';
        } else {
            // 啟用即時診斷 → 建立 PeerConnection（上游相機 + 下游 annotated）
            this.streaming = true;
            this.streamImg && (this.streamImg.src = '');
            this.showRemoteStream();
            await this.startStreaming();
        }
    }

    async startStreaming() {
        try {
            if (this.pc && this.pc.connectionState === 'connected') {
                this.dbg('已連線，直接切顯示');
                return;
            }
            this.dbg('建立 PeerConnection...');
            const pc = new RTCPeerConnection({ iceServers: [] });
            this.pc = pc;

            // 上游：把手機相機 raw MediaStream 送給 Jetson（不經逐幀 encode）
            if (this.video.srcObject) {
                const tracks = this.video.srcObject.getTracks();
                this.dbg('上游加 ' + tracks.length + ' track(s)');
                tracks.forEach(t => pc.addTrack(t, this.video.srcObject));
            } else {
                this.dbg('警告: video.srcObject 為 null，無法上游');
            }

            // 下游：顯示 Jetson 推回的 annotated 串流
            pc.ontrack = (ev) => {
                this.dbg('ontrack 觸發: kind=' + (ev.track && ev.track.kind));
                if (this.remoteVideo) {
                    let stream = (ev.streams && ev.streams[0]) || new MediaStream([ev.track]);
                    this.remoteVideo.srcObject = stream;
                    this.remoteVideo.style.display = this.streaming ? 'block' : 'none';
                    // 用事件監看 srcObject 是否真的有畫格
                    const poll = setInterval(() => {
                        const rv = this.remoteVideo;
                        if (!rv) { clearInterval(poll); return; }
                        this.dbg('remoteVideo: readyState=' + rv.readyState +
                                  ' w=' + rv.videoWidth + ' h=' + rv.videoHeight +
                                  ' paused=' + rv.paused +
                                  ' muted=' + rv.muted);
                    }, 1500);
                    // 畫面有更新即清掉輪詢
                    this.remoteVideo.addEventListener('loadeddata', () => {
                        clearInterval(poll);
                        this.dbg('loadeddata 觸發，開始有畫面! size=' + this.remoteVideo.videoWidth + 'x' + this.remoteVideo.videoHeight);
                    });
                    this.remoteVideo.play().then(() => {
                        this.dbg('remoteVideo.play() resolved');
                    }).catch((e) => {
                        this.dbg('play() 失敗: ' + e.name + ' - ' + e.message);
                        const tryPlay = () => { this.remoteVideo.play(); };
                        document.addEventListener('touchstart', tryPlay, { once: true });
                    });
                }
            };

            pc.onconnectionstatechange = () => {
                this.dbg('連線狀態: ' + pc.connectionState);
                this.updateStatus('WebRTC: ' + pc.connectionState);
                if (pc.connectionState === 'connected') {
                    this.setOnlineStatus(true);
                    this.monitorStats();
                    this.boostUpstream(pc);
                }
            };

            // data channel：接收 Jetson 推理結果（歸一化框+標籤），疊在本地相機畫面上
            pc.ondatachannel = (ev) => {
                this.dbg('ondatachannel 觸發: ' + (ev.channel && ev.channel.label));
                const ch = ev.channel;
                ch.onmessage = (msg) => this.handleDetections(msg);
            };

            // 信令：fetch offer → answer
            const resp = await fetch('/webrtc/offer');
            if (!resp.ok) throw new Error('offer HTTP ' + resp.status);
            const data = await resp.json();
            this.dbg('取得 offer (ident=' + data.ident.slice(0,6) + '...)');
            await pc.setRemoteDescription({ type: 'offer', sdp: data.sdp });
            this.dbg('設入 remote offer OK');
            const answer = await pc.createAnswer();
            await pc.setLocalDescription(answer);
            // 等待手機端 ICE gathering 完成，確保 answer 含 host candidate（LAN 直連）
            if (pc.iceGatheringState !== 'complete') {
                this.dbg('等待手機 ICE gathering...');
                await new Promise((resolve) => {
                    const onDone = () => { pc.removeEventListener('icegatheringstatechange', onDone); resolve(); };
                    pc.addEventListener('icegatheringstatechange', onDone);
                    setTimeout(resolve, 2000); // 保險逾時
                });
            }
            this.dbg('送出 answer');
            const answerFinal = pc.localDescription || answer;
            const ar = await fetch('/webrtc/answer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ident: data.ident, sdp: answerFinal.sdp })
            });
            this.dbg('answer 回傳 status=' + ar.status);
        } catch (error) {
            console.error('[streaming]', error);
            this.updateStatus('串流連線失敗: ' + error.message);
            this.dbg('錯誤: ' + error.message);
        }
    }

    // 收到 Jetson 推理結果，疊框在本地相機畫面上
    handleDetections(msg) {
        let d;
        try { d = JSON.parse(msg.data); } catch (e) { return; }
        this.drawDetections(d.detections || []);
    }

    // live 時疊框對象恆為本地相機(√ 已由 showRemoteStream 設定只有 camera 顯示)
    _activeVideo() {
        if (this.video && this.video.videoWidth) return this.video;
        return null;
    }

    // 計算某 video 在容器內以 object-fit:cover 的完整縮放。
    // cover: scale = max(cw/vw, ch/vh)，內容縮放為 (vw*s, vh*s)，中央對齊。
    // box 可超出容器(canvas 自動 clip) → 視覺上等同 cover 的裁切效果。
    _coverRect() {
        const cv = this.overlay;
        const cw = cv.clientWidth, ch = cv.clientHeight;
        const v = this._activeVideo();
        const f = { ox: 0, oy: 0, dw: cw, dh: ch };
        if (!v) return f;
        const vw = v.videoWidth, vh = v.videoHeight;
        if (!vw || !vh) return f;
        const s = Math.max(cw / vw, ch / vh);
        const dw = vw * s, dh = vh * s;
        const ox = (cw - dw) / 2, oy = (ch - dh) / 2;
        return { ox, oy, dw, dh };
    }

    drawDetections(dets) {
        const cv = this.overlay;
        if (!cv) return;
        const cw = cv.clientWidth, ch = cv.clientHeight;
        if (!cw || !ch) return;
        if (cv.width !== cw || cv.height !== ch) { cv.width = cw; cv.height = ch; }
        const ctx = cv.getContext('2d');
        ctx.clearRect(0, 0, cw, ch);
        if (this.detectionCount) this.detectionCount.textContent = dets.length;
        const rect = this._coverRect();
        const v = this._activeVideo();
        this.dbg('SIZE: vb=' + (v ? v.videoWidth + 'x' + v.videoHeight : 'none') +
                 ' cv=' + cw + 'x' + ch +
                 ' rect=' + rect.ox.toFixed(0) + ',' + rect.oy.toFixed(0) +
                 ',' + rect.dw.toFixed(0) + ',' + rect.dh.toFixed(0) +
                 ' det=' + JSON.stringify(dets.map(d => d.bbox.slice(0, 4).map(n => n.toFixed(2)))).slice(0, 60));
        ctx.lineWidth = 3;
        ctx.font = '14px sans-serif';
        for (const d of dets) {
            const b = d.bbox;
            const x = rect.ox + b[0] * rect.dw, y = rect.oy + b[1] * rect.dh;
            const w = (b[2] - b[0]) * rect.dw, h = (b[3] - b[1]) * rect.dh;
            ctx.strokeStyle = '#00c800';
            ctx.strokeRect(x, y, w, h);
            ctx.fillStyle = 'rgba(0,200,0,0.85)';
            const label = d.class + ' ' + Math.round((d.confidence || 0) * 100) + '%';
            ctx.fillText(label, x, y > 18 ? y - 6 : y + 16);
        }
    }

    async monitorStats() {
        if (!this.pc || this.pc.connectionState !== 'connected') return;        try {
            const stats = await this.pc.getStats();
            let inboundFps = 0;
            stats.forEach((s) => {
                if (s.type === 'inbound-rtp' && s.kind === 'video' && s.framesPerSecond) {
                    inboundFps = s.framesPerSecond;
                }
            });
            if (this.fpsDisplay && inboundFps > 0) this.fpsDisplay.textContent = inboundFps;
            if (this.fpsWarning) this.fpsWarning.style.display = inboundFps > 0 && inboundFps < 12 ? 'block' : 'none';
        } catch (e) { /* ignore */ }
        setTimeout(() => this.monitorStats(), 1000);
    }

    // 提高手機上游送出的解析度（真 HD 而非放大）
    boostUpstream(pc) {
        setTimeout(async () => {
            try {
                const sender = pc.getSenders().find(s => s.track && s.track.kind === 'video');
                if (!sender) { this.dbg('boost: 找不到 video sender'); return; }
                const params = await sender.getParameters();
                if (!params.encodings || params.encodings.length === 0) {
                    params.encodings = [{}];
                }
                params.encodings[0].maxWidth = 1920;
                params.encodings[0].maxHeight = 1440;
                params.encodings[0].maxFramerate = (params.encodings[0].maxFramerate || 30);
                await sender.setParameters(params);
                this.dbg('boost: 已設上游 send → max 1920x1440@30');
            } catch (e) {
                this.dbg('boost 失敗: ' + e.message);
            }
        }, 800);
    }

    async stopStreaming() {
        if (this.pc) {
            try { await this.pc.close(); } catch (e) { /* ignore */ }
            this.pc = null;
        }
        this.requestInFlight = 0;
    }

    // ---- 開始診斷（定格 1080p + 中文框）----

    async startDiagnosis() {
        if (!this.cameraActive) { alert('請先開啟相機'); return; }

        this.wasStreaming = this.streaming;
        this.requestInFlight = 0;

        // 診斷中：按鈕不可按
        if (this.btnDiagnose) this.btnDiagnose.disabled = true;
        if (this.btnLive) this.btnLive.disabled = true;

        // 1. 立即定格：先確保 video 最新幀已繪製再抓取
        //    ON 模式 video 是 hidden，先強制繪製一幀確保拿到目前畫面
        if (this.video.readyState < 2) {
            await new Promise((res) => {
                this.video.onloadeddata = res;
                setTimeout(res, 400);
            });
        }
        // 暫時顯示 video、等待一幀渲染，確保 drawImage 抓到最新畫面
        const prevVDisp = this.video.style.display;
        const prevImgDisp = this.streamImg ? this.streamImg.style.display : '';
        this.video.style.display = '';
        this.streamImg && (this.streamImg.style.display = 'none');
        await new Promise((res) => requestAnimationFrame(() => requestAnimationFrame(res)));
        const hiCanvas = document.createElement('canvas');
        hiCanvas.width = this.video.videoWidth;
        hiCanvas.height = this.video.videoHeight;
        hiCanvas.getContext('2d').drawImage(this.video, 0, 0);
        const frozenUrl = hiCanvas.toDataURL('image/jpeg', 0.92);
        // 恢復原顯示狀態
        this.video.style.display = prevVDisp;
        this.streamImg && (this.streamImg.style.display = prevImgDisp);

        // 切換顯示：hide video/remote → show frozen frame
        if (this.video) this.video.style.display = 'none';
        if (this.remoteVideo) this.remoteVideo.style.display = 'none';
        if (this.streamImg) {
            this.streamImg.style.display = '';
            this.streamImg.src = frozenUrl;
        }
        if (this.overlay) this.overlay.style.display = 'none';

        // 2. 顯示診斷狀態
        if (this.diagnosisPanel) this.diagnosisPanel.style.display = 'block';
        if (this.diagnosisContent) this.diagnosisContent.textContent = '診斷中...';
        if (this.modeDisplay) this.modeDisplay.textContent = '診斷中...';

        // 3. 背景送 /infer_hd
        try {
            const hiB64 = frozenUrl.split(',')[1];
            const resp = await fetch('/infer_hd', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image: hiB64 })
            });
            const data = await resp.json();

            // 4. 診斷完成
            if (data.success) {
                if (this.streamImg) this.streamImg.src = 'data:image/jpeg;base64,' + data.annotated_image;
                if (this.diagnosisContent) this.diagnosisContent.textContent = this.renderDiagnosis(data);
                if (this.modeDisplay) this.modeDisplay.textContent = '定格診斷完成';
            } else {
                if (this.diagnosisContent) this.diagnosisContent.textContent = '診斷失敗: ' + (data.message || '未知錯誤');
            }
        } catch (error) {
            if (this.diagnosisContent) this.diagnosisContent.textContent = '錯誤: ' + error.message;
        } finally {
            if (this.btnDiagnose) this.btnDiagnose.disabled = false;
            if (this.btnLive) this.btnLive.disabled = false;
            // 5. 自動往下捲到診斷報告
            if (this.diagnosisPanel && this.diagnosisPanel.scrollIntoView) {
                this.diagnosisPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }
    }

    resumeLive() {
        if (this.diagnosisPanel) this.diagnosisPanel.style.display = 'none';
        if (this.overlay && this.ctx) this.ctx.clearRect(0, 0, this.overlay.width, this.overlay.height);
        if (this.wasStreaming) {
            // 診斷前是即時診斷（WebRTC）模式 → 恢復 remote annotated 串流
            this.streaming = true;
            this.showRemoteStream();
            if (this.modeDisplay) this.modeDisplay.textContent = '即時診斷';
        } else {
            // 診斷前是 raw camera 模式 → 回到手機相機
            this.showLocalCamera();
        }
    }

    renderDiagnosis(data) {
        let content = '';
        content += '偵測到的損傷：\n';
        if (data.detections && data.detections.length > 0) {
            for (const det of data.detections) {
                content += '• ' + det.class + '（' + (det.confidence * 100).toFixed(0) + '%）\n';
            }
        } else {
            content += '未偵測到缺陷\n';
        }
        return content;
    }
}
