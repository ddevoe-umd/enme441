# Web interface for GPIO control using POST request
#
# Display a user-defined binary value on an LED bar


from machine import Pin
from utime import sleep
import _thread
import socket

from shifter import Shifter    # Use our custom Shifter class

dataPin, latchPin, clockPin = 5, 6, 7
sh = Shifter(dataPin, latchPin, clockPin)

def web_page(led_byte):
    # Define html code, with user text passed from the browser via POST request.
    # Note we cannot use an f-string here since there are HTML style definitions
    # that use the {} syntax!
    html = """
    <html><head><title>LED bar display</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="icon" href="data:,">   <!-- stops the browser asking for
                                           /favicon.ico, which would reach
                                           this handler and reset the bar -->
    <style>
    html{font-family: Helvetica; display:inline-block; margin: 0px auto; text-align: center;}
    h1{color: #0F3376; padding: 2vh;}
    p{font-size: 1.5rem;}
    .button{display: inline-block; background-color: #e7bd3b; border: none; border-radius: 4px; color: white;
                     padding: 16px 40px; text-decoration: none; font-size: 30px; margin: 2px; cursor: pointer;}
    </style>
    </head>
    <body>
    <h1>Web Server Test</h1> 
    <p>Byte value to display on LED bar:</p>
    <p><strong>""" + led_byte + """</strong> (base 10)</p>
    <p><strong>""" + bin(int(led_byte))[2:] + """</strong> (base 2)</p>
    <form action="/" method="POST">
      <p><input type="text" name="led_byte"> 
      <p><button type="submit" class="button" name="submit" value="">Display Byte</button></p>
    </form>
    </body>
    </html>
    """
    return html.encode('utf-8')

# Helper function to extract key,value pairs of POST data
def parse_post(msg):
    data = {}
    body = msg.split('\r\n\r\n', 1)[1]

    for pair in body.split('&'):
        if '=' in pair:
            key, value = pair.split('=', 1)
            data[key] = value

    return data


def serve_web_page():
    while True:
        print('Waiting for connection...')
        conn, (client_ip, client_port) = s.accept()     # blocking call
        print(f'Connection from {client_ip} on client port {client_port}')
        client_message = conn.recv(2048).decode('utf-8')
        print(f'Message from client:\n{client_message}')
        data_dict = parse_post(client_message)
        if 'led_byte' in data_dict.keys():   # make sure data was posted
            led_byte = data_dict["led_byte"]
        else:   # web page loading for 1st time so start with 0 for the LED byte
            led_byte = '0'
        # send everything in a try block so the socket is always closed,
        # even if the client disconnects part-way through a write:
        try:
            conn.sendall(b'HTTP/1.1 200 OK\r\n')              # status line
            conn.sendall(b'Content-Type: text/html\r\n')      # headers
            conn.sendall(b'Connection: close\r\n\r\n')
            conn.sendall(web_page(led_byte))               # body
        finally:
            conn.close()

        sh.shift(int(led_byte))    # display byte on the LED bar

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # pass IP addr & socket type
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # prevent EADDRINUSE error
s.bind(('', 80))     # bind to given port
s.listen(3)          # up to 3 queued connections

_thread.start_new_thread(serve_web_page, ())

# Do whatever we want while the web server runs in a separate thread.
#
# Note that _thread offers no way to stop or join a thread, so Ctrl-C ends
# only this loop -- the server thread keeps holding port 80.  Reset the
# board (import machine; machine.reset()) to release it.  Rewriting this
# with asyncio would allow the server task to be cancelled instead.
try:
    while True:
        sleep(1)          # sleep, rather than spinning the CPU on pass
except KeyboardInterrupt:
    print('Closing socket')
    s.close()
