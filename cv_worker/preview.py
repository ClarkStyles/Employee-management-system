"""
CV Worker Preview Module.

Generates annotated JPEG preview frames for active zone monitoring requests.
Frames are written to Redis (zone:{zone_id}:preview) with a short TTL.
Only generates when Redis flag preview_active:{zone_id} is set and > 0.
Frames are NEVER written to disk.
"""

import base64
import logging
import cv2
import numpy as np
import redis

from . import config

logger = logging.getLogger(__name__)

# Module-level Redis connection (lazy init)
_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            decode_responses=False
        )
    return _redis_client


def is_preview_active(zone_id: str) -> bool:
    """Check if any manager client is currently watching this zone's preview."""
    try:
        r = _get_redis()
        val = r.get(f"preview_active:{zone_id}")
        return val is not None and int(val) > 0
    except Exception as e:
        logger.error(f"is_preview_active error: {e}")
        return False


def generate_preview(
    zone_id: str,
    frame: np.ndarray,
    boxes: list,
    roi_coords: list,
    customer_count: int = 0,
    density: float = 0.0,
) -> None:
    """
    Draw detection overlays onto a resized copy of the frame and write to Redis.

    Args:
        zone_id:        Zone identifier string (matches DB id)
        frame:          Raw BGR frame from cv2 (full resolution)
        boxes:          List of [x1,y1,x2,y2] bounding boxes in model coords
        roi_coords:     List of (x,y) proportional coordinates defining zone ROI
        customer_count: Current customer count for overlay text
        density:        Current density value for overlay text
    """
    if not is_preview_active(zone_id):
        return  # Nobody watching — skip encoding

    try:
        # --- 1. Resize to preview dimensions ---
        PREVIEW_W, PREVIEW_H = 400, 400
        orig_h, orig_w = frame.shape[:2]
        preview = cv2.resize(frame, (PREVIEW_W, PREVIEW_H))

        scale_x = PREVIEW_W / orig_w
        scale_y = PREVIEW_H / orig_h

        # --- 2. Draw ROI polygon ---
        if roi_coords:
            pts = np.array(
                [[int(x * PREVIEW_W), int(y * PREVIEW_H)] for x, y in roi_coords],
                dtype=np.int32
            ).reshape((-1, 1, 2))
            cv2.polylines(preview, [pts], isClosed=True, color=(0, 255, 255), thickness=2)

        # --- 3. Draw bounding boxes ---
        for box in boxes:
            x1, y1, x2, y2 = box
            # Scale from model-input space back to original, then to preview
            # boxes are already in original frame space (from detector.py before crop)
            px1 = int(x1 * scale_x)
            py1 = int(y1 * scale_y)
            px2 = int(x2 * scale_x)
            py2 = int(y2 * scale_y)

            # Clamp to preview dimensions
            px1, py1 = max(0, px1), max(0, py1)
            px2, py2 = min(PREVIEW_W - 1, px2), min(PREVIEW_H - 1, py2)

            cv2.rectangle(preview, (px1, py1), (px2, py2), color=(0, 200, 80), thickness=2)

        # --- 4. Text overlays ---
        zone_name = f"Zone {zone_id}"
        overlay_lines = [
            zone_name,
            f"Count: {customer_count}",
            f"Density: {density:.2f}",
        ]

        y_offset = 20
        for line in overlay_lines:
            # Shadow for readability
            cv2.putText(
                preview, line, (11, y_offset + 1),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2, cv2.LINE_AA
            )
            cv2.putText(
                preview, line, (10, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA
            )
            y_offset += 22

        # --- 5. JPEG encode (quality=60, heavily compressed) ---
        ok, buffer = cv2.imencode('.jpg', preview, [cv2.IMWRITE_JPEG_QUALITY, 60])
        if not ok:
            logger.warning(f"Preview JPEG encode failed for zone {zone_id}")
            return

        # --- 6. Base64-encode and write to Redis with TTL ---
        b64_frame = base64.b64encode(buffer.tobytes())
        r = _get_redis()
        r.set(f"zone:{zone_id}:preview", b64_frame, ex=5)  # 5-second TTL

    except Exception as e:
        logger.error(f"Preview generation error (zone {zone_id}): {e}", exc_info=True)
