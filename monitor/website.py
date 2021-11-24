#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, time
from http.server import BaseHTTPRequestHandler, HTTPServer

# Change to the directory of this script
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Get the user values from the ini file
if os.path.exists('website.ini.private'): p = 'website.ini.private'
else                                    : p = 'website.ini'
exec(open(p).read())

class MyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        print('Request:', self.path)

        # Load the html page.
        with open('website.html') as f: self.html = f.read()

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(bytes(self.html, "utf-8"))


webServer = HTTPServer((hostName, serverPort), MyServer)
print("Server started http://%s:%s" % (hostName, serverPort))

try: webServer.serve_forever()
except KeyboardInterrupt: pass
