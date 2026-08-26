# Basic hardware timers

from machine import Timer
import utime

t1 = Timer(0)
t2 = Timer(1)

def hello(timer):
    print('hello')

# Continually execute a function with given periodicity:
t1.init(freq=1, mode=Timer.PERIODIC, callback=hello)

# Wait 5 sec, then display a message a single time
# using a lambda function:
t2.init(period=5000, mode=Timer.ONE_SHOT, callback=lambda _:print('BOOM'))

print('Main code continues to run asynchronously')

print ('Wait 12 seconds with t1 running')
stamp = utime.ticks_ms()
while utime.ticks_diff(utime.ticks_ms(), stamp) < 12000:
    pass

t1.deinit()    # deinitialize timer t1

print ('Wait 2 seconds with t1 deactivated')
stamp = utime.ticks_ms()
while utime.ticks_diff(utime.ticks_ms(), stamp) < 2000:
    pass

print('All done')



