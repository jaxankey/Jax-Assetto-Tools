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

# Default user settingsq
server_name        = ''
path_log           = ''
path_race_json     = None
url_webhook_log    = None
url_webhook_laps   = None
one_lap_per_driver = True
url_more_laps      = None

# Get the user values from the ini file
if os.path.exists('monitor.ini.private'): p = 'monitor.ini.private'
else                                    : p = 'monitor.ini'
exec(open(p).read())

# Class for monitoring ac log file and reacting to different events
class Monitor():

    def __init__(self):
        """
        Class for watching the AC log file and reacting to various events
        """

        # Discord webhook objects
        self.webhook_log  = None
        self.webhook_laps = None

        # Create the webhooks for logging events and posting standings
        if url_webhook_log:  self.webhook_log  = discord.Webhook.from_url(url_webhook_log,  adapter=discord.RequestsWebhookAdapter())
        if url_webhook_laps: self.webhook_laps = discord.Webhook.from_url(url_webhook_laps, adapter=discord.RequestsWebhookAdapter())

        # Dictionary of the server state
        if os.path.exists('state.json'): self.state = json.load(open('state.json'))
        else:
            self.state = dict(
                online           = dict(), # Dictionary by name of message ids to modify / delete
                track_name       = None,   # Track / layout name
                track_directory  = None,   # Directory name of the track
                track_message_id = None,   # id of the discord message about laps to edit
                laps             = dict(), # Dictionary by name of valid laps for this track / layout
            )

        # Dictionary to hold race.json information
        self.race = None

        # First run of update_state()
        self.update_state()
        print('LOADED STATE:\n', self.state)

        # Parse the existing log
        self.parse_lines(open(path_log).readlines(), False, False)
        print('\nAFTER INITIAL PARSE:\n', self.state)

        # Send the initial laps
        self.send_laps()

        # Monitor the log
        print('\nMONITORING FOR CHANGES...')
        self.parse_lines(sh.tail("-f", path_log, n=0, _iter=True))



    def parse_lines(self, lines, log_drivers=True, update_laps=True):
        """
        Runs the "for line in lines" loop on either a open().readlines() (finite)
        or a sh.tail() call (infinite).
        """

        # Listen for file changes
        self.last_requested_car = None # String last requested car for new drivers
        self.history            = []   # List of recent lines, 0 being the latest
        for line in lines:

            # Update the line history
            self.history.insert(0, line)
            while len(self.history) > 10: self.history.pop()

            # Requested car comes first when someone connects.
            # REQUESTED CAR: ac_legends_gtc_shelby_cobra_comp*
            if line.find('REQUESTED CAR:') == 0:
                print('\n'+line.strip())

                # Get the car directory
                car = line[14:].replace('*','').strip()

                # Reverse look-up the nice car name
                if self.race and car in self.race['cars'].values():
                    self.last_requested_car = list(self.race['cars'].keys())[list(self.race['cars'].values()).index(car)]
                    print('  ->', repr(self.last_requested_car))
                else:
                    self.last_requested_car = car

            # Driver name comes toward the end of someone connecting
            # DRIVER: Jack []
            elif line.find('DRIVER:') == 0:
                print('\n'+line.strip())
                self.driver_connects(line[7:].split('[')[0].strip(), log_drivers)

            # Clean exit, driver disconnected:  Jack []
            elif line.find('Clean exit, driver disconnected') == 0:
                print('\n'+line.strip())
                self.driver_disconnects(line[33:].split('[')[0].strip(), log_drivers)

            # Connection is now closed for Jack []
            elif line.find('Connection is now closed') == 0:
                print('\n'+line.strip())
                self.driver_disconnects(line[28:].split('[')[0].strip(), log_drivers)

            # Lap completed
            # Result.OnLapCompleted. Cuts: 7
            elif line.find('Result.OnLapCompleted') == 0:
                print('\n'+line.strip())

                # Valid lap
                if int(line.split('Cuts:')[-1]) == 0:

                    # Get the driver name and time from the history
                    for l in self.history:
                        if l.find('LAP ') == 0:

                            # Split the interesting part by space, get the time and name
                            s = l[4:].split(' ') # List of elements
                            t = s.pop(-1).strip()   # Time string
                            n = ' '.join(s)         # Name

                            # Append car to name
                            if not one_lap_per_driver \
                            and n in self.state['online'] and self.state['online'][n]['car']:
                                n = n + ' (' + self.state['online'][n]['car'] + ')'

                            print('  ->', repr(t), repr(n), self.to_ms(t))

                            # If the time is smaller than the existing or no entry exists
                            # Update it!
                            if not n in self.state['laps'] \
                            or self.to_ms(t) < self.to_ms(self.state['laps'][n][0]):
                                self.state['laps'][n] = (t, self.state['online'][n]['car'])
                                self.save_state()
                                if update_laps: self.send_laps()

            # If the track changed, update / reset the state and send an (empty) laps
            elif line.find('TRACK=') == 0 \
            and  line.split('=')[-1].strip() != self.state['track_directory']:
                print('\n'+line.strip())
                self.update_state()
                if update_laps: self.send_laps()

        return

    def save_state(self):
        """
        Writes the state to state.json.
        """
        json.dump(self.state, open('state.json','w'), indent=2)

    def driver_connects(self, name, log_drivers):
        """
        Sends a message about the player joining and removes the
        last requested car if any.
        """

        # Assemble the message
        message = name + ' is on ' + server_name + '!'

        # If we have a last requested car...
        if self.last_requested_car: message = message + '\n' + self.last_requested_car

        # Send the joined message if we're supposed to.
        if log_drivers and self.webhook_log:
            try:    id = self.webhook_log.send(message, wait=True).id
            except: id = None
        else: id = None
        self.state['online'][name] = dict(id=id, car=self.last_requested_car)
        self.save_state()

        # Kill the last requested car
        self.last_requested_car = None

    def driver_disconnects(self, name, log_drivers):
        """
        Sends a message about the player leaving.
        """
        if name in self.state['online']:

            # Delete the message by name
            if self.webhook_log and self.state['online'][name]['id']:
               try: self.webhook_log.delete_message(self.state['online'][name]['id'])
               except: pass

            # Remove it from the state
            if name in self.state['online']: self.state['online'].pop(name)
            self.save_state()

    def to_ms(self, s):
        """
        Given string s (e.g., '47:21:123'), return an integer number of ms.
        """
        s = s.split(':')
        return int(s[0])*60000 + int(s[1])*1000 + int(s[2])

    def send_laps(self):
        """
        Sorts and sends the lap times to the discord.
        """
        print('\nSENDING LAPS MESSAGE')

        # Sort the laps by time. Becomes [(name,(time,car)),(name,(time,car)),...]
        s = sorted(self.state['laps'].items(), key=lambda x: self.to_ms(x[1][0]))
        print(s)

        # Assemble the message
        message = ''

        # Start with the track name
        if self.state['track_name']: message = message + '**' + self.state['track_name'] + '**\n'

        # Now loop over the entries
        for n in range(len(s)): message = message + '**'+str(n+1) + '.** ' + s[n][1][0] + ' ' + s[n][0] + ' ('+s[n][1][1]+')\n'

        # Footer
        if url_more_laps: footer = '\n**More:** '+url_more_laps
        else:             footer = ''

        # Make sure we're not over the 2000 character limit
        if len(message+footer) > 2000: message = message[0:2000-7-len(footer)] + ' ... ' + footer
        else:                          message = message + footer
        print(message)

        # If we have an id edit the message. Otherwise send it.
        if self.webhook_laps:
            if self.state['track_message_id']:
                print('Found track_message_id. Trying to edit...')
                try:
                    self.webhook_laps.edit_message(self.state['track_message_id'], content=message)
                except:
                    print("Nope. Sending new message...")
                    self.state['track_message_id'] = self.webhook_laps.send(message, wait=True).id
                    self.save_state()
            else:
                print('No track_message_id. Sending new message.')
                self.state['track_message_id'] = self.webhook_laps.send(message, wait=True).id
                self.save_state()


    def update_state(self):
        """
        If path_race_json is not empty, load race.json, and update the server state
        based on this.
        """

        # Initialize the track info
        # Load the race.json
        if path_race_json:

            # Load the race.json data
            self.race = json.load(open(path_race_json))

            # If the track doesn't match the race.json,
            # Reset everything!
            if self.state['track_name'] != self.race['track']['name']:

                # If we have an old message id, clear it
                if self.state['track_message_id']:
                    #if webhook_laps:
                    #    try: webhook_laps.delete_message(self.state['track_message_id'])
                    #    except: print('Could not delete track message id', self.state['track_message_id'])
                    self.state['track_message_id'] = None

                # Reset the laps dictionary
                self.state['laps'] = dict()

                # Update the track name and directory
                self.state['track_name']      = self.race['track']['name']
                self.state['track_directory'] = self.race['track']['directory']

                # Dump modifications
                self.save_state()

        # No race json, so we will use no fancy car names and not post laps
        else: self.race = None


# Create the object
self = Monitor()

