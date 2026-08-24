# pwm_blink.py
#
# Basic PWM example
# ESP32 C3 SuperMini

from machine import Pin, PWM

# Use PWM on built-in LED
pwm = PWM(Pin(8), freq=10, duty=512)

f = pwm.freq()   # get the base frequency; pwm.freq(x) sets it.
                 # Channels sharing an LEDC timer share a
                 # frequency, so changing one can move another.

# Alternate ways to set the duty cycle to 50% (for example):
# pwm.duty(512)                # set 10-bit duty cycle (0-1023)
# pwm.duty_u16(32768)          # set 16-bit duty cycle (0-65535)
# pwm.duty_ns(int(1e9/f/2))    # set pulse width in nanoseconds

try:
    while True: 
        pass
    
except KeyboardInterrupt:
    pwm.deinit()       # Turn off the PWM
