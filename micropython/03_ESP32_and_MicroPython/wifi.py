# wifi.py
#
# Establish WiFi connection
# Uses networks & credentials defined in the config file

import config
import network
import time

def connect():
    wlan = network.WLAN(network.STA_IF)
    
    wlan.active(False)
    time.sleep(0.5)
    wlan.active(True)
    time.sleep(0.5)  # let the radio come up before calling connect()
    
    if wlan.isconnected():
        print('WiFi connected:', wlan.ifconfig())
        return
    for ssid, password in config.WIFI_NETWORKS:
        print('Connecting to WiFi: {}...'.format(ssid))
        wlan.connect(ssid, password)
        timeout = 5
        start = time.time()
        while not wlan.isconnected():
            if time.time() - start > timeout:
                print(f'connection to {ssid} failed, try next network')
                wlan.disconnect()
                break
            time.sleep(1)
        else:
            # run only if the while() loop finished, i.e. connection made
            print('WiFi connected:', wlan.ifconfig())
            return
    print('Could not connect to any known WiFi network.')
