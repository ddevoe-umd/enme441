# THIS IS AN OLDER VERSION WITH EXTRA (AND PROBABLY UNNECESSARY) 
# BITS OF CODE -- DO NOT USE UNLESS ISSUES WITH NEWER VERSION

# shifter_spi.py
#
# Shift register class using hardware SPI
# Supports one or more daisy-chained 74HC595 shift registers.
#
# ESP32-C3 SuperMini

from machine import Pin, SPI
import time


# Bit-reversal lookup table: _REV[b] is b with its eight bits reversed.
# Reversing here, rather than creating the SPI object with firstbit=SPI.LSB,
# leaves the bus in its normal MSB-first mode for every other peripheral
# sharing it.  The arithmetic below swaps nibbles, then pairs, then
# neighbors within the given byte.
def _rev8(b):
    b = ((b & 0x0F) << 4) | (b >> 4)
    b = ((b & 0x33) << 2) | ((b & 0xCC) >> 2)
    b = ((b & 0x55) << 1) | ((b & 0xAA) >> 1)
    return b

# Save the lookup table to avoid wasting cycles re-creating it for each byte
_REV = bytes(_rev8(i) for i in range(256))


def _flip_bits(data):
    """Reverse the bits of each byte so an MSB-first bus emits them LSB-first"""
    return bytes(_REV[b] for b in data)


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
        """
        Shift an arbitrary-length word to support chained registers,
        with SPI automatically pinging the clock pin on each bit
            data      : integer to transmit
            num_bits  : number of valid bits

        num_bits also says how wide the chain is: it is rounded up to a
        whole number of bytes, one byte per 74HC595.  The padding bits
        are sent first, so they end up in the furthest register.
        """
        nbytes = (num_bits + 7) // 8
        data &= (1 << num_bits) - 1     # Mask off unused upper bits
        data <<= -num_bits % 8          # Pad short of a byte with 0
        self.spi.write(_flip_bits(data.to_bytes(nbytes, 'little')))
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
        sck=Pin(7),
        mosi=Pin(5)
    )

    s = Shifter(spi, latch=6)

    while True:
        for i in range(256):
            s.shift(i)
            time.sleep(0.1)
