import os
import sys

sys.path.insert(0, 'backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

import django
django.setup()

from cv_worker.capture import VideoStream
from cv_worker.detector import Detector
from cv_worker import config

src = 'https://www.youtube.com/watch?v=KMJS66jBtVQ'
vs = VideoStream(src)
print('opened', vs.stream.isOpened())
frame = vs.read()
print('frame_read', frame is not None)
if frame is not None:
    print('shape', frame.shape)
    d = Detector()
    boxes = d.detect(frame, roi_coords=config.ZONE_ROIS['9'])
    print('boxes', boxes[:5])
vs.release()
