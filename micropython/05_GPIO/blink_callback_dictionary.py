# blink_callback_dictionary.py
#
# Use a dictionary to relate two input and output pins.
# Flip the state of an output pin when the
# corresponding input pin sees a transition.
#
# ESP32-C3


from machine import Pin

# Define input pins:
in1 = Pin(0, Pin.IN)
in2 = Pin(1, Pin.IN)

# Define output pins:
out1 = Pin(2, Pin.OUT)
out2 = Pin(3, Pin.OUT)

# relate input/output pins using a dictionary:
pins =  {in1:out1, in2:out2}

# Define a callback function:
def myCallback(p):
    print(f'Transition detected on pin {p}')
    pin = pins[p]  # find the output Pin from the dictionary
    pin.value(int(not pin.value()))   # flip the pin state

# Execute myCallback() if pin 1 goes HIGH:
in1.irq(handler=myCallback, trigger=Pin.IRQ_RISING)

# Execute myCallback() if pin 2 goes either LOW or HIGH:
in2.irq(handler=myCallback, trigger=(Pin.IRQ_FALLING | Pin.IRQ_RISING))

try:
    while True:
        pass
except KeyboardInterrupt:
    print('Exiting\n')
