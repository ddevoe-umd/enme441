# Drive the motor through a shift register and ULN2803.
#
# ESP32-C3 -> 74HC595 -> ULN2803 -> stepper motor
#
# The shift register outputs drive the ULN2803 inputs, and the
# ULN2803 outputs sink current from the motor coils.  This lets
# the shift register control larger motors than it could
# drive directly.
#
# Power the shift register from 3.3V or 5V, and the ULN2803 COM pin
# and motor from 5V.  Tie all grounds together.

from machine import Pin
from shifter import Shifter
import time

s = Shifter(data=5, clock=7, latch=6)   # Set up shifter

m_seq = [0b0001,
         0b0011,
         0b0010,
         0b0110,
         0b0100,
         0b1100,
         0b1000,
         0b1001]

delay = 1200  # delay between steps [us]

# Make a full rotation of the output shaft:
def loop(dir):     # dir = rotation direction (1=ccw, -1=cw)
    m_state = 0    # track position within m_seq
    for i in range(4096): # 4096 half-steps/rev
        m_state += dir
        m_state %= 8
        # Same shift register outputs as stepper_with_shifter.py:
        s.shift(m_seq[m_state] << 4)
        time.sleep_us(delay)

try:
    loop(1)
    loop(-1)
except Exception as e:
    print(e)
finally:
    s.shift(0)    # De-energize all coils
