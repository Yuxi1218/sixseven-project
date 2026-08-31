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
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
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

class YOLOManager:
    def __init__(self):
        self.model_n = None
        self.model_s = None
        self.model_loaded = False
        self.current_frame = None
        self.annotated_frame = None
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
            
            # Load both models
            print("Loading yolo11n for streaming...")
            self.model_n = YOLO(CONFIG["yolo11n_model_path"])
            
            print("Loading yolo11s for diagnosis...")
            self.model_s = YOLO(CONFIG["yolo11s_model_path"])
            
            self.model_loaded = True
            print("Models loaded!")
            return {"status": "loaded", "device": self.device}
            
        except Exception as e:
            print(f"Model load error: {e}")
            YOLO_LOAD_FAILED = True
            return {"status": "demo_mode"}

    def infer(self, image_data, use_large=False):
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
                conf=CONFIG["confidence"],
                imgsz=CONFIG["img_size"],
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
                    "class": class_name,
                    "confidence": conf,
                    "bbox": xyxy.tolist()
                })
            
            annotated_img = img.copy()
            for det in detections:
                x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
                cv2.rectangle(annotated_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f'{det["class"]} {det["confidence"]:.2f}'
                cv2.putText(annotated_img, label, (x1, y1 - 10),
                          cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            with self.current_frame_lock:
                self.annotated_frame = annotated_img.copy()
            
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


@app.get("/", response_class=HTMLResponse)
async def index():
    with open(os.path.join(CONFIG["templates_dir"], "index.html"), "r", encoding="utf-8") as f:
        return f.read()


@app.get("/status")
async def get_status():
    return JSONResponse({
        "yolo_loaded": yolo_manager.model_loaded,
        "ollama_available": ollama_manager.available,
        "model_available": yolo_manager.YOLO_AVAILABLE
    })


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

        _, buffer = cv2.imencode('.jpg', result["annotated_image"],
                             [cv2.IMWRITE_JPEG_QUALITY, 80])
        annotated_b64 = base64.b64encode(buffer).decode('utf-8')

        return JSONResponse({
            "image": annotated_b64,
            "fps": result["fps"],
            "detections": result["detections"]
        })

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
    uvicorn.run(app, host="0.0.0.0", port=8000)