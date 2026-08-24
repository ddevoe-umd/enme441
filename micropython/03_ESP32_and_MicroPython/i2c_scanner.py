from machine import Pin
from machine import I2C

# Note: ESP32 C3 supports hardware I2C mapping to any GPIO pins. Other
# ESP32 variants have dedicated hardware I2C pins, with other pins
# only supporting software I2C. If using pins that don't support 
# hardware I2C, use the SoftI2C instead of I2C module:
# from machine import SoftI2C as I2C

def scan(sda=8, scl=9):
    i2c = I2C(sda=Pin(sda), scl=Pin(scl)) 
     
    print('Scanning I2C bus...')
    devices = i2c.scan()
    print(f'I2C device count: {len(devices)}')
    for d in devices:  
        print(f'Device address: {hex(d)}')
    print()

if __name__ == '__main__':
    scan(8,9)
