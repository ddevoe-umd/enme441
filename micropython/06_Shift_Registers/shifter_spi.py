# shifter_spi.py
#
# Shift register class using hardware SPI
# Supports one or more daisy-chained 74HC595 shift registers.
#
# ESP32-C3 SuperMini

from machine import Pin, SPI
import time

# ----------------------------------------------------------
# Bit-reversal lookup table
# ----------------------------------------------------------

# Reversing here, rather than creating the SPI object with firstbit=SPI.LSB,
# leaves the bus in its normal MSB-first mode for every other peripheral
# sharing it.  The arithmetic below swaps nibbles, then pairs, then
# neighbors within the given byte.
def _reverse_byte(b):
    b = ((b & 0x0F) << 4) | (b >> 4)
    b = ((b & 0x33) << 2) | ((b & 0xCC) >> 2)
    b = ((b & 0x55) << 1) | ((b & 0xAA) >> 1)
    return b

# Save lookup table for a large number of bytes (256) to avoid wasting cycles
# re-creating it for each byte
_REV = bytes(_reverse_byte(i) for i in range(256))

# ----------------------------------------------------------
# Shifter class
# ----------------------------------------------------------

class Shifter:

    def __init__(self, spi, latch):
        """
        spi   : Pre-initialized machine.SPI object
        latch : GPIO connected to STCP (RCLK) of the 74HC595
        """
        self.spi = spi
        self.latch = Pin(latch, Pin.OUT)
        self.latch.off()

    def _latch(self):
        """ Transfer shifted data to the output pins """
        self.latch.on()
        time.sleep_us(1)
        self.latch.off()
    
    def shift(self, data, num_bits=8):
        nbytes = (num_bits + 7) // 8      # determine # of bytes
        for b in data.to_bytes(nbytes, 'little'):
            self.spi.write(_REV[b:b+1])   # need to slice _REV[b:b+1] to get a byte
                                          # otherwise _REV[b] retrns int
        self._latch()


# ----------------------------------------------------------
# Example
# ----------------------------------------------------------

if __name__ == "__main__":

    # Create the SPI object for use by Shifter
    spi = SPI(
        1,
        baudrate=1000000,
        polarity=0,
        phase=0,
        sck=Pin(5),
        mosi=Pin(6)
    )

    s = Shifter(spi, latch=0)
    try:
        while True:
            for i in range(256):
                s.shift(i)
                time.sleep(0.001)
                print(f'{i:08b}')
    except:
        spi.deinit()   # Release the hardware SPI
