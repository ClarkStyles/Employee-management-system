import os
import sys

sys.path.insert(0, 'backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

import django
django.setup()

import redis
from cv_worker.capture import VideoStream
from cv_worker.detector import Detector
from cv_worker.preview import generate_preview

r = redis.Redis(host='127.0.0.1', port=6379, decode_responses=False)
r.set('preview_active:9', 1, ex=5)

src = 'https://www.youtube.com/watch?v=KMJS66jBtVQ'
vs = VideoStream(src)
frame = vs.read()
print('frame_read', frame is not None)
if frame is not None:
    d = Detector()
    roi = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    boxes = d.detect(frame, roi_coords=roi)
    print('box_count', len(boxes))
    generate_preview('9', frame, boxes, roi, customer_count=3, density=0.4)
    data = r.get('zone:9:preview')
    print('preview_written', data is not None)
    print('preview_len', len(data) if data is not None else 0)
vs.release()
