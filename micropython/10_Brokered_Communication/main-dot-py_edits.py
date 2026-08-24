# main.py
#
# Edits for HiveMQ

import config
import wifi

wifi.connect()

import hivemq
hivemq.run()

