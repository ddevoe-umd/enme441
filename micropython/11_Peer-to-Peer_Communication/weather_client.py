# weather_client.py
#
# The ESP32 as an HTTP *client*: fetch the current temperature and
# humidity for College Park, MD from the National Weather Service and
# print them.  
#
# requests replaces the entire socket / bind / listen / send / recv dance
# with two lines -- but only for the client half.  There is no
# requests-equivalent for serving.
#
# Install the library first:
#     import mip
#     mip.install('requests')
#
# ESP32 C3

import wifi
import requests
import time

STATION = 'KCGS'  # College Park Airport (KCGS)
URL = f'https://api.weather.gov/stations/{STATION}/observations/latest'

# api.weather.gov answers HTTP 403 to any request with no User-Agent.
# The NWS asks that you identify your application and give a contact
# address -- put your own terpmail address in here before running this:
HEADERS = {'User-Agent': '(ENME441 project, nobody@umd.edu)'}

def get_observation():
    '''Return (timestamp, temp_C, humidity_pct), or None if unavailable.'''
    try:
        r = requests.get(URL, headers=HEADERS)
    except OSError as e:      # DNS failure, no route, TLS handshake failed
        print('Request failed:', e)
        return None
    try:
        if r.status_code != 200:
            print(f'Server returned HTTP {r.status_code}')
            return None
        obs = r.json()['properties']
    finally:
        r.close()   # urequests does NOT close the socket for you.  Skip
                    # this and the board runs out of sockets after a
                    # handful of requests, then every call fails.

    # Any field can be null when the station misses an hourly report,
    # so never assume a number came back:
    return (obs['timestamp'],
            obs['temperature']['value'],        # degrees C
            obs['relativeHumidity']['value'])   # percent


wifi.connect()

while True:
    result = get_observation()
    if result is None:
        print('No observation available\n')
    else:
        timestamp, temp_c, humidity = result
        print(f'Observation at {timestamp} ({STATION})')
        if temp_c is None:
            print('  temperature: not reported')
        else:
            print(f'  temperature: {temp_c:.1f} C  ({temp_c*9/5 + 32:.1f} F)')
        if humidity is None:
            print('  humidity:    not reported\n')
        else:
            print(f'  humidity:    {humidity:.0f} %\n')

    # Stations report about once an hour, so there is nothing to gain by
    # asking more often -- and the NWS asks that you not hammer the API.
    time.sleep(600)


# ---------------------------------------------------------------------
# If the 4.7 kB response plus the TLS handshake proves too much for the
# board's memory, Open-Meteo returns the same two values in about 380
# bytes, with no User-Agent required:
#
#   URL = ('https://api.open-meteo.com/v1/forecast'
#          '?latitude=38.9897&longitude=-76.9378'
#          '&current=temperature_2m,relative_humidity_2m')
#   c = requests.get(URL).json()['current']
#   c['temperature_2m'], c['relative_humidity_2m']
# ---------------------------------------------------------------------
