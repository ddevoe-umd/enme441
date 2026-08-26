# blink_pair_flag.py
#
# Blink 2 LEDs on and off at 1 Hz, with opposite polarity
# ESP32 C3
 
from machine import Pin
from time import sleep
 
led1 = Pin(0, Pin.OUT)
led2 = Pin(1, Pin.OUT)
state = 1    # flag for led1 ON (and led2 OFF) 
 
try:
    while True:
        led1.value(state)
        led2.value(~state)
        sleep(0.5)
        state = ~state      # flip the flag 
 
except KeyboardInterrupt:
    print('Exiting\n')
