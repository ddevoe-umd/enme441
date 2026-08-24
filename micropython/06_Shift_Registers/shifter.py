# shifter.py
#
# Shift register class
#
# ESP32-C3 SuperMini

from machine import Pin
import time 

class Shifter():

    def __init__(self, data, latch, clock):
        self.dataPin = Pin(data, Pin.OUT)
        self.latchPin = Pin(latch, Pin.OUT)
        self.clockPin = Pin(clock, Pin.OUT)

    def _ping(self, p):
        """ping the clock (CLK) or latch (RCLK) pin"""
        p.value(1)
        time.sleep_us(10)
        p.value(0)
        
    def shift(self, data, num_bits=8):
        """
        Shift all bits in an arbitrary-length word, allowing
        multiple 8-bit shift registers to be chained (with overflow
        of SR<n> tied to input of SR<n+1>)

        The value of num_bits determines how many shift registers
        are present (num_bits = 8 --> 1 SR by default).
        (N-1)*8 < num_bits <= N*8 implies there are N chained
        shift registers
        """

        """
        Load bits short of a byte with 0.  The math works because
        the modulo operator returns the remainder, defined as:
            a % b = a - b * floor(a/b)
        So for example:
            -10 % 8 = -10 - 8 * floor(-10 / 8) 
                    = -10 - 8 * floor(-1.25)
                    = -10 - 8 * (-2)
                    = -10 - (-16)
                    = 6
        Python's modulo is non-negative, so this works even
        when a < b.
        """
        for i in range(-num_bits%8):
            self.dataPin.value(0)
            self._ping(self.clockPin)

        # Send the word
        for i in range(num_bits):
            self.dataPin.value(data & (1<<i))
            self._ping(self.clockPin)
        self._ping(self.latchPin)
        
    

# ----------------------------------------------------------
# Example
# ----------------------------------------------------------

if __name__ == "__main__":
    s = Shifter(data=6, latch=0, clock=5)
    for i in range(256):
        s.shift(i)
        time.sleep(0.001)
