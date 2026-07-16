import asyncio
import websockets
import json

async def test_ws():
    uri = "ws://127.0.0.1:8000/ws/manager/preview/9/"
    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected!")
            
            # Wait for frames
            for _ in range(3):
                message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                data = json.loads(message)
                if data.get('type') == 'preview_frame':
                    frame_b64 = data.get('frame')
                    print(f"Received frame! Size: {len(frame_b64)}")
    except Exception as e:
        print(f"Connection failed or timed out: {e}")

if __name__ == "__main__":
    asyncio.run(test_ws())
