import os
import socketio
import pygame
import time
import sys

# Seconds given to each calibration step (gas, brake, steering)
CALIBRATION_SECONDS = 4
# An axis must move at least this far during its step to be accepted
MIN_AXIS_RANGE = 0.3

# Deadzone threshold: ignore minor stick drift or pedal rest noise
DEADZONE = 0.05

# Calibrated precisely to your system specs
MAX_SPEED = 1.3

# Waveshare's mandatory namespace endpoint
WAVESHARE_NAMESPACE = '/json'

sio = socketio.Client()
ROBOT_URL = os.environ.get("ROBOT_URL", "http://192.168.50.5:5000")

# Initialize Pygame Controller Subsystems
pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() == 0:
    print("❌ Critical: No steering wheel or joystick detected! Check USB connectivity.")
    sys.exit()

wheel = pygame.joystick.Joystick(0)
wheel.init()
print(f"🎮 Connected to Input Device: {wheel.get_name()}")

@sio.event(namespace=WAVESHARE_NAMESPACE)
def connect():
    print(f"✅ Real-time pipeline linked safely inside namespace: {WAVESHARE_NAMESPACE}")

@sio.event(namespace=WAVESHARE_NAMESPACE)
def disconnect():
    print("⚠️ Connection dropped from UGV Beast.")


def read_axes():
    pygame.event.pump()
    return [wheel.get_axis(i) for i in range(wheel.get_numaxes())]


def calibrate():
    """Ask the user to move each control, and pick the axis that moves for each one.

    Works on any wheel, so the axis numbers don't have to be hard-coded.
    """
    print("\n=== Calibration ===")
    print("Leave the wheel and pedals untouched, then press Enter.")
    input()
    rest = read_axes()

    steps = [
        ("gas", "Press the GAS pedal fully and hold it"),
        ("brake", "Press the BRAKE pedal fully and hold it"),
        ("steering", "Turn the STEERING wheel fully left, then fully right"),
    ]
    results = {}
    for name, prompt in steps:
        input(f"{prompt}. Press Enter, then do it for {CALIBRATION_SECONDS} seconds...")
        lo = [1e9] * len(rest)
        hi = [-1e9] * len(rest)
        end = time.time() + CALIBRATION_SECONDS
        while time.time() < end:
            values = read_axes()
            for i, v in enumerate(values):
                lo[i] = min(lo[i], v)
                hi[i] = max(hi[i], v)
            time.sleep(0.01)

        used = [r["axis"] for r in results.values()]
        candidates = [i for i in range(len(rest)) if i not in used]
        best = max(candidates, key=lambda i: hi[i] - lo[i])
        if hi[best] - lo[best] < MIN_AXIS_RANGE:
            print(f"❌ Calibration failed: no axis moved enough for {name}.")
            print("   Check the wheel and pedal cables, then run the script again.")
            sys.exit(1)

        r = rest[best]
        if name == "steering":
            results[name] = {"axis": best, "rest": r, "lo": lo[best], "hi": hi[best]}
        else:
            # The pedal's pressed position is whichever extreme is farther from rest
            pressed = lo[best] if (r - lo[best]) > (hi[best] - r) else hi[best]
            results[name] = {"axis": best, "rest": r, "pressed": pressed}
        print(f"   {name} -> axis {best}")

    return results


def pedal_amount(raw, c):
    """0.0 at rest, 1.0 fully pressed."""
    span = c["pressed"] - c["rest"]
    if abs(span) < 1e-6:
        return 0.0
    return max(0.0, min(1.0, (raw - c["rest"]) / span))


def steering_amount(raw, c):
    """-1.0 full left, 0.0 centred, +1.0 full right (sign depends on the wheel)."""
    if raw >= c["rest"]:
        span = c["hi"] - c["rest"]
    else:
        span = c["rest"] - c["lo"]
    if abs(span) < 1e-6:
        return 0.0
    return max(-1.0, min(1.0, (raw - c["rest"]) / span))


