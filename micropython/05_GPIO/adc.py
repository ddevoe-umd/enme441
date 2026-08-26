# adc.py
#
# Analog-to-digital conversion
#
# ESP32-C3

from machine import Pin, ADC
from time import sleep

# ESP32 has 12-bit ADC

# ADC is available on pins 0-4 on the ESP32-C3.
# These are the ADC1 channels. GPIO 5 is the only ADC2 channel,
# and ADC2 shares hardware with the radio -- readings there are
# unreliable whenever WiFi is active, so stay on pins 0-4.

# Set up a potentiometer with outer pins at 3.3V and gnd,
# and the middle pin connected to GPIO 0

# create an ADC object
adc = ADC(Pin(0))     # options for C3: 0,1,2,3,4

# Add attenuation to increase the input voltage range
# (ranges below are for the ESP32-C3 -- other ESP32 variants have different values):
# ADC.ATTN_0DB: No attenuation (0mV ~ 750mV)
# ADC.ATTN_2_5DB: 2.5dB attenuation (0mV ~ 1050mV)
# ADC.ATTN_6DB: 6dB attenuation (0mV ~ 1300mV)
# ADC.ATTN_11DB: 11dB attenuation (0mV ~ 2500mV)

adc.atten(ADC.ATTN_11DB) 

while True:
    v1 = adc.read()        # 0 to (2^12)-1 = 4095
    v2 = adc.read_u16()    # 0 to (2^16)-1 = 65535
    v3 = adc.read_uv()     # microvolts w/o attenuation
    print(f'read: {v1:4.0d}, read_u16: {v2:5.0d}, read_uv: {v3:7.0d}')
    sleep(0.1)
    
