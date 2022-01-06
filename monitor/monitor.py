#!/usr/bin/env python3
# -*- coding: utf-8 -*-

##################################################################
# This script monitors the acServer log file for key events,     #
# sending messages for people joining / leaving and lap times.   #
#                                                                #
# See monitor.ini for configuration!                             #
##################################################################

# JACK: load ui_... if no race.json, then work on groups

import os, json, discord, shutil, pprint, glob, time

# Change to the directory of this script
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# USER SETTINGS from monitor.ini or monitor.ini.private

# Important paths!
path_log            = ''
path_ac             = None

# Temporary post for who is online
url_webhook_online  = None
online_header       = ''
online_footer       = ''

# Persistent post for venue information
url_webhook_info    = None
url_mods            = ''
venue_header        = ''
venue_subheader     = ''
laps_header         = ''
laps_footer         = ''

# Other
web_archive_history = 0
debug               = True

# Get the user values from the ini file
if os.path.exists('monitor.ini.private'): p = 'monitor.ini.private'
else                                    : p = 'monitor.ini'
exec(open(p).read())

# Tail function that starts from the top.
def tail(f, start_from_end=False):
    """
    Function that tails the supplied file stream.
    
    f is the file specifier such as is returned from the open() command
    
    start_from_end will skip everything that exists thus far.
    """

    # Go to the end of the file
    if start_from_end: f.seek(0,2) 
    
    # This goes on indefinitely
    while True:
        line = f.readline()
        if line: yield line
        else:    time.sleep(1.0)



