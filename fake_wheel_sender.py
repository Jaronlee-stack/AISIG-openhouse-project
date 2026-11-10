"""
Simulated wheel for testing without the Thrustmaster T300.

Sends the same kind of drive commands as General control.py, using a
steering sweep and a pedal pulse instead of real inputs. Runs the loop at
the same ~100 Hz rate and sends only when values change.

Run the fake server first (fake_robot_server.py), then:
    python fake_wheel_sender.py                  (defaults to localhost:5000, 10 s)
    python fake_wheel_sender.py 30               (run for 30 seconds)
"""
import math
import os
import sys
import time

import socketio

ROBOT_URL = os.environ.get("ROBOT_URL", "http://localhost:5000")
NAMESPACE = '/json'
MAX_SPEED = 1.3
LOOP_SLEEP = 0.01
DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0

sio = socketio.Client()
sio.connect(ROBOT_URL, namespaces=[NAMESPACE], transports=['websocket'])
print(f"Connected to {ROBOT_URL}{NAMESPACE}, sending for {DURATION:.0f} s")

last_left = None
last_right = None
sent = 0
start = time.monotonic()

try:
    while time.monotonic() - start < DURATION:
        t = time.monotonic() - start
        # Simulated inputs: steering sweeps left and right, throttle pulses on and off
        steering = 0.8 * math.sin(2 * math.pi * 0.25 * t)
        throttle = 0.6 if (int(t) % 4) < 2 else 0.0
        brake = 0.0

        linear_drive = throttle - brake
        left_speed = linear_drive + steering
        right_speed = linear_drive - steering
        max_motor = max(abs(left_speed), abs(right_speed))
        if max_motor > 1.0:
            left_speed /= max_motor
            right_speed /= max_motor
        final_left = round(left_speed * MAX_SPEED, 2)
        final_right = round(right_speed * MAX_SPEED, 2)

        if final_left != last_left or final_right != last_right:
            sio.emit('json', {"T": 1, "L": final_left, "R": final_right}, namespace=NAMESPACE)
            sent += 1
            last_left, last_right = final_left, final_right

        time.sleep(LOOP_SLEEP)
except KeyboardInterrupt:
    pass
finally:
    sio.emit('json', {"T": 1, "L": 0.0, "R": 0.0}, namespace=NAMESPACE)
    print(f"Sent {sent} commands. Stop command sent.")
    sio.disconnect()
