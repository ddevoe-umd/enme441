# Drive a stepper motors through a shift register to
# save ESP32 GPIO pins on the M5Stack Atom Matrix
#
# Smaller steppers (e.g. 28BYJ-48) can be driven directly
# from the shift register outputs.
#
# Use Vcc = 5V for both the shift register & motor
#
# While this code is designed for driving a single motor,
# the value of using a shift register is that we
# can easily extend the code to work with 2 or more
# motors without using any additional GPIO pins.

from machine import Pin
from shifter import Shifter
import time

s = Shifter(data=5,latch=6,clock=7)   # Set up shifter

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
def loop(dir):     # dir = rotation direction (1=cww, -1=cw)
    m_state = 0    # track position within m_seq:
    for i in range(4096): # 4096 steps/rev
        m_state += dir
        m_state %= 8 
        s.shift(~(m_seq[m_state]<<4) & 0b11111111)
        time.sleep_us(delay)

try:
    loop(1)
except Exception as e:
    print(e)


