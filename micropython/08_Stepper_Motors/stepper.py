# Stepper motor control
#
# ESP32-C3

from machine import Pin
import time

# Drive the motor directly from a ULN2803 Darlington array
#
# Power the stepper motor and ULN2803 from 5V on ESP32

pin_nums = [0,5,6,7] # ULN2803 inputs for each motor phase
pins = []
for pin_num in pin_nums:
  pins.append(Pin(pin_num, Pin.OUT))

delay = 1200  # delay between steps [us]

# Define the pin sequence for CW motion:
seq = [
    0b0001,
    0b0011,
    0b0010,
    0b0110,
    0b0100,
    0b1100,
    0b1000,
    0b1001
    ]

# Make a full rotation of the output shaft:
def loop(dir): # dir = 1 (cw) or -1 (ccw)
    pos = 0   # track position in cw sequence
    # 512 cycles per revolution
    # (8 cycles/rotation * 64 gear ratio):
    for i in range(512): 
        # 8 half-steps per cycle:
        for halfstep in range(8):
            # Walk through each of the 4 control pins:
            for j in range(4):
                pins[j].value(seq[pos] & (1<<j))
                
            pos += dir    # move to next position in sequence
            pos %= 8      # stay in [0,7] range
            time.sleep_us(delay)  # need small delay between steps
try:
  loop(1)
  loop(-1)
except Exception as e:
  print(e)

