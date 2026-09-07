import os

# PyTorch/YOLO compatibility - will be set True if model loading fails
YOLO_LOAD_FAILED = False

# Register custom YOLO modules as safe globals (required by newer torch.load
# with weights_only=True to load ultralytics checkpoints).
import torch.serialization as ts
for mod in ['block', 'tasks']:
    for name in ['C3k2', 'C3k', 'C3', 'C2f', 'C2PSA', 'DetectionOutput']:
        try:
            ts.add_safe_globals([f'ultralytics.nn.modules.{mod}.{name}'])
            ts.add_safe_globals([f'ultralytics.nn.tasks.{name}'])
        except Exception:
            pass

import base64
import time
import threading
import cv2
import numpy as np
from PIL import Image as PILImage, ImageDraw, ImageFont
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG = {
    "yolo11n_model_path": os.path.join(BASE_DIR, "models", "yolo11n.pt"),
    "yolo11s_model_path": os.path.join(BASE_DIR, "models", "yolo11s.pt"),
    "ollama_url": "http://localhost:11434/api/generate",
    "ollama_model": "gemma3:1b",  # smallest available gemma3 tag
    "device": "cpu",
    "confidence": 0.25,
    "img_size": 640,
    "static_dir": os.path.join(BASE_DIR, "static"),
    "templates_dir": os.path.join(BASE_DIR, "templates"),
}

# 類別名稱中文化（用於標註框與前端顯示）
# 目前部署為 4 類緊急模型（damage/defect/crack/dent）；未來重訓 7 類時再恢復細分
CLASS_NAMES_ZH = {
    "Crack": "裂痕",
    "Dent": "凹痕",
    "Missing_Fastener": "缺鉚釘",
    "Skin_Cover": "蒙皮受損",
    "Fuselage_damage": "機身損傷",
    "Wing_damage": "機翼損傷",
    "Engine_damage": "引擎損傷",
}


def _zh_name(class_name):
    return CLASS_NAMES_ZH.get(class_name, class_name)

_FONT_PATH = "/usr/share/fonts/truetype/arphic/uming.ttc"


def _draw_zh_boxes(img, detections, font_size=None):
    """在 OpenCV BGR 圖上畫框+中文標籤，回傳 annotated BGR 圖。"""
    if font_size is None:
        font_size = max(16, int(min(img.shape[:2]) / 25))
    try:
        font = ImageFont.truetype(_FONT_PATH, font_size)
    except Exception:
        font = ImageFont.load_default()

    pil = PILImage.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    pad = font_size // 4

    for det in detections:
        x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
        draw.rectangle([x1, y1, x2, y2], outline=(0, 255, 0), width=2)
        label = f'{det["class"]} {det["confidence"]:.0%}'
        tb = draw.textbbox((x1, y1 - font_size - pad * 2), label, font=font)
        draw.rectangle(tb, fill=(0, 255, 0))
        draw.text((tb[0], tb[1]), label, fill=(0, 0, 0), font=font)

    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

