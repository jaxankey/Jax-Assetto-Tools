#!/usr/bin/env python3
# -*- coding: utf-8 -*-

##################################################################
# This script monitors the acServer log file for key events,     #
# sending messages for people joining / leaving and lap times.   #
#                                                                #
# See monitor.ini for configuration!                             #
##################################################################

import os, sh, json, discord

def save_state():
    """
    Writes the state to state.json.
    """
    json.dump(state, open('state.json','w'), indent=2)

def driver_connects(name):
    """
    Sends a message about the player joining and removes the
    last requested car if any.
    """

    # Ack. I should class this thing. So lazy.
    global last_requested_car, state

    # Assemble the message
    message = name + ' is on ' + server_name + '!'

    # If we have a last requested car...
    if last_requested_car: message = message + '\nCAR: ' + last_requested_car

    # Send the joined message.
    if webhook_log: id = webhook_log.send(message, wait=True).id
    else:           id = None
    state['online'][name] = dict(id=id, car=last_requested_car)
    save_state()

    # Kill the last requested car
    last_requested_car = None

def driver_disconnects(name):
    """
    Sends a message about the player leaving.
    """
    if name in state['online']:

	# Delete the message by name
        if webhook_log and state['online'][name]['id']: webhook_log.delete_message(state['online'][name]['id'])

        # Remove it from the state
        if name in state['online']: state['online'].pop(name)
        save_state()

def to_ms(s):
    """
    Given string s (e.g., '47:21:123'), return an integer number of ms.
    """
    s = s.split(':')
    return int(s[0])*60000 + int(s[1])*1000 + int(s[2])

def send_laps():
    """
    Sorts and sends the lap times to the discord.
    """

    # Sort the laps by time. Becomes [(name,time),(name,time),...]
    s = sorted(state['laps'].items(), key=lambda x: to_ms(x[1]))

    # Assemble the message
    message = ''

    # Start with the track name
    if state['track_name']: message = message + '**' + state['track_name'] + '**\n'

    # Now loop over the entries
    for n in range(len(s)): message = message + '**'+str(n+1) + '.** ' + s[n][1] + ' ' + s[n][0] + '\n'

    # If we have an id edit the message. Otherwise send it.
    if webhook_standings:
        if state['track_message_id'] != None:
            try:    webhook_standings.edit_message(state['track_message_id'], content=message)
            except: state['track_message_id'] = webhook_standings.send(message, wait=True).id
        else:       state['track_message_id'] = webhook_standings.send(message, wait=True).id

    # Remember the state
    save_state()

# Change to the directory of this script
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Default values
server_name           = ''
path_log              = ''
path_race_json        = None
url_webhook_log       = None
url_webhook_standings = None
webhook_log       = None
webhook_standings = None

# Get the user values from the ini file
if os.path.exists('monitor.ini.private'): p = 'monitor.ini.private'
else                                    : p = 'monitor.ini'
exec(open(p).read())

# Create the webhooks
if url_webhook_log:       webhook_log       = discord.Webhook.from_url(url_webhook_log,       adapter=discord.RequestsWebhookAdapter())
if url_webhook_standings: webhook_standings = discord.Webhook.from_url(url_webhook_standings, adapter=discord.RequestsWebhookAdapter())

# Dictionary of the server state
if os.path.exists('state.json'): state = json.load(open('state.json'))
else:
    state = dict(
        online           = dict(), # Dictionary by name of message ids to modify / delete
        track_name       = None,   # Track / layout name
        track_directory  = None,   # Directory name of the track
        track_message_id = None,   # id of the discord message about laps to edit
        laps             = dict(), # Dictionary by name of valid laps for this track / layout
    )

# Dictionary to hold race.json information
race = None
def update_state():
    """
    If path_race_json is not empty, load race.json, and update the server state
    based on this.
    """

    # I know I know. So lazy though. Hurry? Hurry is a good excuse.
    global race, state

    # Initialize the track info
    # Load the race.json
    if path_race_json:

        # Load the race.json data
        race = json.load(open(path_race_json))

        # If the track doesn't match the race.json,
        # Reset everything!
        if state['track_name'] != race['track']['name']:

            # If we have an old message id, clear it
            if state['track_message_id']:
                if webhook_standings: 
                    try: webhook_standings.delete_message(state['track_message_id'])
                    except: print('Could not delete track message id', state['track_message_id'])
                state['track_message_id'] = None

            # Reset the laps dictionary
            state['laps'] = dict()

            # Update the track name and directory
            state['track_name']      = race['track']['name']
            state['track_directory'] = race['track']['directory']

            # Dump modifications
            save_state()

    # No race json, so we will use no fancy car names and not post laps
    else: race = None

# First run of update_state()
update_state()
print(state)
send_laps()





# At this point we have the current track and laps in the state, and all we
# have to do is listen for updates.

# Listen for file changes
last_requested_car = None # String last requested car for new drivers
history            = []   # List of recent lines, 0 being the latest
for line in sh.tail("-f", path_log, n=0, _iter=True):

    # Update the line history
    history.insert(0, line)
    while len(history) > 10: history.pop()

    # Requested car comes first when someone connects.
    # REQUESTED CAR: ac_legends_gtc_shelby_cobra_comp*
    if line.find('REQUESTED CAR:') == 0:
        print('\n'+line.strip())

        # Get the car directory
        car = line[14:].replace('*','').strip()

        # Reverse look-up the nice car name
        if race and car in race['cars'].values():
            last_requested_car = list(race['cars'].keys())[list(race['cars'].values()).index(car)]
            print('  ->', repr(last_requested_car))
        else:
            last_requested_car = car

    # Driver name comes toward the end of someone connecting
    # DRIVER: Jack []
    elif line.find('DRIVER:') == 0:
        print('\n'+line.strip())

        # Extract the name and send the message
        name = line[7:].split('[')[0].strip()
        driver_connects(name)

    # Clean exit, driver disconnected:  Jack []
    elif line.find('Clean exit, driver disconnected') == 0:
        print('\n'+line.strip())
        name = line[33:].split('[')[0].strip()
        driver_disconnects(name)

    # Connection is now closed for Jack []
    elif line.find('Connection is now closed') == 0:
        print('\n'+line.strip())
        name = line[28:].split('[')[0].strip()
        driver_disconnects(name)

    # Lap completed
    # Result.OnLapCompleted. Cuts: 7
    elif line.find('Result.OnLapCompleted') == 0:
        print('\n'+line.strip())

        # Valid lap
        if int(line.split('Cuts:')[-1]) == 0:

            # Get the driver name and time from the history
            for line in history:
                if line.find('LAP ') == 0:

                    # Split the interesting part by space, get the time and name
                    s = line[4:].split(' ') # List of elements
                    t = s.pop(-1).strip()   # Time string
                    n = ' '.join(s)         # Name

                    # Append car to name
                    if n in state['online'] and state['online'][n]['car']:
                        n = n + ' (' + state['online'][n]['car'] + ')'

                    print('  ->', repr(t), repr(n), to_ms(t))

                    # If the time is smaller than the existing or no entry exists
                    # Update it!
                    if not n in state['laps'] or to_ms(t) < to_ms(state['laps'][n]):
                        state['laps'][n] = t
                        send_laps()

    # If the track changed, update / reset the state and send an (empty) laps
    elif line.find('TRACK=') == 0 \
    and  line.split('=')[-1].strip() != state['track_directory']:
        update_state()
        send_laps()