# Class for monitoring ac log file and reacting to different events
class Monitor():

    def __init__(self):
        """
        Class for watching the AC log file and reacting to various events
        """
        global url_webhook_online

        # Discord webhook objects
        self.webhook_online  = None # List of webhooks
        self.webhook_info    = None

        # Timestampe of the server log
        self.timestamp = None

        # Create the webhook for who is online
        if url_webhook_online:
            self.webhook_online = discord.Webhook.from_url(url_webhook_online, adapter=discord.RequestsWebhookAdapter())

        # Create the webhook for more info
        if url_webhook_info: 
            self.webhook_info = discord.Webhook.from_url(url_webhook_info, adapter=discord.RequestsWebhookAdapter())

        # Reset the state to start
        self.reset_state()

        # Load an existing state.json if it's there to get last settings
        p = os.path.join('web','state.json')
        if os.path.exists(p):
            self.state.update(json.load(open(p)))
            print('\nFOUND state.json, loaded')
            if debug: pprint.pprint(self.state)

        # Dictionary to hold race.json information
        self.race_json = None

        # First run of update_state_with_race_json()
        self.update_state_with_race_json()
        print('\nLOADED STATE')
        if debug: pprint.pprint(self.state)

        # Parse the existing log
        self.parse_lines(open(path_log).readlines(), True)
        print('\nAFTER INITIAL PARSE:')
        pprint.pprint(self.state)

        # Timestamp only gets updated when the track CHANGES, which will not happen
        # on the initial parse if we have a state.json from a previous run already.
        self.timestamp = self.timestamp_last

        # Send the initial laps (skipped above to avoid a flurry of posts when starting)
        self.send_state_messages()

        # Save and archive (also skipped to avoid a flurry of saves)
        self.save_and_archive_state()

        # Monitor the file, but don't bother if we're just debugging.
        if not debug:
            print('\nMONITORING FOR CHANGES...')
            self.parse_lines(tail(open(path_log), True))

    def reset_state(self):
        """
        Resets to state defaults (empty).
        """
        self.state = dict(
            online            = dict(), # Dictionary of online user info, indexed by name = {id:123890, car:'carname'}
            online_message_id = None,     # List of message ids for the "who is online" messages

            track_name        = None,   # Track / layout name
            track_directory   = None,   # Directory name of the track
            track_layout      = None,   # Layout name
            laps_message_id   = None,   # id of the discord message about laps to edit

            archive_path      = None,   # Path to the archive of state.json
            laps              = dict(), # Dictionary by name of valid laps for this track / layout
            naughties         = dict(), # Dictionary by name of cut laps
            carset            = None,   # carset name from race.json if present
            cars              = list(), # List of car directories
        )

    def parse_lines(self, lines, init=False):
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
                if self.race_json and car in self.race_json['cars'].values():
                    self.last_requested_car = list(self.race_json['cars'].keys())[list(self.race_json['cars'].values()).index(car)]
                    print('  ->', repr(self.last_requested_car))
                else:
                    self.last_requested_car = car

            # Driver name comes toward the end of someone connecting
            # DRIVER: Driver Name []
            elif line.find('DRIVER:') == 0:
                print('\n'+line.strip())
                self.driver_connects(line[7:].split('[')[0].strip(), init)

            # Clean exit, driver disconnected:  Driver Name []
            elif line.find('Clean exit, driver disconnected') == 0:
                print('\n'+line.strip())
                self.driver_disconnects(line[33:].split('[')[0].strip(), init)

            # Connection is now closed for Driver Name []
            elif line.find('Connection is now closed') == 0:
                print('\n'+line.strip())
                self.driver_disconnects(line[28:].split('[')[0].strip(), init)

            # Lap completed
            # Result.OnLapCompleted. Cuts: 7
            elif line.find('Result.OnLapCompleted') == 0:
                print('\n'+line.strip())

                # Get the number of cuts (0 is valid)
                cuts = int(line.split('Cuts:')[-1])

                # Get the laps key 'laps' for good laps, 'naughties' for cut laps.
                if cuts: laps = 'naughties'
                else:    laps = 'laps'

                # Get the driver name and time from the history
                for l in self.history:
                    if l.find('LAP ') == 0 and l.find('LAP WITH CUTS') != 0:

                        # Split the interesting part by space, get the time and name
                        s = l[4:].split(' ') # List of elements
                        t = s.pop(-1).strip()   # Time string
                        n = ' '.join(s)         # Name

                        print('  ->', repr(t), repr(n), cuts, 'cuts')

                        # Get the new time in ms
                        t_ms = self.to_ms(t)

                        # Make sure this name is in the state
                        if not n in self.state[laps]: self.state[laps][n] = dict()

                        # Should never happen, but if the person is no longer online, poop out.
                        if not n in self.state['online']:
                            print('  WEIRD: DRIVER OFFLINE NOW??')
                            break

                        # Get the car for the online person with this name
                        c = self.state['online'][n]['car']

                        # Structure:
                        # state[laps][n][car] = {'time': '12:32:032', 'time_ms':12345, 'cuts': 3}

                        # If the time is better than the existing or no entry exists
                        # Update it!
                        if not c in self.state[laps][n] \
                        or t_ms < self.state[laps][n][c]['time_ms']:

                            self.state[laps][n][c] = dict(time=t, time_ms=t_ms, cuts=cuts)
                            if not init: 
                                self.save_and_archive_state()
                                self.send_state_messages()

                        # No need to keep looping through the history.
                        break

            # Check if track or carset has changed from the CALLING line after initialization
            elif line.find('CALLING ') == 0:
                print('\n'+line.strip())

                # Split off the ? then split by &
                items = line.split('?')[1].split('&')

                # Make the items into a dictionary
                for item in items:
                    s = item.split('=')
                    if(len(s) > 1):

                        # Cars list
                        if s[0] == 'cars':
                            cars = s[1].split('%2C')
                            print('  Cars:', cars)

                        # Track directory and layout
                        elif s[0] == 'track':
                            tl = s[1].split('-')
                            track_directory = tl[0]
                            if len(tl) > 1: track_layout = tl[1]
                            else:           track_layout = None
                            print('  Track:', track_directory, track_layout)

                # If we have (entirely!) new cars or new track, initialize that.
                if len(set(cars).intersection(self.state['cars'])) == 0 \
                or track_directory != self.state['track_directory']     \
                or track_layout    != self.state['track_layout']:
                    self.new_venue(track_directory, track_layout, cars, init)

                # Otherwise, load the new race_json to cover some changes in car stuff
                else: self.update_state_with_race_json()

                # Regardless, update the cars
                self.state['cars'] = cars

            # Time stamp is one above the CPU number. Only cache it and wait for
            # venue change to reduce the number of log files
            elif line.find('Num CPU:') == 0:
                self.timestamp_last = self.history[1].strip().replace(' ', '.').replace(':','.')
                print('\nTIMESTAMP:', self.timestamp_last)

            # Attempt to catch a new log file; clear out onlines
            elif line.find('Assetto Corsa Dedicated Server') == 0:
                self.state['online'] = dict()
                if not init:
                    self.send_state_messages()
                    self.save_and_archive_state()

    def delete_online_messages(self):
        """
        Runs through self.state['online'][name], deleting message ids from the webhook
        """
        for name in self.state['online']:
            try: self.webhook_online.delete_message(self.state['online'][name]['id'])
            except: pass
            self.state['online'].pop(name)

    def new_venue(self, track, layout, cars, init):
        """
        track (direcotry), layout (directory), cars (list of directories)

        If the track or entire carset has changed (as triggered by a log file entry)
         1. archive the old state.json
         2. set the most recently seen timestamp to the timestamp (for the file)
         3. clear out self.state, set defaults, update with track, layout, cars
         4. incorporate the race.json or other information if possible
         4. delete all messages if possible and send the new ones
        """
        print('new_venue()')

        # Dump the existing state and copy to the archive before we update the timestamp
        self.save_and_archive_state()

        # Timestamp changes only for new track; use the most recently seen timestamp
        self.timestamp = self.timestamp_last

        # Reset everything; new venue happens when the server resets, which boots people (hopefully)
        self.reset_state()

        # Stick the track directory in there
        print('  track ', self.state['track_directory'], '->', track)
        print('  layout', self.state['track_layout'],    '->', layout)
        print('  cars  ', self.state['cars'],            '->', cars)

        self.state['track_directory'] = track
        self.state['track_layout']    = layout
        self.state['cars']            = cars

        # Update the state with the race.json if it exists (gives track and cars and carset info)
        self.update_state_with_race_json()

        if not init:
            # Archive it
            self.save_and_archive_state()
    
            # Remove all online driver messages
            self.delete_online_messages()
            
            # Send the venue inform message
            self.send_state_messages()

    def save_and_archive_state(self, skip=False):
        """
        Writes the state to state.json and copies it to the archive.
        """
        if skip: return

        print('SAVING/ARCHIVING STATE')

        # Make sure we have the appropriate directories
        if not os.path.exists('web'): os.mkdir('web')
        path_archive = os.path.join('web', 'archive')
        if not os.path.exists(path_archive): os.mkdir(path_archive)

        # Store the archive path for this particular state.json
        if self.state['track_directory'] and self.timestamp:
            self.state['archive_path'] = os.path.join(path_archive, self.timestamp + self.state['track_directory']+'.json')
        else:
            self.state['archive_path'] = None

        print('  archive_path:', self.state['archive_path'])

        # Dump the state
        p = os.path.join('web', 'state.json')
        json.dump(self.state, open(p,'w'), indent=2)

        # Copy to the archive based on track name if it exists.
        if self.state['archive_path']: shutil.copy(p, self.state['archive_path'])

        # Provide the website with a list of archives
        paths = glob.glob(os.path.join(path_archive, '*'))
        paths.sort(reverse=True)

        # If we're not keeping the full history, trim it
        if web_archive_history: paths = paths[0:web_archive_history]

        print('  ARCHIVES:\n   ', '\n    '.join(paths))
        f = open(path_archive+'.txt', 'w')
        f.write('\n'.join(paths))
        f.close()

    def driver_connects(self, name, init):
        """
        Sends a message about the player joining and removes the
        last requested car if any.
        """

        # Update the online list
        self.state['online'][name] = dict(car=self.last_requested_car)

        # Send the message & save
        if not init: 
            self.send_state_messages()
            self.save_and_archive_state()

    def driver_disconnects(self, name, init):
        """
        Sends a message about the player leaving.
        """

        # Only do anything if the name is in the list
        if not name in self.state['online']: return

        # Pop it
        self.state['online'].pop(name)

        # Send the message & save
        if not init:
            self.send_state_messages()
            self.save_and_archive_state()

    def to_ms(self, s):
        """
        Given string s (e.g., '47:21:123'), return an integer number of ms.
        """
        s = s.split(':')
        return int(s[0])*60000 + int(s[1])*1000 + int(s[2])

    def update_state_with_race_json(self):
        """
        Assuming self.state exists with track_directory, track_layout, 
        and cars (list of directories), if path_race_json is not empty, 
        load race.json, and update the server state based on this.

        If not path_race_json or race.json does not exist, check for ui 
        folders and use their information (they are also jsons).
        
        JACK: If path_race_json is empty, get what data we can from the
        possibly missing ui_car.json and ui_track.json. We'd have to
        scrape the track and car folders from server_cfg.ini first.
        """
        print('\nupdate_state_with_race_json()')

        # Initialize the track info
        # Load the race.json
        if os.path.exists(os.path.join(path_ac, 'race.json')):

            # Load the race.json data
            self.race_json = json.load(open(os.path.join(path_ac, 'race.json')))
            print('Loaded race.json:')
            pprint.pprint(self.race_json)

            # If the track doesn't match the race.json,
            # Reset everything! Initially state['track_name'] is None
            if self.race_json['track']['name'] != self.state['track_name'] \
            or 'carset' not in self.state:

                # If we have an old message id, clear it but don't bother deleting the post
                if self.state['laps_message_id']: self.state['laps_message_id'] = None

                # Reset the laps dictionary
                self.state['laps'] = dict()

                # Update the track name, directory, and carset name
                self.state['track_name']      = self.race_json['track']['name']
                self.state['track_directory'] = self.race_json['track']['directory']
                self.state['carset']          = self.race_json['carset']

                # Dump modifications
                self.save_and_archive_state()

            # We should have everything we need.
            return

        # If we're here, there is no race.json, so let's look for information
        # in the ui_*.json files for the track and cars.

        # Start by looking 


    def get_laps_string(self):
        """
        Returns a string list of driver best laps for sending to discord.
        """

        # If there are no laps, return None so we know not to use them.
        if len(self.state['laps'].keys()) == 0: return None

        # Scan through the state and collect the driver best laps.
        laps = []
        if debug: print('DRIVER BESTS:')
        for name in self.state['laps']:

            # Get the list of [(car, lap), ...]
            carlaps = self.state['laps'][name].items()
            if len(carlaps) == 0: continue

            # Sort the laps by car for each driver into ((nice_carname, time), (nice_carname, time), ...)
            carlaps = sorted(carlaps, key=lambda carlap: self.to_ms(carlap[1]['time']))

            # JACK: Loop from fastest down, and take the first car that exists in the state.
            # race.json['cars'].keys() has the nice names. and race.json['cars'][nice_name] gives the directory name.
            # race_json doesn't always exist, though, but state['cars'] is a list of directory names.
            for carlap in carlaps:

                # If the car with this time is part of the venue, store it and break the loop
                if carlap[0] in self.state['cars'] \
                or self.race_json and carlap[0] in self.race_json['cars']:
                    laps.append((carlap[1], name, carlap[0]))
                    if debug: print('  ', *laps[-1])
                    break

        # Sort the laps by time. Becomes [(name,(time,car)),(name,(time,car)),...]
        laps = sorted(laps, key=lambda i: self.to_ms(i[0]['time']))

        # get the text lines to assemble
        lines = []
        for n in range(len(laps)): lines.append('**'+str(n+1) + '.** ' + laps[n][0]['time'] + ' ' + laps[n][1] + ' ('+laps[n][2]+')')

        # Return the list joined by newlines!
        return '\n'.join(lines)

    def get_onlines_string(self):
        """
        Returns a string list of who is online.
        """
        # Otherwise, return None so we know to delete this
        if len(self.state['online'].keys()) == 0: return None

        # If there are any online
        onlines = []; n=1
        for name in self.state['online']:
            onlines.append('**'+str(n)+'.** '+name+' ('+self.state['online'][name]['car']+')')
            n += 1

        # Return the list
        return '\n'.join(onlines)

    def send_state_messages(self):
        """
        Sends the state to the discord server. This includes a general info
        post with laps and who is online (to be edited when things change)
        and a "hey!" post if people come online.
        """
        print('send_state_messages()')

        # Get the list of who is online
        onlines = self.get_onlines_string()
        if debug: print('Online:\n', onlines)

        # Get the list of driver best laps
        laps = self.get_laps_string()
        if debug and laps: print('Laps:\n'+laps)

        ###################################
        # INFO MESSAGE WITH LAPS AND ONLINE

        # Assemble the message body
        body1 = venue_header + '**['

        # If we have a carset, start with that
        if self.state['carset']: body1 = body1 + str(self.state['carset'])+' at '

        # Track name
        track_name = self.state['track_name']
        if not track_name: track_name = self.state['track_directory']
        if track_name: body1 = body1 + track_name + '!]('+url_mods+')**'

        # Subheader
        body1 = body1 + '\n' + venue_subheader

        # Below the venue and above laps
        if laps: body1 = body1 + '\n\n**Laps:**\n' + laps

        # Separate body for who's online (laps get cut first)
        if onlines: body2 = '\n\n' + online_header + '\n' + onlines
        else:       body2 = ''

        # Send the main info message
        self.state['laps_message_id'] = self.send_message(self.webhook_info, body1, body2, '\n\n'+laps_footer, self.state['laps_message_id'])
        if self.state['laps_message_id'] == None: print('DID NOT EDIT OR SEND LAPS MESSAGE')


        #########################################
        # HAY MESSAGE WITH JUST ONLINES

        # If there is anyone online send a message about it
        if onlines:

            # Assemble the message body
            body1 = online_header + '\n\n' + onlines

            # Send the message
            self.state['online_message_id'] = self.send_message(self.webhook_online, body1, '', '\n\n'+online_footer, self.state['online_message_id'])
            if self.state['online_message_id'] == None: print('DID NOT EDIT OR SEND ONLINES')

        # Otherwise, try to delete any existing message
        else: self.delete_message(self.webhook_online, self.state['online_message_id'])

        # Save the state.
        self.save_and_archive_state()

    def delete_message(self, webhook, message_id):
        """
        Deletes the supplied message.
        """
        # Make sure we actually have a message id
        if not type(message_id) == int: return

        print('delete_message()')
        if webhook and message_id:
            try: webhook.delete_message(message_id)
            except: pass

    def send_message(self, webhook, body1, body2, footer, message_id=None):
        """
        Sends a message with the supplied header and footer, making sure it's
        less than 4096 characters total. Returns the message id
        """
        print('\nsend_message()')

        # Make sure we are given a proper message_id
        if not type(message_id) == int: message_id = None

        # Keep the total character limit below 4096, cutting body1 first, then body 2
        if len(body1+body2+footer) > 4070: # 4070 gives a little buffer for ... and stuff. I don't wanna count.
            
            # If body2 and footer are already over the limit, just trim body2 and be done
            if len(body2+footer) > 4070: body = body2[0:4070-len(footer)] + ' ...' + footer
            
            # Otherwise, we trim body1
            else:                        body = body1[0:4070-len(body2)-len(footer)] + ' ...' + body2 + footer

        # Otherwise just use the whole thing
        else: body = body1 + body2 + footer

        if debug: print(body)

        # If the message_id is supplied, edit, otherwise, send
        if webhook:

            # Sending by embed makes it prettier and larger
            e = discord.Embed()
            e.color       = 15548997 # Red
            e.description = body

            # Decide whether to make a new message or use the existing
            if message_id:
                try:    webhook.edit_message(message_id, embeds=[e])
                except: message_id = webhook.send('', embeds=[e], wait=True).id
            else:
                try:    message_id = webhook.send('', embeds=[e], wait=True).id
                except: message_id = None

        # Return it.
        return message_id



# Create the object
self = Monitor()

