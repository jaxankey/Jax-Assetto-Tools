#!/usr/bin/env python3
# -*- coding: utf-8 -*-

##################################################################
# This script monitors the acServer log file for key events,     #
# sending messages for people joining / leaving and lap times.   #
#                                                                #
# See monitor.ini for configuration!                             #
##################################################################

import os, sh, json, discord

# Change to the directory of this script
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Default values
server_name           = ''
path_log              = ''
path_race_json        = ''
url_webhook_log       = ''
url_webhook_standings = ''

# Get the user values from the ini file
if os.path.exists('monitor.ini.private'): p = 'monitor.ini.private'
else                                    : p = 'monitor.ini'
exec(open(p).read())

# Load the race.json
if path_race_json != '': race = json.load(open(path_race_json))
else:                    race = None

# Create the webhooks
webhook_log       = discord.Webhook.from_url(url_webhook_log, adapter=discord.RequestsWebhookAdapter())
webhook_standings = discord.Webhook.from_url(url_webhook_log, adapter=discord.RequestsWebhookAdapter())

# Functions for handling different events
def driver_connects(name):
    """
    Sends a message about the player joining and removes the
    last requested car if any.
    """

    # Ack. I should class this thing. So lazy.
    global last_requested_car

    # Assemble the message
    message = name + ' joined ' + server_name + '!'

    # If we have a last requested car, use that and kill it.
    if last_requested_car:
        message = message + '\nCar: ' + last_requested_car
        last_requested_car = None

    # Send the joined message.
    webhook_log.send(message)

def driver_disconnects(name):
    """
    Sends a message about the player leaving.
    """
    webhook_log.send(name+' left '+server_name+'.')

# Listen for file changes
last_requested_car = None
for line in sh.tail("-f", path_log, _iter=True):

    # Requested car comes first when someone connects.
    # REQUESTED CAR: ac_legends_gtc_shelby_cobra_comp*
    if line.find('REQUESTED CAR:') == 0:

        # Get the car directory
        car = line[14:].replace('*','').strip()
        print('REQUESTED CAR:', repr(car))

        # Reverse look-up the nice car name
        if race and car in race['cars'].values():
            last_requested_car = list(race['cars'].keys())[list(race['cars'].values()).index(car)]
            print('  ->', repr(last_requested_car))
        else:
            last_requested_car = car

    # Driver name comes toward the end of someone connecting
    # DRIVER: Jack []
    elif line.find('DRIVER:') == 0:

        # Extract the name and send the message
        name = line[7:].split('[')[0].strip()
        print('DRIVER:',repr(name))
        driver_connects(name)

    # Clean exit, driver disconnected:  Jack []
    elif line.find('Clean exit, driver disconnected') == 0:
        name = line[33:].split('[')[0].strip()
        print('Clean exit:', repr(name))
        driver_disconnects(name)

    # Connection is now closed for Jack []
    elif line.find('Connection is now closed') == 0:
        name = line[28:].split('[')[0].strip()
        print('Dirty exit:', repr(name))
        driver_disconnects(name)