class YOLOManager:
    def __init__(self):
        self.model_n = None
        self.model_s = None
        self.model_loaded = False
        self.current_frame = None
        self.annotated_frame = None
        self.annotated_seq = 0
        self.current_frame_lock = threading.Lock()
        self.fps = 0
        self.fps_counter = 0
        self.last_fps_time = time.time()
        self.device = "cpu"  # Default to CPU
        
        self.YOLO_AVAILABLE = False
        self.REQUESTS_AVAILABLE = False
        self._check_deps()

    def _check_deps(self):
        try:
            import torch
            from ultralytics import YOLO
            self.YOLO_AVAILABLE = True
            print("Ultralytics available")
        except ImportError as e:
            print(f"Ultralytics not available: {e}")
            
        try:
            import requests
            self.REQUESTS_AVAILABLE = True
        except ImportError:
            pass

    @staticmethod
    def _resolve_model_path(base_path):
        """依名稱解析最優模型：TensorRT .engine 優先於 .pt。找不到回 None。"""
        base = os.path.splitext(base_path)[0]
        for ext in [".engine", ".pt"]:
            cand = base + ext
            if os.path.exists(cand):
                return cand
        # 原路徑直接存在也可用
        if os.path.exists(base_path):
            return base_path
        return None

    @staticmethod
    def _describe_config(path):
        """回傳模型種類描述（供 log/除錯）。"""
        if not path:
            return "N/A"
        if path.endswith(".engine"):
            return "TensorRT engine"
        return os.path.splitext(os.path.basename(path))[0]

    def load_models(self):
        global YOLO_LOAD_FAILED
        if YOLO_LOAD_FAILED:
            print("Demo mode")
            return {"status": "demo_mode"}
        
        try:
            from ultralytics import YOLO
            import torch
            
            # Auto-detect GPU
            if torch.cuda.is_available():
                torch.cuda.set_device(0)
                self.device = "0"
                print("Using GPU")
            else:
                self.device = "cpu"
                print("Using CPU")
            
            # 找出實際存在的模型檔（engine > pt）
            stream_path = self._resolve_model_path(CONFIG["yolo11n_model_path"])
            diag_path = self._resolve_model_path(CONFIG["yolo11s_model_path"])
            print(f"串流模型: {stream_path} ({self._describe_config(stream_path)})")
            print(f"診斷模型: {diag_path} ({self._describe_config(diag_path)})")
            
            if stream_path is None or diag_path is None:
                print(f"模型檔缺失: stream={stream_path}, diag={diag_path}")
                YOLO_LOAD_FAILED = True
                return {"status": "demo_mode"}
            
            # 載入診斷模型（準確優先）
            print("Loading diagnosis model...")
            self.model_s = YOLO(diag_path)
            # 串流(即時診斷)也使用同一顆新 7 類模型（避免舊 nano engine 眼殘）
            # 共用同一個實例，省 Jetson 記憶體
            self.model_n = self.model_s
            
            self.model_loaded = True
            print("Models loaded!")
            return {"status": "loaded", "device": self.device}
            
        except Exception as e:
            print(f"Model load error: {e}")
            YOLO_LOAD_FAILED = True
            return {"status": "demo_mode"}

    def infer(self, image_data, use_large=False, conf=None, imgsz=None):
        if image_data is None:
            return None
        
        if isinstance(image_data, np.ndarray):
            img = image_data
        else:
            nparr = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return None
        
        with self.current_frame_lock:
            self.current_frame = img.copy()
        
        # FPS should update regardless of model availability
        self._update_fps()
        
        if not self.model_loaded:
            return {"detections": [], "annotated_image": img, "fps": self.fps}
        
        try:
            # yolo11n for streaming, yolo11s for diagnosis
            model = self.model_s if use_large else self.model_n
            
            results = model.predict(
                img,
                conf=conf if conf is not None else CONFIG["confidence"],
                imgsz=imgsz if imgsz is not None else CONFIG["img_size"],
                device=self.device,
                verbose=False,
            )
            
            if len(results) == 0:
                return {"detections": [], "annotated_image": img, "fps": self.fps}
            
            result = results[0]
            boxes = result.boxes
            
            detections = []
            for i in range(len(boxes)):
                box = boxes[i]
                xyxy = box.xyxy[0].cpu().numpy()
                conf = float(box.conf[0].cpu().numpy())
                cls = int(box.cls[0].cpu().numpy())
                class_name = result.names[cls]
                
                detections.append({
                    "class": _zh_name(class_name),
                    "confidence": conf,
                    "bbox": xyxy.tolist()
                })
            
            annotated_img = _draw_zh_boxes(img.copy(), detections)
            
            with self.current_frame_lock:
                self.annotated_frame = annotated_img.copy()
                self.annotated_seq += 1
            
            return {
                "detections": detections,
                "annotated_image": annotated_img,
                "fps": self.fps
            }
            
        except Exception as e:
            print(f"Inference error: {e}")
            return {"detections": [], "annotated_image": img, "fps": self.fps}

    def get_current_frame(self):
        with self.current_frame_lock:
            return self.current_frame.copy() if self.current_frame is not None else None

    def get_annotated_frame(self):
        with self.current_frame_lock:
            return self.annotated_frame.copy() if self.annotated_frame is not None else None

    def get_annotated_seq(self):
        with self.current_frame_lock:
            return self.annotated_seq

    def _update_fps(self):
        self.fps_counter += 1
        current_time = time.time()
        elapsed = current_time - self.last_fps_time
        
        if elapsed >= 1.0:
            self.fps = int(self.fps_counter / elapsed)
            self.fps_counter = 0
            self.last_fps_time = current_time


