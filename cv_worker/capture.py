"""
Video capture and frame sampling.
"""
import os
import cv2
import logging
from collections import deque
from . import config

logger = logging.getLogger(__name__)

class VideoStream:
    def __init__(self, src=0):
        self.src = src
        self.stream = cv2.VideoCapture(src)
        if not self.stream.isOpened():
            logger.error(f"Failed to open video source: {src}")

        self.frame_count = 0
        self.interval = config.FRAME_SAMPLE_INTERVAL
        # We can keep a ring buffer of the last N frames if we want to smooth over them
        # For memory, we won't keep the actual large frames here, but just return the current one.
        # We'll let the tracker do temporal smoothing of *counts*, not *frames*.

    def read(self):
        while self.stream.isOpened():
            ret, frame = self.stream.read()
            if not ret:
                # If it's a file, loop it
                if isinstance(self.src, str) and not self.src.startswith('rtsp://'):
                    logger.info(f"Looping video file: {self.src}")
                    self.stream.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    return None

            self.frame_count += 1
            if self.frame_count % self.interval == 0:
                return frame
                
        return None

    def release(self):
        self.stream.release()

class MultiStreamCapture:
    def __init__(self, sources=None):
        self.streams = []
        self.sources = sources or config.CAMERA_URLS
        for source in self.sources:
            if not source:
                continue
            # Handle local camera ID as integer if needed
            try:
                src = int(source)
            except ValueError:
                src = source
            self.streams.append(VideoStream(src))

    def get_frames(self):
        """Yields (stream_idx, frame)"""
        for i, stream in enumerate(self.streams):
            frame = stream.read()
            if frame is not None:
                yield i, frame

    def release(self):
        for stream in self.streams:
            stream.release()
