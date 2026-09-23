# External interrupts using callback functions with debouncing
# ESP32-C3

from machine import Pin
import time

DEBOUNCE_MS = 50     # ignore edges closer together than this

# Define input pins:
in1 = Pin(0, Pin.IN, Pin.PULL_DOWN)
in2 = Pin(1, Pin.IN, Pin.PULL_DOWN)

# Define the callback function:
def myCallback(p):
    print(f'Transition detected on {p}, value = {p.value()}')

# Wrap a callback with a per-pin debounce timer.
# The callback returns the actual handler function to which the
# Pin value is passed when the callback is triggered:
def debounced(callback, delay_ms=DEBOUNCE_MS):
    last = [0]        # list so the inner function can modify it
    def handler(p):
        now = time.ticks_ms()
        if time.ticks_diff(now, last[0]) > delay_ms:
            last[0] = now
            callback(p)
    return handler


# Create the IRQs using the callback function created when calling
# debounced(myCallback):
#
# Execute myCallback() if in1 (GPIO 0) goes HIGH:
in1.irq(handler=debounced(myCallback), trigger=Pin.IRQ_RISING)
#
# Execute myCallback() if in2 (GPIO 1) goes either LOW or HIGH:
in2.irq(handler=debounced(myCallback), trigger=(Pin.IRQ_FALLING | Pin.IRQ_RISING))

try:
    while True:
        time.sleep_ms(100)        # idle instead of spinning at 100% CPU
except KeyboardInterrupt:
    in1.irq(handler=None)
    in2.irq(handler=None)
    print('Exiting\n')