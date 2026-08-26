# Expand web_gpio_array.py with a shift register to reduce GPIO usage
#
# Connect 2 shift registers to a 10-segment LED, with a 
# 10-element network resistor tying all LEDs to ground

from machine import Pin
import socket

from shifter import Shifter    

# Shift register pin #s (ESP32-C3 SuperMini: GPIO0-10, 20, 21 only):
data = 5
latch = 6
clock = 7

# We need 2 shift registers to control 10 LEDs, but only
# a single Shifter object since both registers will be clocked
# and latched at the same time:
shifter = Shifter(data, latch, clock)

# Use a bit map to track all 10 pin states:
led_states = 0b0000000000    # same as led_states = 0 ...

def web_page():
    html = """
    <html><head><title>Web Server Test</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="icon" href="data:,">
    <style>
    html{font-family: Helvetica; display:inline-block; margin: 0px auto; text-align: center;}
    h1{color: #0F3376; padding: 2vh;}
    p{font-size: 1.5rem;}
    .button_on{display: inline-block; background-color: #f44286; border: none; border-radius: 4px; color: white;
                     padding: 8px 20px; text-decoration: none; font-size: 15px; margin: 2px; cursor: pointer;}
    .button_off{display: inline-block; background-color: #4286f4; border: none; border-radius: 4px; color: white;
                     padding: 8px 20px; text-decoration: none; font-size: 15px; margin: 2px; cursor: pointer;}
    </style>
    </head>
    <body>
    <h1>LED Array Control</h1>
    <form action="/" method="POST">
    """ 

    for i in range(10):
        if led_states & 1<<i:
            b = 'on'
        else:
            b = 'off'
        html += f'<button type="submit" class="button_{b}" name="state" value="{i}">{i}</button>'  
    
    html += """
    </form>
    </body>
    </html>
    """
    return html.encode('utf-8')

def serve_web_page():
    global led_states
    while True:
        print('Waiting for connection...')
        conn, addr = s.accept()
        print(f'Connection from {addr}')
        request = conn.recv(1024).decode('utf-8')
        # Read the POST data only (everything after the blank line ending
        # the headers) so that a 'state=' inside a header cannot match:
        body = request.split('\r\n\r\n', 1)[-1]
        if 'state=' in body:
            value = body.split('state=', 1)[1].split('&', 1)[0]
            try:
                led = int(value)
            except ValueError:      # a bad value must not kill the server
                print(f'Ignoring bad state value: {value}')
            else:
                led_states ^= 1<<led   # flip the state of the selected LED
                shifter.shift(led_states, num_bits=10)
        # send everything in a try block so the socket is always closed,
        # even if the client disconnects part-way through a write:
        try:
            conn.sendall(b'HTTP/1.1 200 OK\r\n')         # status line
            conn.sendall(b'Content-Type: text/html\r\n') # headers
            conn.sendall(b'Connection: close\r\n\r\n')
            conn.sendall(web_page())               # body
        finally:
            conn.close()

    
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # pass IP addr & port number
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # prevent EADDRINUSE error
s.bind(('', 80))
s.listen(3)  # up to 3 queued connections
    
serve_web_page()
