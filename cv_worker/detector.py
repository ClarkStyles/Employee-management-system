"""
YOLOv11n ONNX inference and ROI cropping.
"""
import cv2
import numpy as np
import logging
import onnxruntime as ort
from . import config

logger = logging.getLogger(__name__)

class Detector:
    def __init__(self):
        try:
            providers = ['TensorRTExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']
            self.session = ort.InferenceSession(config.ONNX_MODEL_PATH, providers=providers)
            self.input_name = self.session.get_inputs()[0].name
            self.input_shape = self.session.get_inputs()[0].shape
            self.input_h = self.input_shape[2] if isinstance(self.input_shape[2], int) else 640
            self.input_w = self.input_shape[3] if isinstance(self.input_shape[3], int) else 640
            
            # Check if model has NMS baked in by inspecting output shape
            self.output_names = [out.name for out in self.session.get_outputs()]
            logger.info(f"Loaded ONNX model: {config.ONNX_MODEL_PATH} on {self.session.get_providers()[0]}")
        except Exception as e:
            logger.error(f"Failed to load ONNX model: {e}")
            raise

    def get_roi_mask(self, img_shape, polygon_coords):
        """Creates a binary mask for the given polygon coordinates (proportional 0-1)."""
        h, w = img_shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        pts = np.array([[int(x * w), int(y * h)] for x, y in polygon_coords], np.int32)
        pts = pts.reshape((-1, 1, 2))
        cv2.fillPoly(mask, [pts], 255)
        return mask

    def preprocess(self, img):
        # Resize to input shape
        img = cv2.resize(img, (self.input_w, self.input_h))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        # HWC to CHW
        img = img.transpose(2, 0, 1)
        # Add batch dimension and normalize
        img = np.expand_dims(img, axis=0).astype(np.float32) / 255.0
        return img
        
    def nms(self, boxes, scores, iou_threshold):
        # Custom NMS in case it's not exported with nms=True
        indices = cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), 0.0, iou_threshold)
        return indices.flatten() if len(indices) > 0 else []

    def detect(self, frame, roi_coords=None):
        """
        Detect persons in the frame. If roi_coords is provided, crop/mask the frame first.
        """
        if roi_coords:
            mask = self.get_roi_mask(frame.shape, roi_coords)
            masked_frame = cv2.bitwise_and(frame, frame, mask=mask)
            
            # Optimization: use cv2.boundingRect to find bounding box of ROI coordinates
            h, w = frame.shape[:2]
            pts = np.array([[int(x * w), int(y * h)] for x, y in roi_coords], np.int32)
            x, y, bw, bh = cv2.boundingRect(pts)
            
            # Ensure within frame bounds
            x1, y1 = max(0, x), max(0, y)
            x2, y2 = min(w - 1, x + bw), min(h - 1, y + bh)
            
            if x2 > x1 and y2 > y1:
                cropped = masked_frame[y1:y2+1, x1:x2+1]
                input_tensor = self.preprocess(cropped)
            else:
                return []
        else:
            input_tensor = self.preprocess(frame)

        outputs = self.session.run(self.output_names, {self.input_name: input_tensor})
        
        # Parse outputs (YOLOv8/11 format typically: [batch, num_classes+4, num_boxes] if nms=False
        # If nms=True, format is usually [batch, num_boxes, 6] (x1, y1, x2, y2, conf, cls)
        out = outputs[0]
        
        boxes = []
        confidences = []
        
        if len(out.shape) == 3 and out.shape[1] > 6:
            # Format: [1, 84, 8400] (for 80 classes)
            out = out[0].transpose(1, 0) # [8400, 84]
            
            for row in out:
                # class scores start from index 4
                class_scores = row[4:]
                class_id = np.argmax(class_scores)
                
                # Filter by PERSON class
                if class_id != config.PERSON_CLASS_ID:
                    continue
                    
                conf = class_scores[class_id]
                if conf > config.CONFIDENCE_THRESHOLD:
                    # x, y, w, h
                    x, y, w, h = row[0], row[1], row[2], row[3]
                    # convert to x1, y1, x2, y2
                    x1 = x - w/2
                    y1 = y - h/2
                    x2 = x + w/2
                    y2 = y + h/2
                    boxes.append([x1, y1, x2, y2])
                    confidences.append(float(conf))
            
            if boxes:
                indices = self.nms(np.array(boxes), np.array(confidences), config.NMS_IOU_THRESHOLD)
                return [boxes[i] for i in indices]
            return []
            
        elif len(out.shape) == 3 and out.shape[2] == 6:
            # nms=True format
            for row in out[0]:
                x1, y1, x2, y2, conf, cls = row
                if int(cls) == config.PERSON_CLASS_ID and conf > config.CONFIDENCE_THRESHOLD:
                    boxes.append([x1, y1, x2, y2])
            return boxes
            
        # Fallback if structure is unknown
        return []
