import redis
import time

r = redis.Redis(host='localhost', port=6379, decode_responses=False, protocol=2)
r_decoded = redis.Redis(host='localhost', port=6379, decode_responses=True, protocol=2)

# 1. Set preview_active:1
r_decoded.set('preview_active:1', 1)

print(f"preview_active:1 = {r.get('preview_active:1')}")
print("Waiting 3 seconds to see if cv_worker pushes frames...")
time.sleep(3)

# 2. Check if frames are generated
frame_data = r.get('zone:1:preview')
if frame_data:
    print(f"Frame data received, size: {len(frame_data)} bytes")
else:
    print("No frame data received.")