def start_driving_loop(cal):
    print(f"\n🏎️ System Live! Max Speed Limit: {MAX_SPEED}")
    print("Let go of controls or step off pedals to auto-stop. Press Ctrl+C to halt.")

    # Track the last sent motor speeds to prevent spamming duplicates
    last_left = None
    last_right = None
    # Throttle console output so printing doesn't stall the control loop
    last_print = 0.0

    while True:
        # Flush internal event queues to refresh system inputs
        pygame.event.pump()

        # 1. Read calibrated inputs
        raw_steering = steering_amount(wheel.get_axis(cal["steering"]["axis"]), cal["steering"])
        throttle_intensity = pedal_amount(wheel.get_axis(cal["gas"]["axis"]), cal["gas"])
        brake_intensity = pedal_amount(wheel.get_axis(cal["brake"]["axis"]), cal["brake"])

        # 2. Apply deadzone to separate pedal intensities before mixing
        if throttle_intensity < DEADZONE:
            throttle_intensity = 0.0
        if brake_intensity < DEADZONE:
            brake_intensity = 0.0

        linear_drive = throttle_intensity - brake_intensity

        if abs(raw_steering) < DEADZONE:
            raw_steering = 0.0

        # 3. Check for absolute idle state (Auto-Stop Routine)
        if raw_steering == 0.0 and throttle_intensity == 0.0 and brake_intensity == 0.0:
            if last_left != 0.0 or last_right != 0.0:
                if sio.connected:
                    sio.emit('json', {"T": 1, "L": 0.0, "R": 0.0}, namespace=WAVESHARE_NAMESPACE)
                print("🛑 STOPPED (No Active Input Detected)                  ", end="\r")
                last_left = 0.0
                last_right = 0.0
            time.sleep(0.01)
            continue

        # 4. Differential Drive Mixing Logic
        left_speed = linear_drive + raw_steering
        right_speed = linear_drive - raw_steering

        # 5. Proportional Normalization
        max_motor_calc = max(abs(left_speed), abs(right_speed))
        if max_motor_calc > 1.0:
            left_speed /= max_motor_calc
            right_speed /= max_motor_calc

        # Scale outputs up to the speed limit
        final_left = round(left_speed * MAX_SPEED, 2)
        final_right = round(right_speed * MAX_SPEED, 2)

        # 6. Only send over network if values have ACTUALLY changed
        if final_left != last_left or final_right != last_right:
            payload = {"T": 1, "L": final_left, "R": final_right}

            # 7. Broadcast frame to the correct namespace
            if sio.connected:
                sio.emit('json', payload, namespace=WAVESHARE_NAMESPACE)
                now = time.monotonic()
                if now - last_print >= 0.5:
                    print(f"Driving -> L: {payload['L']} | R: {payload['R']}                  ", end="\r")
                    last_print = now

            # Update state anchors
            last_left = final_left
            last_right = final_right

        time.sleep(0.01)  # ~100Hz loop cap; sends only on change


if __name__ == '__main__':
    # Calibrate before connecting, so the robot can't move during setup
    cal = calibrate()
    print(f"Calibrated: steering axis {cal['steering']['axis']}, "
          f"gas axis {cal['gas']['axis']}, brake axis {cal['brake']['axis']}")

    try:
        try:
            sio.connect(ROBOT_URL, namespaces=[WAVESHARE_NAMESPACE], transports=['websocket'])
        except Exception as e:
            print(f"❌ Could not connect to robot at {ROBOT_URL}{WAVESHARE_NAMESPACE}: {e}")
            print("   Check that the robot is powered on, this PC is on its network, and ROBOT_URL is correct.")
            sys.exit(1)
        start_driving_loop(cal)
    except KeyboardInterrupt:
        print("\nHalting session loop. Forcing safe vehicle brake drop sequence...")
    except Exception as e:
        print(f"\nPipeline execution aborted: {e}")
    finally:
        # Send a stop on every exit path, including crashes, before disconnecting
        if sio.connected:
            sio.emit('json', {"T": 1, "L": 0.0, "R": 0.0}, namespace=WAVESHARE_NAMESPACE)
            sio.disconnect()
        print("Driver script safely shut down.")
