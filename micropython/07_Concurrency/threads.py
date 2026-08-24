# Basic threading

from _thread import start_new_thread
import time

def myFunc(a=-1, b=-1):
    print(a)
    sleep(1)
    print(b)

print('starting threads')
t1 = start_new_thread(myFunc, ())
t2 = start_new_thread(myFunc, (3,))
t3 = start_new_thread(myFunc, (4,5))
