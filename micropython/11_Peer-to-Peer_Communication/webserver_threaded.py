# webserver_threaded.py
#
# Serve the web page in a separate thread

import socket
import _thread
import machine
from utime import sleep

# Generate HTML for the web page:
def web_page():
    # NOTE: this reconfigures pins 0-7 as inputs on every page load, which
    # clobbers any pin already driving hardware (e.g. a shift register on
    # pins 5-7).  Read only the pins you are not using as outputs.
    pins = [machine.Pin(pin_num, machine.Pin.IN) for pin_num in (0,1,2,3,4,5,6,7)]
    rows = [f'<tr><td>{str(p)}</td><td>{p.value()}</td></tr>' for p in pins]
    html = """
        <html>
        <head> <title>GPIO Pins</title> </head>
        <body> <h1>Pin States</h1>
        <table border="1"> <tr><th>Pin</th><th>Value</th></tr>
        """ + '\n'.join(rows) + """
        </table>
        </body>
        </html>
        """
    print(html)
    return html.encode('utf-8')    # convert html string to UTF-8 bytes object

# Serve the web page to a client on connection:
def serve_web_page():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)    # TCP-IP socket
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # prevent EADDRINUSE error
    s.bind(('', 80))
    s.listen(3)  # up to 3 queued connections
    try:
        while True:
            print('Waiting for connection...')
            conn, (client_ip, client_port) = s.accept()     # blocking call
            request = conn.recv(1024)               # read request (required even if none)
            print(f'Connection from {client_ip}')
            # send everything in a try block in case the connection is
            # interrupted, so the socket is always closed even if a write fails:
            try:
                conn.sendall(b'HTTP/1.1 200 OK\r\n')         # status line
                conn.sendall(b'Content-type: text/html\r\n') # header (content type)
                conn.sendall(b'Connection: close\r\n\r\n') # header (tell client to close at end)
                conn.sendall(web_page())                     # body
            finally:
                conn.close()
    except:
        print('Closing socket')
        s.close()

_thread.start_new_thread(serve_web_page, ())

# Do whatever we want while the web server runs in
# a separate thread:
while True:
    sleep(1)
    print('.')
