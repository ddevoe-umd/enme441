# blink_pair_toggle.py
#
# Blink 2 LEDs on and off at 1 Hz, with opposite polarity
# ESP32 C3
 
from machine import Pin
from time import sleep
 
led1 = Pin(0, Pin.OUT, value=0)   # Set initial value 
led2 = Pin(1, Pin.OUT, value=1)
 
try:
    while True:
        led1.toggle()
        led2.toggle()
        sleep(0.5)

except KeyboardInterrupt:
    print('Exiting\n')
