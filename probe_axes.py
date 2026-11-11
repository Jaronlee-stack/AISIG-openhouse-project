"""
Diagnostic: print every axis value from the wheel/pedals in real time.

Run it, then while it's running:
  1. Leave everything untouched for a couple seconds
  2. Press the GAS pedal fully
  3. Press the BRAKE pedal fully
  4. Turn the STEERING wheel fully left, then fully right

Copy the printed lines and paste them into the chat.
Press Ctrl+C to stop early.
"""
import time
import pygame

pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() == 0:
    print("No joystick/wheel detected.")
    raise SystemExit(1)

wheel = pygame.joystick.Joystick(0)
wheel.init()
print(f"Device: {wheel.get_name()}  |  axes: {wheel.get_numaxes()}")
print("Running for 20 seconds. Move gas, then brake, then steering...\n")

end = time.time() + 20
try:
    while time.time() < end:
        pygame.event.pump()
        values = "  ".join(f"{i}:{wheel.get_axis(i):+.2f}" for i in range(wheel.get_numaxes()))
        print(values)
        time.sleep(0.2)
except KeyboardInterrupt:
    pass

print("\nDone.")
