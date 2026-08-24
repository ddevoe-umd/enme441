# pwm_pulse.py
#
# Pulse an LED via PWM 
#
# ESP32 C3 SuperMini

from machine import Pin, PWM
from time import sleep

pwm = PWM(Pin(8))   # Use the built-in blue LED
                    # 5 kHz base frequency by default

# Alternates:
# pwm = PWM(Pin(8), freq=5000, duty=0)
# pwm.init(freq=5000, duty=0)
# pwm.freq(5000)
# pwm.duty(0)

def pulse():
    
    while True:
        for i in range(1024):
            pwm.duty(i)
            sleep(0.001)
        for i in range(1023,0,-1):
            pwm.duty(i)
            sleep(0.001)
try:
    pulse()
        
except KeyboardInterrupt:
    pwm.deinit()       # Turn off the PWM
