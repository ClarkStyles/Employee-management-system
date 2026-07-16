import redis
import time
import sys

r = redis.Redis(host='127.0.0.1', port=6379, decode_responses=False)
print("Watching zone:9:preview...", flush=True)

# Simulate manager watching
r.set("preview_active:9", 1)

try:
    for i in range(20):
        val = r.get("zone:9:preview")
        if val:
            print(f"[{i}] Found frame! Size: {len(val)}", flush=True)
        else:
            print(f"[{i}] No frame.", flush=True)
        time.sleep(1)
finally:
    r.delete("preview_active:9")
    print("Done.", flush=True)
