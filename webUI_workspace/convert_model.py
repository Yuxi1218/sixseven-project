import torch
import sys
import os

def convert_to_tensorrt(pt_path, output_path, img_size=640):
    if not os.path.exists(pt_path):
        print(f"Error: {pt_path} not found")
        return False
    
    try:
        from ultralytics import YOLO
        import torch
        
        print(f"Loading model: {pt_path}")
        model = YOLO(pt_path)
        
        success = model.export(
            format='engine',
            imgsz=img_size,
            device=0,
            half=True,
        )
        
        print(f"Model exported to: {success}")
        return success
        
    except Exception as e:
        print(f"Export error: {e}")
        
        try:
            import tensorrt as trt
            print("TensorRT not available, using FP16 ONNX instead")
            
            model = YOLO(pt_path)
            success = model.export(
                format='onnx',
                imgsz=img_size,
                half=True,
            )
            print(f"ONNX exported to: {success}")
            return success
            
        except Exception as e2:
            print(f"ONNX export also failed: {e2}")
            return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert_model.py <model.pt> [output_name]")
        sys.exit(1)
    
    pt_path = sys.argv[1]
    output_name = sys.argv[2] if len(sys.argv) > 2 else None
    
    if output_name:
        output_path = f"models/{output_name}.engine"
    else:
        output_path = None
    
    convert_to_tensorrt(pt_path, output_path)