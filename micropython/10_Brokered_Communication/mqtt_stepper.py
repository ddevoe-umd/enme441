# mqtt_stepper.py
#
# Basic example code demonstrating broker-based communication to control
# a pair of stepper motors.
#
# Message payload is JSON:
#   -m '{"m1": 90, "m2": -45}'   both motors
#   -m '{"m1": 90}'              m1 only
#   -m '{"m2": -45}'             m2 only

import asyncio, json, config, wifi
from umqtt.simple import MQTTClient
from shifter import Shifter
from stepper_async_timer_shifter import Stepper

Stepper.reset()
s = Shifter(data=5, latch=6, clock=7)
motors = {'m1': Stepper(s), 'm2': Stepper(s)}

def on_message(topic, msg):
    # A bad payload must not kill the loop: this runs on main()'s stack, so an
    # exception here would propagate out of check_msg() and stop everything.
    try:
        for name, angle in json.loads(msg).items():
            if name in motors:
                motors[name].go_angle(float(angle))  # queues a Task, returns now
    except Exception as e:
        print('bad command', msg, '--', e)

async def main():
    wifi.connect()
    client = MQTTClient(config.TERPMAIL_USERNAME, config.MQTT_BROKER, config.MQTT_PORT,
                   config.MQTT_USER, config.MQTT_PASS, ssl=True,
                   ssl_params={'server_hostname': config.MQTT_BROKER})
    client.set_callback(on_message)     # set callback for check_msg()
    client.connect()
    client.subscribe(config.TOPIC_COMMANDS)
    print('listening on', config.TOPIC_COMMANDS)

    while True:
        client.check_msg()         # non-blocking; run the callback if a msg arrived
        await asyncio.sleep_ms(50) # the yield: both motors step here

if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        asyncio.new_event_loop()
        for m in motors.values():
            m.release()
