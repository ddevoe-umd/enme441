# digital_in.py
#
# Read digital input values. Connect switches (or wires) between
# GPIO pins and defined voltage levels (0V or 3.3V)
#
# The ESP32 C3 GPIO pins are NOT 5V tolerant -- the absolute
# maximum is 3.6V. Driving a pin from 5V will damage the chip.
#
# ESP32 C3
 
from machine import Pin
from time import sleep
 
p1 = Pin(5, Pin.IN)
p2 = Pin(6, Pin.IN, Pin.PULL_UP)
p3 = Pin(7, Pin.IN, Pin.PULL_DOWN)
 
while True:
    print(f'{p1.value()}, {p2.value()}, {p3.value()}')
    sleep(0.1)
