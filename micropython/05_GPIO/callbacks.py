# External interrupts using callback functions
# ESP32-C3

from machine import Pin

# Define input pins:
in1 = Pin(0, Pin.IN, Pin.PULL_DOWN)
in2 = Pin(1, Pin.IN, Pin.PULL_DOWN)

# Define a callback function:
def myCallback(p):
    print(f'Transition detected on {p}')

#     Pin.irq(handler=Function_to_call,
#             trigger=(Pin.IRQ_FALLING | Pin.IRQ_RISING),
#             wake=(machine.IDLE | machine.SLEEP | machine.DEEPSLEEP)
#
# Note: the wake argument is not supported on the ESP32-C3, which
# has no RTC IO subsystem -- passing it raises "invalid pin for
# wake". Use esp32.wake_on_gpio() to wake the C3 from sleep.

# Execute myCallback() if pin 1 goes HIGH:
in1.irq(handler=myCallback, trigger=Pin.IRQ_RISING)

# Execute myCallback() if pin 2 goes either LOW or HIGH:
in2.irq(handler=myCallback, trigger=(Pin.IRQ_FALLING | Pin.IRQ_RISING))

try:
    while True:
        pass
except:
    print('Exiting\n')


