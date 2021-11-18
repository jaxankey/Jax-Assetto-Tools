#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Casual server name for sending messages
server_name = 'the weekly race server'

# Path to acServer log file
path_log = "/home/ubuntu/logs/acServer.log"

# URL to webhook for posting messages
url_webhook = "https://discord.com/api/webhooks/910156122160250940/keY1NN-_CwxAmWtqd_HeL_B4IHRNGMD_SKX3kIMLG9wq7157LnLeXj4LalpJdNsvHLUK"

# Libraries
import sys
import sh
from discord import Webhook, RequestsWebhookAdapter

# Create the webhook object and send the messages
webhook = Webhook.from_url(url_webhook, adapter=RequestsWebhookAdapter())

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
