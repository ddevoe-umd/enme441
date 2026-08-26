# pwm_pulser.py
#
# A Pulser object will pulse an LED via PWM 
# in a separate thread
#
# ESP32-C3

from machine import PWM, Pin
from time import sleep
from _thread import start_new_thread

class Pulser:
    
    def __init__(self, pin, period = 1.0):
        self.pwm = PWM(pin)
        self.isOn = False
        self.period = period
    
    def start(self):
        self.isOn = True
        start_new_thread(self.__pulse, ())
 
    def stop(self):
        self.isOn = False

    def __pulse(self):
        steps = 100
        while self.isOn:
            for i in range(steps):
                dc = int(2**16 * i / steps)
                self.pwm.duty_u16(dc)
                sleep(self.period / 2 / steps)
            for i in range(steps-1, 0, -1):
                dc = int(2**16 * i / steps)
                self.pwm.duty_u16(dc)
                sleep(self.period / 2 / steps)


p = Pulser(pin = 8, period = 1.0)

for i in range(3):
    print('Pulser ON')
    p.start()
    sleep(5)
    print('Pulser OFF')
    p.stop()
    sleep(5)



