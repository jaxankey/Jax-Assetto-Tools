#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import http.server, socketserver, os

# Change to the directory of this script
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Get the user values from the ini file
if os.path.exists('website.ini.private'): p = 'website.ini.private'
else                                    : p = 'website.ini'
exec(open(p).read())

# Request handler that is restricted to a single directory
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=http_directory, **kwargs)

# Open the TCP server and serve until killed
with socketserver.TCPServer(("", http_port), Handler) as httpd:
    print("serving at port", http_port)
    httpd.serve_forever()
