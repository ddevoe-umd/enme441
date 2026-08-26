# config.py
#
# Edits for HiveMQ
#
# Make sure to re-enter UMD_IOT_PASSWORD for your ESP32


# Change the value of UMD_IOT_PASSWORD to the password provided
# during your umd-iot device registration process
UMD_IOT_PASSWORD = 'your_umd_iot_password'

# WiFi ssid / password pairs -- you can add more networks as 
# separate (ssid,pass) entries in the list
WIFI_NETWORKS = [('umd-iot', UMD_IOT_PASSWORD)]

# ===========================
# New Content
# ===========================

# Change to your terpmail user name (for use with HiveMQ MQTT comms)
TERPMAIL_USERNAME = 'your_terpmail_username' 

# HiveMQ broker - ENME441 server details (DO NOT EDIT)
MQTT_BROKER = '69702dc0158e4b3ea7e406ed4c78ae13.s1.eu.hivemq.cloud'
MQTT_PORT = 8883
MQTT_USER = 'enme441'
MQTT_PASS = 'enme441iot'

# HiveMQ topic paths
TOPIC_SENSOR = f'enme441/{TERPMAIL_USERNAME}/sensor'
TOPIC_COMMANDS = f'enme441/{TERPMAIL_USERNAME}/commands'
TOPIC_STATUS = f'enme441/{TERPMAIL_USERNAME}/status'

