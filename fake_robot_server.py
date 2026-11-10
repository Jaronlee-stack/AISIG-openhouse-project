"""
Fake robot server for testing General control.py without the Waveshare UGV Beast.

Listens on the /json namespace, logs every 'json' drive command it receives,
and reports the time gap between messages and the command values.

Run:   python fake_robot_server.py
Then point General control.py at it:
    set ROBOT_URL=http://localhost:5000     (Windows cmd)
    $env:ROBOT_URL="http://localhost:5000"  (PowerShell)
"""
import time

import socketio
from aiohttp import web

PORT = 5000
NAMESPACE = '/json'

sio = socketio.AsyncServer(cors_allowed_origins='*')
app = web.Application()
sio.attach(app)

state = {'count': 0, 'last_arrival': None, 'gap_sum_ms': 0.0, 'gap_max_ms': 0.0}


@sio.event(namespace=NAMESPACE)
async def connect(sid, environ):
    print(f"[connect] client {sid} joined {NAMESPACE}")


@sio.event(namespace=NAMESPACE)
async def disconnect(sid):
    print(f"[disconnect] client {sid} left")
    if state['count']:
        avg = state['gap_sum_ms'] / max(1, state['count'] - 1)
        print(f"[summary] {state['count']} messages, avg gap {avg:.1f} ms, "
              f"max gap {state['gap_max_ms']:.1f} ms")
    state.update(count=0, last_arrival=None, gap_sum_ms=0.0, gap_max_ms=0.0)


@sio.on('json', namespace=NAMESPACE)
async def on_json(sid, data):
    now = time.perf_counter()
    state['count'] += 1
    gap_ms = 0.0
    if state['last_arrival'] is not None:
        gap_ms = (now - state['last_arrival']) * 1000
        state['gap_sum_ms'] += gap_ms
        state['gap_max_ms'] = max(state['gap_max_ms'], gap_ms)
    state['last_arrival'] = now
    print(f"#{state['count']:>6}  gap {gap_ms:7.1f} ms  L={data.get('L')}  R={data.get('R')}")


if __name__ == '__main__':
    print(f"Fake robot listening on http://localhost:{PORT}{NAMESPACE}")
    web.run_app(app, host='0.0.0.0', port=PORT)
