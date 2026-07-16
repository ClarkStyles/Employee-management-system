import cv2
import yt_dlp
import sys
import os

url = "https://www.youtube.com/watch?v=rZBCPV01x8w"
print(f"Resolving {url}...")

deno_path = os.path.expanduser('~\\.deno\\bin')
if deno_path not in os.environ.get('PATH', ''):
    os.environ['PATH'] = deno_path + os.pathsep + os.environ.get('PATH', '')

ydl_opts = {'format': 'best[ext=mp4][height<=720]/best', 'quiet': True}
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(url, download=False)
    stream_url = info['url']

print("Stream URL resolved! (len: {})".format(len(stream_url)))
print("Opening with cv2.VideoCapture...")
cap = cv2.VideoCapture(stream_url)
if not cap.isOpened():
    print("FAILED to open video capture.")
    sys.exit(1)

print("Reading first frame...")
ret, frame = cap.read()
if not ret:
    print("FAILED to read first frame.")
    sys.exit(1)

print(f"Successfully read frame! Shape: {frame.shape}")
cap.release()
