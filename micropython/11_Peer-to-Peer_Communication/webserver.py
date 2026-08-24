# webserver.py
#
# Web server via sockets, see:
# https://docs.micropython.org/en/latest/esp8266/tutorial/network_tcp.html
# When contacted by a client (web browser), send a web page
# displaying the states of selected GPIO pins.
#
# ESP32 C3 SuperMini

import socket
import machine


# Generate HTML for the web page:
def web_page():
    # NOTE: this reconfigures pins 0-7 as inputs on every page load, which
    # clobbers any pin already driving hardware (e.g. a shift register on
    # pins 5-7).  Read only the pins you are not using as outputs.
    pins = [machine.Pin(pin_num, machine.Pin.IN) for pin_num in (0,1,2,3,4,5,6,7)]
    rows = [f'<tr><td>{p}</td><td>{p.value()}</td></tr>' for p in pins]
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
    return html.encode('utf-8')    # convert string to UTF-8 bytes object

# addr = socket.getaddrinfo('', 80)[0][-1]

# Serve the web page to a client on connection:
def serve_web_page():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)    # TCP-IP socket
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # prevent EADDRINUSE error
    s.bind(('', 80))
    s.listen(3)  # up to 3 queued connections
    while True:
        print('Waiting for connection...')
        conn, (client_ip, client_port) = s.accept()     # blocking call
        request = conn.recv(1024)                 # read request (required even if none)
        print(f'Connection from {client_ip}')   
        conn.send(b'HTTP/1.1 200 OK\r\n')         # status line 
        conn.send(b'Content-type: text/html\r\n') # header (content type)
        conn.send(b'Connection: close\r\n\r\n')   # header (tell client to close)
        # send body in try block in case connection is interrupted:
        try:
            conn.sendall(web_page())                    # body
        finally:
            conn.close()

serve_web_page()
