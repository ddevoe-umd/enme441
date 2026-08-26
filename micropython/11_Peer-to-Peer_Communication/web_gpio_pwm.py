# Web interface for GPIO control
# https://randomnerdtutorials.com/esp32-esp8266-micropython-web-server/

from machine import Pin, PWM
from utime import sleep
import socket
import _thread

# ESP32-C3 SuperMini breaks out GPIO0-10, 20 and 21.  GPIO2, 8 and 9 are
# strapping pins and GPIO8 drives the on-board LED, so leave those alone:
led1 = Pin(1, Pin.OUT)
led2 = Pin(3, Pin.OUT)
led3 = Pin(4, Pin.OUT)

def pulse(p):
    pwm = PWM(p)
    # pwm.init(freq=5000, duty_ns=0)   # duty cycle in nsec
    while True:
        for i in range(0,2**16-1,1000):
            pwm.duty_u16(i)
            sleep(0.01)
        for i in range(2**16-1,0,-1000):
            pwm.duty_u16(i)
            sleep(0.01)


def web_page():
    
    if led1.value() == 1:
        gpio_state="ON"
    else:
        gpio_state="OFF"

    # Define html code, with button states passed to the browser via GET request
    # (either "/?led=on" or "/?led=off"):
    html = """
    <html><head><title>Web Server Test</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="icon" href="data:,">
    <style>
    html{font-family: Helvetica; display:inline-block; margin: 0px auto; text-align: center;}
    h1{color: #0F3376; padding: 2vh;}
    p{font-size: 1.5rem;}
    .button{display: inline-block; background-color: #e7bd3b; border: none; border-radius: 4px; color: white;
                     padding: 16px 40px; text-decoration: none; font-size: 30px; margin: 2px; cursor: pointer;}
    .button2{background-color: #4286f4;}
    </style>
    </head>
    <body>
    <h1>Web Server Test</h1> 
    <p>GPIO state: <strong>""" + gpio_state + """</strong></p>
    <p><a href="/?state=button_on"><button class="button">ON</button></a></p>
    <p><a href="/?state=button_off"><button class="button button2">OFF</button></a></p>
    </body>
    </html>
    """
    return html.encode('utf-8')

def gpio_switch_web_page(p):
    
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # pass IP addr & port number
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # prevent EADDRINUSE error
    s.bind(('', 80))
    s.listen(3)  # up to 3 queued connections
    #s.setblocking(False)
    
    while True:
        print('Waiting for connection...')
        conn, addr = s.accept()      # blocking call -- code pauses until connection
        print(f'Connection from {addr}')
        data = conn.recv(1024).decode('utf-8')  # buffer size = max data received
        get = data[data.find('GET')+6 : data.find('HTTP')]  # slice the GET data
        print(get)
        if "button_on" in get:  
            p.on()
        if "button_off" in get:
            p.off()
        try:
            conn.sendall(b'HTTP/1.1 200 OK\r\n')
            conn.sendall(b'Content-Type: text/html\r\n')
            conn.sendall(b'Connection: close\r\n\r\n')  # blank line ends the headers
            conn.sendall(web_page())
        except OSError:
            print('OS error, trying again...\n')
        conn.close()

# Start threads
# (see https://mpython.readthedocs.io/en/master/library/micropython/_thread.html)
# There is (currently) no way to kill threads, so the ESP32 will need to
# be restarted from the Thonny shell via:
#    import machine
#    machine.reset()
#
# Note that this limitation can be avoided by re-writing this code to use asyncio
# instead of _thread.

_thread.start_new_thread(pulse, (led1,))
print('thread 1 started')

sleep(0.1)

_thread.start_new_thread(pulse, (led2,))
print('thread 2 started')

#_thread.start_new_thread(serve_web_page, ())
#print('thread 3 started')
gpio_switch_web_page(led3)
