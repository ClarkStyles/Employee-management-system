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
    def _open_stream(self):
        stream_url = self.src
        # Resolve YouTube URLs to direct video streams
        if isinstance(self.src, str) and ('youtube.com' in self.src or 'youtu.be' in self.src):
            logger.info(f"Resolving YouTube URL: {self.src}")
            try:
                import yt_dlp
                import os
                # Ensure deno is in PATH for yt-dlp to use as a JS runtime
                deno_path = os.path.expanduser('~\\.deno\\bin')
                if deno_path not in os.environ.get('PATH', ''):
                    os.environ['PATH'] = deno_path + os.pathsep + os.environ.get('PATH', '')
                
                # format string prioritizes mp4 up to 720p for fast CV processing
                ydl_opts = {'format': 'best[ext=mp4][height<=720]/best', 'quiet': True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(self.src, download=False)
                    stream_url = info['url']
                    logger.info(f"Resolved stream URL for {self.src}")
            except ImportError:
                logger.error("yt-dlp not installed. Cannot open YouTube links. Run: pip install yt-dlp")
            except Exception as e:
                logger.error(f"Failed to resolve YouTube URL {self.src}: {e}")

        self.stream = cv2.VideoCapture(stream_url, cv2.CAP_FFMPEG)
        if not self.stream.isOpened():
            logger.error(f"Failed to open video source: {self.src}")

    def __init__(self, src=0):
        self.src = src
        self.frame_count = 0
        self.interval = config.FRAME_SAMPLE_INTERVAL
        self._open_stream()

    def _restart_stream(self):
        """Close the current stream and reopen it from the beginning."""
        try:
            if hasattr(self, 'stream') and self.stream is not None:
                self.stream.release()
        except Exception:
            pass

        self.frame_count = 0
        self._open_stream()

    def read(self):
        if not hasattr(self, 'stream') or not self.stream.isOpened():
            logger.info(f"Attempting to reopen video source: {self.src}")
            import time
            time.sleep(2)
            self._open_stream()
            if not hasattr(self, 'stream') or not self.stream.isOpened():
                return None

        while self.stream.isOpened():
            ret, frame = self.stream.read()
            if not ret:
                logger.info(f"Reached end of video source, looping: {self.src}")
                self._restart_stream()
                if not self.stream.isOpened():
                    return None
                continue

            self.frame_count += 1
            if self.frame_count % self.interval == 0:
                return frame

        return None

    def release(self):
        if hasattr(self, 'stream'):
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
