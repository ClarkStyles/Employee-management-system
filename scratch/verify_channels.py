import os
import sys
import asyncio
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / 'backend'
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
import django

django.setup()

from channels.layers import get_channel_layer

async def main():
    layer = get_channel_layer()
    await layer.send('test.channel', {'type': 'test.message', 'value': 1})
    print('send ok')
    print(await layer.receive('test.channel'))

asyncio.run(main())
