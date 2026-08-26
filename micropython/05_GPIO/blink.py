# blink.py
#
# Blink an LED on and off at 1 Hz
# ESP32 C3
 
from machine import Pin
from time import sleep
 
led = Pin(0, Pin.OUT)
 
try:
    while True:
        led.on()
        sleep(0.5)
        led.off()
        sleep(0.5)
 
except KeyboardInterrupt:
    print('Exiting\n')