class OllamaManager:
    def __init__(self):
        self.url = CONFIG["ollama_url"]
        self.model = CONFIG["ollama_model"]
        self.available = False
        self.REQUESTS_AVAILABLE = False
        self._check_deps()
        self._check_connection()

    def _check_deps(self):
        try:
            import requests
            self.REQUESTS_AVAILABLE = True
        except ImportError:
            pass

    def _check_connection(self):
        if not self.REQUESTS_AVAILABLE:
            return

        try:
            import requests
            response = requests.get("http://localhost:11434/api/tags", timeout=5)
            if response.status_code == 200:
                self.available = True
                print("Ollama available")
        except Exception as e:
            print(f"Ollama not available: {e}")

    def generate_diagnosis(self, detections):
        if not self.available:
            return {
                "success": False,
                "message": "Ollama service not available",
                "diagnosis": "Please ensure Ollama is running on this device."
            }
        
        if not detections or len(detections) == 0:
            return {
                "success": True,
                "message": "No defects detected",
                "diagnosis": "No damage detected. The wing surface appears to be in good condition."
            }
        
        labels = list(set([d["class"] for d in detections]))
        labels_text = ", ".join(labels)
        
        prompt = f"""You are an aircraft maintenance expert. A wing damage inspection detected: {labels_text}

Provide:
1. Severity (Low/Medium/High)
2. Recommended repair actions
3. Whether immediate maintenance is needed

Be concise."""

        try:
            import requests
            response = requests.post(
                self.url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 130}
                },
                timeout=300
            )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    "success": True,
                    "message": "Diagnosis completed",
                    "diagnosis": result.get("response", ""),
                    "detections": detections
                }
            return {"success": False, "message": "Ollama error"}
            
        except Exception as e:
            return {"success": False, "message": str(e)}


yolo_manager = YOLOManager()
ollama_manager = OllamaManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting Jetson Wing Damage Detection System...")
    model_status = yolo_manager.load_models()
    print(f"Model status: {model_status}")
    yield


app = FastAPI(
    title="Sixseven Wing Damage Detection",
    description="Offline wing damage detection system",
    version="1.0.0",
    lifespan=lifespan
)

app.mount("/static", StaticFiles(directory=CONFIG["static_dir"]), name="static")


@app.middleware("http")
async def no_store_all(request, call_next):
    """整個站台不讓瀏覽器快取 → 評審/參賽者手機拿到的永遠是最新前端。"""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/", response_class=HTMLResponse)
async def index():
    with open(os.path.join(CONFIG["templates_dir"], "index.html"), "r", encoding="utf-8") as f:
        html = f.read()
    # 動態版號：app.js 修改時間 → 手機每次都會拿到最新前端，比賽現場免清快取
    try:
        mtime = int(os.path.getmtime(os.path.join(CONFIG["static_dir"], "app.js")))
        html = html.replace("?v=15", f"?v={mtime}")
    except OSError:
        pass
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/status")
async def get_status():
    return JSONResponse({
        "yolo_loaded": yolo_manager.model_loaded,
        "ollama_available": ollama_manager.available,
        "model_available": yolo_manager.YOLO_AVAILABLE
    })


