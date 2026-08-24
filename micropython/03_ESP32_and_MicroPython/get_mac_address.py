# get_mac_address.py
#
# Find the MAC address for your ESP32 to register with 
# the umd-iot network

import network
import ubinascii
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
mac = ubinascii.hexlify(wlan.config('mac'), ':').decode()
print('MAC address:', mac)
