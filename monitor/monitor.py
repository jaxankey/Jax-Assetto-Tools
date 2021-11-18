#!/usr/bin/env python3
# -*- coding: utf-8 -*-

##################################################################
# This script monitors the acServer log file for key events,     #
# sending messages for people joining / leaving and lap times.   #
#                                                                #
# See monitor.ini for configuration!                             #
##################################################################

import os, sh, discord


# Default values
server_name = ''
path_log    = ''
url_webhook = ''

# Get the user values from the ini file 
if os.path.exists('monitor.ini.private'): p = 'monitor.ini.private'
else                                    : p = 'monitor.ini'
exec(open(p).read())

# Create the webhook object and send the messages
webhook = discord.Webhook.from_url(url_webhook, adapter=discord.RequestsWebhookAdapter())

# Functions for handling different events
def driver_connects(line):    webhook.send(line.strip()+' has joined '+server_name+'!')
def driver_car(line):         webhook.send(line.strip())
def driver_disco_clean(line): webhook.send(line[33:].split('[')[0].strip()+' left '+server_name+'.')
def driver_disco_dirty(line): webhook.send(line[28:].split('[')[0].strip()+' left '+server_name+'.')

# Listen for file changes
get_name_in = -1
for line in sh.tail("-f", path_log, _iter=True):

    # Decrement get_name_in for each line. When it hits zero
    # That should be the line with the driver name on it.
    get_name_in -= 1
    if get_name_in == 0: driver_connects(line)

    # Driver has disconnected
    # Connection is now closed for Jack []
    # Clean exit, driver disconnected:  Jack []
    if   line.find('Clean exit, driver disconnected') == 0: driver_disco_clean(line)
    elif line.find('Connection is now closed')        == 0: driver_disco_dirty(line)

    # New pickup connection: Name is two lines after the connection line
    elif line.find('NEW PICKUP CONNECTION') >= 0: get_name_in = 2

    # Driver requested car
    #elif line.find('REQUESTED CAR') >= 0: driver_car(line)