@app.get("/stream")
async def stream_video():
    """MJPEG 串流：有新幀就吐新幀；逾時無新幀就重吐末幀，維持 img 流動不中斷。"""
    boundary = "frame"
    last_seq = -1
    last_tx = 0.0

    def generate():
        nonlocal last_seq, last_tx
        while True:
            seq = yolo_manager.get_annotated_seq()
            frame = yolo_manager.get_annotated_frame()
            now = time.time()
            if seq == last_seq and frame is not None and (now - last_tx) < 0.12:
                # 無新幀，給足時間讓下一幀到達；避免空轉
                time.sleep(0.02)
                continue
            if frame is None:
                time.sleep(0.05)
                continue
            last_seq = seq
            last_tx = time.time()
            ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                yield (b'--' + boundary.encode() + b'\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + str(len(buf)).encode() + b'\r\n\r\n'
                       + buf.tobytes() + b'\r\n')

    return StreamingResponse(
        generate(),
        media_type=f"multipart/x-mixed-replace; boundary={boundary}",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---- WebRTC 串流（DMA 式旁路，NVENC 硬編） ----
import webrtc_stream as webrtc

_peer_map = {}  # ident -> pc
_infer_task = None
_infer_running = False


def _stop_web_infer():
    """所有 WebRTC peer 關閉 → 停止連續推理，釋放 GPU（避免與診斷衝突）。"""
    global _infer_running
    _infer_running = False
    print("[web-infer] 停止（所有 peer 已關閉）")


def _web_infer_loop():
    """連續推理環：手機上游相機幀到達即推理，更新 annotated_frame 供下游推流。
    每幀 ~21ms（yolo11n imgsz640）→ 下游可達 ~45 FPS，繞過手機逐幀 encode。"""
    global _infer_running
    last_seq = -1
    cnt = 0
    processed = 0
    while _infer_running:
        try:
            seq = webrtc.get_upstream_seq()
            img = webrtc.get_upstream_frame_newest()
            if img is None or seq == last_seq:
                time.sleep(0.005)
                if img is None:
                    cnt += 1
                    if cnt % 100 == 0:
                        print(f"[web-infer] 無上游幀 ({cnt})")
                continue
            last_seq = seq
            img_h, img_w = img.shape[:2]
            if processed % 60 == 0:
                print(f"[web-infer] up frame shape={img.shape} (h={img_h} w={img_w})", flush=True)
            # live 走較準確的 7 類 yolo11s（已換掉眼殘的舊 nano engine）
            res = yolo_manager.infer(img, use_large=True, conf=CONFIG["confidence"], imgsz=640)
            # 把偵測框歸一化(0~1)推到手機疊加，手機顯示原生畫質
            dets = (res or {}).get("detections") or []
            if dets and img_w > 0 and img_h > 0:
                norm = [{
                    "class": d["class"],
                    "confidence": round(d["confidence"], 3),
                    "bbox": [
                        round(d["bbox"][0] / img_w, 4),
                        round(d["bbox"][1] / img_h, 4),
                        round(d["bbox"][2] / img_w, 4),
                        round(d["bbox"][3] / img_h, 4),
                    ],
                } for d in dets]
                webrtc.push_detections({"seq": seq, "n": len(norm), "detections": norm})
            elif not dets:
                webrtc.push_detections({"seq": seq, "n": 0, "detections": []})
            processed += 1
            if processed % 25 == 0:
                print(f"[web-infer] 推理 {processed} 幀(dc={len(webrtc._data_channels)})", flush=True)
        except Exception as e:
            print(f"[web-infer] err: {e}")
            time.sleep(0.02)


@app.get("/webrtc/offer")
async def webrtc_offer():
    """手機請求 offer：Jetson 建 pc + 啟用連續推理，回傳 SDP offer。"""
    global _infer_task, _infer_running
    try:
        webrtc.set_peer_closed_callback(_stop_web_infer)
        if not _infer_running:
            _infer_running = True
            _infer_task = threading.Thread(target=_web_infer_loop, daemon=True)
            _infer_task.start()
        webrtc.init(yolo_manager.get_annotated_frame)
        sdp, pc = await webrtc.create_offer()
        ident = str(id(pc))
        _peer_map[ident] = pc
        return JSONResponse({"sdp": sdp, "ident": ident})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"offer failed: {e}")


