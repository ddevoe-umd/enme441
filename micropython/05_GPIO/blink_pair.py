# blink_pair.py
#
# Blink 2 LEDs on and off at 1 Hz, with opposite polarity
# ESP32 C3
 
from machine import Pin
from time import sleep
 
led1 = Pin(0, Pin.OUT)
led2 = Pin(1, Pin.OUT)
 
try:
    while True:
        led1.on()
        led2.off()
        sleep(0.5)
        led1.off()
        led2.on()
        sleep(0.5)
 
except KeyboardInterrupt:
    print('Exiting\n')
