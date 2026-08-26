# hivemq.py
#
# Example comms with HiveMQ MQTT broker
#
# ESP32 C3

import config
import time
import json
import ssl
from machine import Pin
from umqtt.simple import MQTTClient

# --- Setup ---
led = Pin(8, Pin.OUT)  # Built-in LED

# --- MQTT callback for incoming commands ---
def on_message(topic, msg):
    print(f'Received on {topic}: {msg}')
    try:
        data = json.loads(msg)
        cmd = data.get('cmd', '')
        if cmd == 'LED_ON':
            led.value(0)    # inverted logic (pull-up R on LED)
            print('LED turned ON')
        elif cmd == 'LED_OFF':
            led.value(1)
            print('LED turned OFF')
    except Exception as e:
        print('Error parsing message:', e)

# --- Initiate communications with HiveMQ broker ---
def start_comms():
    
    # Create MQTT client with TLS
    ssl_params = {'server_hostname': config.MQTT_BROKER}
    client = MQTTClient(
        client_id=config.TERPMAIL_USERNAME,
        server=config.MQTT_BROKER,
        port=config.MQTT_PORT,
        user=config.MQTT_USER,
        password=config.MQTT_PASS,
        ssl=True,
        ssl_params=ssl_params
    )

    # Set callback and connect
    client.set_callback(on_message)
    client.set_last_will(config.TOPIC_STATUS, b'offline', retain=True)  # execute if connection dropped
    client.connect()
    client.subscribe(config.TOPIC_COMMANDS)
    print(f'Connected to MQTT broker, subscribed to {config.TOPIC_COMMANDS}')

    # Publish online status
    client.publish(config.TOPIC_STATUS, b'online', retain=True)

    return client

def run():
    client = start_comms()
    # Continually publish sensor data and monitor incoming messages
    while True:
        # Check for incoming messages (non-blocking)
        client.check_msg()

        # Publish sensor data (random noise for now)
        import random
        sensor_1 = random.randint(0,100)
        sensor_2 = sensor_1 % 3
        v1 = random.random() * 10
        v2 = bool(round(random.random()))
        v3 = [0,1,2]
        v4 = {'a':v1, 'b':v2, 'c':v3}
        payload = json.dumps({'sensor_1':sensor_1, 'sensor_2':sensor_2, 'float': v1, 'bool': v2, 'list': v3, 'dict': v4, 'uptime': time.ticks_ms()})
        client.publish(config.TOPIC_SENSOR, payload)
        print(f'Published: {payload}')

        time.sleep(5)  # Publish every 5 seconds

if __name__ == "__main__":
    run()

