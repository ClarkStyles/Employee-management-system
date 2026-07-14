import os
import sys
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "cv_worker" / "models"
MODEL_PATH = MODELS_DIR / "yolo11n.onnx"
# Ultralytics provides public links for some models, but usually you export it yourself.
# For demo purposes, we will use a small placeholder or a generic model url if available,
# or instruct the user. Let's use YOLOv8n ONNX URL from a public repo if possible, 
# or just create a dummy file if not found, since actual YOLOv11n onnx isn't officially direct-downloadable easily without the pip package.

# Actually, the best way to get it is using the ultralytics package we installed.
def download_model():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    if MODEL_PATH.exists():
        print(f"Model already exists at {MODEL_PATH}")
        return

    print("Exporting YOLOv11n to ONNX using ultralytics package...")
    try:
        from ultralytics import YOLO
        # This will download the pt file if missing, then export to onnx
        model = YOLO("yolo11n.pt") 
        # Using nms=False because we implemented runtime NMS in detector.py
        model.export(format="onnx", nms=False)
        
        # The exported file is created in the current working directory as yolo11n.onnx
        import shutil
        if os.path.exists("yolo11n.onnx"):
            shutil.move("yolo11n.onnx", str(MODEL_PATH))
            print(f"Model successfully exported to {MODEL_PATH}")
        else:
            print("Failed to find exported model.")
    except ImportError:
        print("Error: 'ultralytics' package not installed. Cannot export model.")
        sys.exit(1)
    except Exception as e:
        print(f"Error exporting model: {e}")
        sys.exit(1)

if __name__ == "__main__":
    download_model()
