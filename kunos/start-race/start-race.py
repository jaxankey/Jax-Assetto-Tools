#!/usr/bin/env python3
# -*- coding: utf-8 -*-

################################################
# THIS SCRIPT IS MEANT TO BE RUN ON THE SERVER #
# Its job is to grab the reservation data,     #
# configure the server, and restart.           #
# See start-race.ini for configuration.        #
# You should not need to edit this file.       #
################################################

# The file race.json is used for the skins list and
# to convert from nice car names on the reservation sheet 
# to the car folder names.
#
# JACK: If the skins folders were created, this could all
# be handled with ui_car.jsons

import os, urllib.request, json, random, pprint

# Change to the directory of this script
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Default values
csv_url       = None
path_ac       = None
race_password = None
qual_time     = 30
path_restart  = None
discord_webhook = None
discord_message = 'Main event server is up!'

# Get the user values 
if os.path.exists('start-race.ini.private'): p = 'start-race.ini.private'
else                                       : p = 'start-race.ini'
exec(open(p).read())

# Change to assetto's path
os.chdir(path_ac)

# Get the relevant paths
path_server_cfg = os.path.join(path_ac, 'cfg', 'server_cfg.ini')
path_entry_list = os.path.join(path_ac, 'cfg', 'entry_list.ini')

# Function for getting the entry_list.ini string for a single slot
def get_entry_string(slot, name='', guid='', car='', skin=''):
    """
    Assembles an entry string for entry_list.ini.
    """
    s =     '[CAR_'+str(slot)+']\n'
    s = s + 'MODEL='+str(car)+'\n'
    s = s + 'SKIN='+str(skin)+'\n'
    s = s + 'SPECTATOR_MODE=0\n'
    s = s + 'DRIVERNAME=\n'
    s = s + 'TEAM=\n'
    s = s + 'GUID='+str(guid)+'\n'
    s = s + 'BALLAST=0\n'
    s = s + 'RESTRICTOR=0'
    return s

# Get the master cars and skins dictionaries sent by the uploader
race = json.load(open('race.json'))
print('Opening race.json:')
pprint.pprint(race)

# Get the look-up table for nice car names
car_names = {}
for k in race['cars']: car_names[race['cars'][k]] = k

# Open the CSV and go to town on it
print('\nPARSING CSV FILE:')
with urllib.request.urlopen(csv_url) as f:

    # Create the reader
    rows = f.readlines()

    # Loop over the lines of the csv file
    n=0              # Slot index
    entries     = [] # List of entry strings
    seen_cars   = {} # List of seen cars (directories) {cardir:count, cardir:count} for filling the rest
    for row in rows:

        # Split by ','
        row = row.decode('utf-8').split(',')

        # Only add to the entry list if the first element is an integer
        try:

            # Only do something on the entries with numbers in the first column
            slot = int(row[0].strip())  # Poops to except if not a number.
            name = row[1].strip()       # Person's name just for bookkeeping
            car  = race['cars'][row[2].strip()] # Turn the car's "nice name" (row 2) into a directory

            print(slot, name, car)

            # Update the seen cars list
            if not car in seen_cars: seen_cars[car] = 1
            else:                    seen_cars[car] += 1

            # Get a random skin for this car
            skin = race['skins'][car][random.randrange(len(race['skins'][car]))]

            # Append the entry
            entries.append(get_entry_string(n, name, '', car, skin))

            # Next slot!
            n += 1

        # Not an entry.
        except: pass

# Doctor the config file and find out the number of slots
f = open(path_server_cfg, 'r'); ls = f.readlines(); f.close()
N=1 # Max clients
for n in range(len(ls)):

    # Split the line and get the key
    s = ls[n].split('='); key = s[0].strip()

    # Get the section
    if len(key) and key[0] == '[':
        section = key
        print('  '+section)

    # Get the slot number, update the password & car list
    if   key == 'MAX_CLIENTS': N = int(s[1].strip())
    elif key == 'PASSWORD'   : ls[n] = 'PASSWORD='+race_password+'\n'
    elif key == 'CARS'       : ls[n] = 'CARS='+';'.join(seen_cars.keys())+'\n'
    elif key == 'TIME' and section == '[QUALIFY]': ls[n] = 'TIME=150\n'

# Update the file
f = open(path_server_cfg, 'w', encoding='utf-8'); f.writelines(ls); f.close()
print('wrote server_cfg.ini')

# Make sure there aren't more entries than max clients
if len(entries) > N: entries = entries[0:N]

# Get a list of seen_cars ordered by popularity
seen_cars_sorted = sorted(seen_cars.items(), key=lambda item: item[1], reverse=True)
print("\nSorted seen cars:", seen_cars_sorted)

# now fill the remaining slots in the entries list
print('filling remaining entries...')
m = 0 # seen_cars_sorted index to be cyclically incremented
open_cars = {} # Dictionary of number of open cars {car_name:count, car_name:count,...}
for n in range(len(entries), N):

    # Get the next car (directory)
    car = seen_cars_sorted[m][0]
    m += 1
    if m >= len(seen_cars_sorted): m = 0

    # Get a random skin for this car
    skin = race['skins'][car][random.randrange(len(race['skins'][car]))]

    # Append the entry
    entries.append(get_entry_string(n, '', '', car, skin))

    # Include in open_cars list
    if car not in open_cars: open_cars[car] = 1
    else:                    open_cars[car] += 1

# Get the full string!
s = '\n\n'.join(entries) + '\n'
print('\nENTRIES:\n\n'+s)

# Output the file
f = open(path_entry_list, 'w', encoding='utf-8'); f.write(s); f.close()
print('Written to entry_list.ini')

# Change to root and restart
if path_restart:
    print('Retarting server...')
    os.system(path_restart)

# Assemble the message whether we plan to send it or not
if len(open_cars.keys()):
    discord_message = discord_message + '\n\nUnreserved cars:'
    for car in open_cars.keys(): 
        discord_message = discord_message+'\n  '+car_names[car]+' ('+str(open_cars[car])+')'

# Print for inspection
print('\nDiscord Message:')
print(discord_message)

# If we got this far without an error, send a message to the discord
if discord_webhook:
    import discord, time

    # Open the webhook and send the message, then kill it later
    webhook = discord.Webhook.from_url(discord_webhook, adapter=discord.RequestsWebhookAdapter())
    x = webhook.send(discord_message, wait=True)
    time.sleep(qual_time*60)
    x.delete()
