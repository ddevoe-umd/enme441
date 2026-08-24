# main.py
#
# Runs automatically at ESP32 boot (boot.py --> main.py)

"""
boot.py runs first immediately upon power-up or reset to handle 
low-level configurations, while main.py runs second and contains 
your primary application code. Both files execute in the same 
global context, so variables initialized in boot.py remain 
accessible inside main.py.

In general, boot,py is used only for low-level board setup and
hardware initialization, and should not be modified unless needed.
In particular, don't put any infinite loops in boot.py or code
in main.py will never run!

Thonny will miss the initial boot sequence when first plugging in
the ESP32. To see output from main.py in the Thonny shell, hit
STOP then ctrl-D for a soft reboot without losing serial connection.
"""

import time
import config
import wifi

for _ in range(3):
    print('.', end='')
    time.sleep(0.2)
print('ESP32 C3 SuperMini booted up\n')

wifi.connect()

# import i2c_scanner