@app.post("/webrtc/answer")
async def webrtc_answer(request: Request):
    """手機回傳 answer SDP，建立連線開始推流。"""
    global _infer_running
    try:
        body = await request.json()
        ident = body.get("ident", "")
        sdp = body.get("sdp", "")
        if not sdp or ident not in _peer_map:
            raise HTTPException(status_code=400, detail="bad answer")
        pc = _peer_map.pop(ident)
        await webrtc.set_answer(pc, sdp)
        return JSONResponse({"ok": True})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"answer failed: {e}")


@app.post("/infer")
async def infer(request: Request):
    try:
        body = await request.json()
        image_b64 = body.get("image", "")

        if not image_b64:
            raise HTTPException(status_code=400, detail="No image provided")

        image_data = base64.b64decode(image_b64)
        result = yolo_manager.infer(image_data, use_large=False)

        if result is None:
            raise HTTPException(status_code=500, detail="Inference failed")

        # 極小 payload：不再回傳 base64 image（串流由 /stream 提供）
        return JSONResponse({
            "fps": result["fps"],
            "detections": result["detections"]
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/infer_hd")
async def infer_hd(request: Request):
    """高清定格偵斷：同一幀跑 3 次推理合併結果，降低單發漏檢。"""
    try:
        body = await request.json()
        image_b64 = body.get("image", "")
        if not image_b64:
            raise HTTPException(status_code=400, detail="No image provided")
        img = _decode_image(image_b64)
        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image")

        # 跑 3 次，合併 detections（下次格式，取最高信心 + 中位框）
        merged = {}
        det_tuple_list = []  # (conf, cls, bbox, annotated)
        annotated = None
        for _ in range(3):
            result = yolo_manager.infer(img, use_large=True, conf=0.25, imgsz=640)
            if result is None:
                raise HTTPException(status_code=500, detail="Inference failed")
            annotated = result["annotated_image"]
            for d in result["detections"]:
                key = f'{d["class"]}_{d["bbox"]}'
                det_tuple_list.append((d["confidence"], d["class"], d["bbox"]))
                if key not in merged or d["confidence"] > merged[key]["confidence"]:
                    merged[key] = {"class": d["class"], "confidence": d["confidence"], "bbox": d["bbox"]}

        detections = list(merged.values())
        # 信心由高至低排序
        detections.sort(key=lambda x: x["confidence"], reverse=True)

        # 用最後一次的 annotated 圖（含所有框）
        if annotated is not None and detections:
            annotated = _draw_zh_boxes(img.copy(), detections)

        print(f"[infer_hd×3] 圖{img.shape[1]}x{img.shape[0]} 合併後 {len(detections)} 個: " +
              "; ".join(f"{d['class']}({d['confidence']:.2f})" for d in detections))
        return JSONResponse({
            "success": True,
            "annotated_image": _encode_jpeg(annotated, 90),
            "detections": detections,
            "fps": result["fps"] if result else 0,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _decode_image(image_b64):
    image_data = base64.b64decode(image_b64)
    nparr = np.frombuffer(image_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image")
    return img


def _encode_jpeg(img, quality=85):
    _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(buffer).decode('utf-8')


# Defect classes that count as "major/structural" damage.
# Only when one of these is detected do we invoke the LLM (Ollama) diagnosis.
MAJOR_CLASSES = {"Fuselage_damage", "Wing_damage", "Engine_damage", "damage"}
MINOR_MESSAGE = ("此影像僅偵測到輕微缺陷，未啟動 LLM 診斷。"
                 "若有需要，請上傳更明顯的結構性損傷影像以獲得詳細維修建議。")


def _should_invoke_llm(detections):
    for det in detections or []:
        if det.get("class") in MAJOR_CLASSES:
            return True
    return False


@app.post("/reconnect-wifi")
async def reconnect_wifi(request: Request):
    """Debug 工具：把 WiFi 從 AP 模式切回原本的基地台（如 Yuxi's Room）。
    用於測試 Jetson 熱點後要恢復連線。需要 root（nmcli）。"""
    import subprocess as sp
    try:
        body = await request.json()
        target = (body.get("ssid") or "").strip()
    except Exception:
        target = ""

    # 目標 AP 名稱：預設 Yuxi's Room
    if not target:
        target = "Yuxi's Room"

    # 若目前在 AP 模式（有 sixseven-ap/AirCraft67Team），先刪掉該 hotAP con
    for hot_ssid in ["AirCraft67Team", "sixseven-ap"]:
        sp.run(["nmcli", "connection", "delete", hot_ssid],
               capture_output=True, text=True)

    # 開啟無線並連回目標 AP（自動重掃候選）
    sp.run(["nmcli", "radio", "wifi", "on"], capture_output=True, text=True)
    time.sleep(6)  # 等掃描
    r = sp.run(["nmcli", "device", "wifi", "connect", target],
               capture_output=True, text=True)
    time.sleep(6)  # 等 DHCP

    # 回報新 IP
    ips = sp.run(["hostname", "-I"], capture_output=True, text=True).stdout.strip()
    return JSONResponse({
        "ok": r.returncode == 0,
        "message": (r.stdout or r.stderr or "").strip()[:200],
        "ips": ips,
        "note": "若成功，WiFi 已回復到" + target + "；IP 會變，網頁可能需以新 IP 重新連線"
    })


@app.post("/diagnose")
async def diagnose():
    try:
        frame = yolo_manager.get_current_frame()

        if frame is None:
            raise HTTPException(status_code=400, detail="No frame available. Please start the camera first.")

        result = yolo_manager.infer(frame, use_large=True)

        if result is None:
            raise HTTPException(status_code=400, detail="Inference failed")

        if not _should_invoke_llm(result["detections"]):
            return JSONResponse({
                "success": True,
                "message": "Only minor defects detected; LLM not invoked",
                "diagnosis": MINOR_MESSAGE,
                "annotated_image": _encode_jpeg(result["annotated_image"]),
                "detections": result["detections"],
                "llm_invoked": False,
            })

        diag_result = ollama_manager.generate_diagnosis(result["detections"])
        diag_result["annotated_image"] = _encode_jpeg(result["annotated_image"])
        diag_result["detections"] = result["detections"]
        diag_result["llm_invoked"] = True
        return JSONResponse(diag_result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/diagnose_upload")
async def diagnose_upload(request: Request):
    try:
        body = await request.json()
        image_b64 = body.get("image", "")

        if not image_b64:
            raise HTTPException(status_code=400, detail="No image provided")

        img = _decode_image(image_b64)
        result = yolo_manager.infer(img, use_large=True)

        if result is None:
            raise HTTPException(status_code=400, detail="Inference failed")

        if not _should_invoke_llm(result["detections"]):
            return JSONResponse({
                "success": True,
                "message": "Only minor defects detected; LLM not invoked",
                "diagnosis": MINOR_MESSAGE,
                "annotated_image": _encode_jpeg(result["annotated_image"], 80),
                "detections": result["detections"],
                "llm_invoked": False,
            })

        diag_result = ollama_manager.generate_diagnosis(result["detections"])
        diag_result["annotated_image"] = _encode_jpeg(result["annotated_image"], 80)
        diag_result["detections"] = result["detections"]
        diag_result["llm_invoked"] = True
        return JSONResponse(diag_result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sixseven Wing Damage Detection WebUI")
    parser.add_argument("--ssl", action="store_true",
                        help="啟用 HTTPS（內網 camera 串流需安全來源，非 localhost 需 HTTPS）")
    parser.add_argument("--certfile", default="certs/cert.pem")
    parser.add_argument("--keyfile", default="certs/key.pem")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    ssl_kwargs = {}
    if args.ssl:
        cert = os.path.join(BASE_DIR, args.certfile)
        key = os.path.join(BASE_DIR, args.keyfile)
        if os.path.exists(cert) and os.path.exists(key):
            ssl_kwargs["ssl_certfile"] = cert
            ssl_kwargs["ssl_keyfile"] = key
            print(f"HTTPS 已啟用：https://{args.host}:{args.port}")
        else:
            print("⚠️ 找不到憑證，退回 HTTP")

    uvicorn.run(app, host=args.host, port=args.port, **ssl_kwargs)