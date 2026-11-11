import socketio
import pygame
import time
import sys

# Define your exact Thrustmaster T300 hardware mappings
AXIS_STEERING = 0  
AXIS_BRAKE    = 1  
AXIS_THROTTLE = 3  
                  
# Deadzone threshold: Ignore minor stick drifts or uncalibrated pedal rest noise
DEADZONE = 0.05 

# Calibrated precisely to your system specs
MAX_SPEED = 1.3  

# Waveshare's mandatory namespace endpoint
WAVESHARE_NAMESPACE = '/json'

sio = socketio.Client()
ROBOT_URL = "http://192.168.50.5:5000"

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

def normalize_pedal(axis_value):
    """Transforms racing pedals (+1.0 at rest to -1.0 mashed) to [0.0 to 1.0] scale."""
    normalized = ((axis_value - 1.0) / -2.0)
    return max(0.0, min(1.0, normalized))

def start_driving_loop():
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
        
        # 1. Read Raw Values from T300 Wheel Base
        raw_steering = wheel.get_axis(AXIS_STEERING)
        raw_brake    = wheel.get_axis(AXIS_BRAKE)
        raw_throttle = wheel.get_axis(AXIS_THROTTLE)
        
        # 2. Extract linear driving forces [0.0 to 1.0]
        throttle_intensity = normalize_pedal(raw_throttle)
        brake_intensity    = normalize_pedal(raw_brake)
        
        # Apply deadzone directly to separate pedal intensities before mixing
        if throttle_intensity < DEADZONE:
            throttle_intensity = 0.0
        if brake_intensity < DEADZONE:
            brake_intensity = 0.0
            
        linear_drive = throttle_intensity - brake_intensity
        
        if abs(raw_steering) < DEADZONE:
            raw_steering = 0.0

        # 3. Check for absolute idle state (Auto-Stop Routine)
        # Evaluates clean, post-deadzone values to prevent endless reversing loops
        if raw_steering == 0.0 and throttle_intensity == 0.0 and brake_intensity == 0.0:
            if last_left != 0.0 or last_right != 0.0:
                stop_payload = {"T": 1, "L": 0.0, "R": 0.0}
                if sio.connected:
                    sio.emit('json', stop_payload, namespace=WAVESHARE_NAMESPACE)
                print("🛑 STOPPED (No Active Input Detected)                  ", end="\r")
                last_left = 0.0
                last_right = 0.0
            time.sleep(0.01)
            continue
        
        # 4. Differential Drive Mixing Logic
        left_speed  = linear_drive + raw_steering
        right_speed = linear_drive - raw_steering

        # 5. Proportional Normalization
        max_motor_calc = max(abs(left_speed), abs(right_speed))
        if max_motor_calc > 1.0:
            left_speed  /= max_motor_calc
            right_speed /= max_motor_calc

        # Scale outputs strictly up to your 1.3 limit
        final_left  = round(left_speed * MAX_SPEED, 2)
        final_right = round(right_speed * MAX_SPEED, 2)

        # 6. Only send over network if values have ACTUALLY changed
        if final_left != last_left or final_right != last_right:
            payload = {
                "T": 1,
                "L": final_left,
                "R": final_right
            }
            
            # 7. Broadcast Frame to the correct namespace
            if sio.connected:
                sio.emit('json', payload, namespace=WAVESHARE_NAMESPACE)
                now = time.monotonic()
                if now - last_print >= 0.5:
                    print(f"Driving -> L: {payload['L']} | R: {payload['R']}                  ", end="\r")
                    last_print = now
            
            # Update state anchors
            last_left = final_left
            last_right = final_right
            
        time.sleep(0.01)  # ~100Hz loop cap; sends only on change, so network traffic stays low

if __name__ == '__main__':
    try:
        try:
            sio.connect(ROBOT_URL, namespaces=[WAVESHARE_NAMESPACE], transports=['websocket'])
        except Exception as e:
            print(f"❌ Could not connect to robot at {ROBOT_URL}{WAVESHARE_NAMESPACE}: {e}")
            print("   Check that the robot is powered on, this PC is on its network, and ROBOT_URL is correct.")
            sys.exit(1)
        start_driving_loop()
    except KeyboardInterrupt:
        print("\nHalting session loop. Forcing safe vehicle brake drop sequence...")
        if sio.connected:
            sio.emit('json', {"T": 1, "L": 0.0, "R": 0.0}, namespace=WAVESHARE_NAMESPACE)
            sio.disconnect()
        print("Driver script safely shut down.")
    except Exception as e:
        print(f"\nPipeline execution aborted: {e}")
