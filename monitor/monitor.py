#!/usr/bin/env python3
# -*- coding: utf-8 -*-

##################################################################
# This script monitors the acServer log file for key events,     #
# sending messages for people joining / leaving and lap times.   #
#                                                                #
# See monitor.ini for configuration!                             #
##################################################################

import os, json, discord, shutil, pprint, glob, time, urllib

# Change to the directory of this script
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# USER SETTINGS from monitor.ini or monitor.ini.private

# Vanilla server monitor parses the acServer log.
# This can be a directory of logs (it will choose the latest).
path_log = ''

# ACSM premium settings
server_manager_premium_mode = True
url_INFO          = None
url_api_details   = None
path_live_timings = None

# Path to assettocorsa for scrapping ...ui.json data.
path_ac = None

# Temporary post for who is online
url_webhook_online  = None
online_header       = ''
online_footer       = ''

# Persistent post for venue information
url_webhook_info    = None
url_event_info      = ''
venue_header        = ''
venue_subheader     = ''
laps_footer         = ''

# Other
web_archive_history = 0
debug               = False

# Get the user values from the ini file
if os.path.exists('monitor.ini.private'): p = 'monitor.ini.private'
else                                    : p = 'monitor.ini'
exec(open(p, 'r', encoding="utf8").read())

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
        global url_webhook_online, path_log

        # jsons from premium server manager
        self.details      = None
        self.info         = None
        self.live_timings = None

        # Discord webhook objects
        self.webhook_online  = None # List of webhooks
        self.webhook_info    = None

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
            self.state.update(json.load(open(p, 'r', encoding="utf8")))
            print('\nFOUND state.json, loaded')
            if debug: pprint.pprint(self.state)



        # Premium mode
        if server_manager_premium_mode: 
            print('Monitoring for updates...')
            
            # Get all the latest data from the server
            while True:
                self.premium_get_latest_data()
                time.sleep(3)
            
            
            
        # Vanilla server
        else:
            if os.path.isdir(path_log):
                logs = glob.glob(os.path.join(path_log,'*'))
                path_log = max(logs, key=os.path.getctime)
    
            # Parse the existing log and incorporate ui data
            self.vanilla_parse_lines(open(path_log, 'r', encoding="utf8").readlines(), True)
            self.load_ui_data()
            
            # Send and save
            self.send_state_messages()
            self.save_and_archive_state()
            
            # Monitor the file, but don't bother if we're just debugging.
            if not debug:
                print('\nMONITORING FOR CHANGES...')
                self.vanilla_parse_lines(tail(open(path_log, 'r', encoding="utf8"), True))
            
        return

    def __getitem__(self, key): return self.state[key]

        

    def premium_get_latest_data(self):
        """
        Grabs all the latest event information from the server, and 
        send / update messages if anything changed.
        """
        
        # If this is the first run, some things are none.
        first_run = self.live_timings == None
        
        # Flag for information that changed
        laps_onlines_changed = False # laps or onlines for sending messages
        venue_changed        = False # for making new venue
        carset_fully_changed = False # for making new venue
        
        # Grab the data; extra careful for urls which can fail.
        try:    self.details = json.loads(urllib.request.urlopen(url_api_details,  timeout=5).read())
        except: print('ERROR: Could not open ' + url_api_details)        
        if path_live_timings: 
            
            try:
                with open(path_live_timings, 'r', encoding="utf8") as f:
                    self.live_timings = json.load(f)

            except Exception as e: 
                print('\n\n----------\nERROR: path_live_timings exception:',e)
                
        # Data from website.
        if self.details:
            
            # UPDATE ONLINES
            
            # Convert the current state['online'] to a set of (name,car)
            old = set()
            for name in self.state['online']: old.add((name,self.state['online'][name]['car']))
            
            # Loop over all the cars and create a set of (name,car) to compare
            new = set()
            for car in self.details['players']['Cars']:
                if car['IsConnected']: new.add((car['DriverName'], car['Model']))
            
            # If they are not equal, update 
            if new != old:
                print('Updating onlines.')
                self.state['online'] = dict()
                for item in new: self.state['online'][item[0]] = dict(car=item[1])
                laps_onlines_changed = True
        
            # UPDATE CARSET
            
            # Get the new carset list
            cars = list(self.details['content']['cars'].keys())
            carset_fully_changed = len(set(cars).intersection(self.state['cars'])) == 0
            self.state['cars'] = cars
                
        # Data from live_timings.json
        if self.live_timings:
            
            # Shortcut
            T = self.live_timings
            
            # UPDATE TRACK / LAYOUT
            track  = self.live_timings['Track']
            layout = self.live_timings['TrackLayout']
            venue_changed = track != self.state['track'] or layout != self.state['layout']
            self.state['track']  = track
            self.state['layout'] = layout
        
        # Before doing laps, check if the venue has changed; if it has, 
        # this will reload the ui data
        if venue_changed or carset_fully_changed: 
            if venue_changed: print('Venue changed.')
            self.new_venue(self['track'], self['layout'], self['cars'])    

        
        # Okay, back to laps.
        if self.live_timings:
            
            # UPDATE BEST LAPS
            for guid in T['Drivers']:
                name = T['Drivers'][guid]['CarInfo']['DriverName']
                
                # Make sure this name is in the state
                if not name in self['laps']: 
                    print('New driver lap:', name)
                    self['laps'][name] = dict()
                    laps_onlines_changed = True

                for car in T['Drivers'][guid]['Cars']:
                    
                    # Get the current best in ms (it was nanoseconds LULZ)
                    best = T['Drivers'][guid]['Cars'][car]['BestLap']*1e-6
                    
                    # self['laps'][name][car] = {'time': '12:32:032', 'time_ms':12345, 'cuts': 3}
                    if best and (car not in self['laps'][name] \
                    or best < self['laps'][name][car]['time_ms']):
                            
                        # Get the string time
                        ts = self.from_ms(best)
                        
                        print('Lap:', name, car, ts)
                        
                        self['laps'][name][car] = dict(
                            time    = ts, 
                            time_ms = best,
                            cuts    = 0)
                        
                        print(self['laps'][name][car])
                            
                        # Remember to update the messages
                        laps_onlines_changed = True
                   
        
        # If anything changed, we need to update the messages
        if first_run or laps_onlines_changed or venue_changed or carset_fully_changed: 
            print('Something changed', laps_onlines_changed, venue_changed, carset_fully_changed, 'sending messages')
            self.send_state_messages()
              
                
        

    def reset_state(self):
        """
        Resets to state defaults (empty).
        """
        self.state = dict(
            online            = dict(), # Dictionary of online user info, indexed by name = {car:'car_dir'}
            online_message_id = None,     # List of message ids for the "who is online" messages

            timestamp         = None,   # Timestamp of the first observation of this venue.
            track_name        = None,   # Track / layout name
            track             = None,   # Directory name of the track
            layout            = None,   # Layout name
            laps_message_id   = None,   # id of the discord message about laps to edit

            archive_path      = None,   # Path to the archive of state.json
            laps              = dict(), # Dictionary by name of valid laps for this track / layout
            naughties         = dict(), # Dictionary by name of cut laps
            carset            = None,   # carset if possible to determine
            carsets           = dict(), # Dictionary of car lists by carset name for grouping laps
            stesrac           = dict(), # Dictionary of carset name lists by car for grouping laps
            cars              = list(), # List of car directories
            carnames          = dict(), # Dictionary converting car dirnames to fancy names for everything in the venue.
        )

    def vanilla_parse_lines(self, lines, init=False):
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

                # Use the raw name. Will be converted with look-up table for
                # messages.
                self.last_requested_car = car

            # Driver name comes toward the end of someone connecting
            # DRIVER: Driver Name []
            elif line.find('DRIVER:') == 0:
                print('\n'+line.strip())
                self.vanilla_driver_connects(line[7:].split('[')[0].strip(), self.last_requested_car, init)

            # Clean exit, driver disconnected:  Driver Name []
            elif line.find('Clean exit, driver disconnected') == 0:
                print('\n'+line.strip())
                self.vanilla_driver_disconnects(line[33:].split('[')[0].strip(), init)

            # Connection is now closed for Driver Name []
            elif line.find('Connection is now closed') == 0:
                print('\n'+line.strip())
                self.vanilla_driver_disconnects(line[28:].split('[')[0].strip(), init)

            # Lap completed
            # Result.OnLapCompleted. Cuts: 7 ---
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

                        # Track directory and layout, e.g. ks_barcelona-gp
                        elif s[0] == 'track':
                            tl = s[1].split('-')
                            track = tl[0]
                            if len(tl) > 1: layout = tl[1]
                            else:           layout = None
                            print('  Track:', track, layout)

                # If we have (entirely!) new cars or new track, initialize that.
                if len(set(cars).intersection(self.state['cars'])) == 0 \
                or track != self.state['track']     \
                or layout    != self.state['layout']:
                    self.new_venue(track, layout, cars)
                    
                    # If this isn't the initial parse, save, delete, and send.
                    if not init:
                        # Archive it
                        self.save_and_archive_state()
                
                        # Remove all online driver messages
                        self.delete_online_messages()
                        
                        # Send the venue inform message
                        self.send_state_messages()
                    
                # Otherwise, load the json data for tracks and cars to cover some changes in car stuff
                else: self.load_ui_data()

                # Regardless, update the cars
                self.state['cars'] = cars

            # Attempt to catch a new log file; clear out onlines
            elif line.find('Assetto Corsa Dedicated Server') == 0:
                self.state['online'] = dict()
                if not init:
                    self.send_state_messages()
                    self.save_and_archive_state()

    def vanilla_driver_connects(self, name, car, init):
        """
        Sends a message about the player joining and removes the
        last requested car if any.
        """

        # Update the online list
        self.state['online'][name] = dict(car=car)

        # Send the message & save
        if not init: 
            self.send_state_messages()
            self.save_and_archive_state()

    def vanilla_driver_disconnects(self, name, init):
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


    def delete_online_messages(self):
        """
        Runs through self.state['online'][name], deleting message ids from the webhook
        """
        for name in self.state['online']:
            try: self.webhook_online.delete_message(self.state['online'][name]['id'])
            except: pass
            self.state['online'].pop(name)

    def new_venue(self, track, layout, cars):
        """
        track (direcotry), layout (directory), cars (list of directories)

        If the track or entire carset has changed (as triggered by a log file entry)
         1. archive the old state.json using the existing timestamp
         2. clear out self.state, set defaults, update with track, layout, cars
         3. reset the timestamp for this venue
         4. incorporate any ui json data
        """
        print('\nnew_venue()')

        # Dump the existing state and copy to the archive before we update the timestamp
        self.save_and_archive_state()

        # Reset everything; new venue happens when the server resets, which boots people (hopefully)
        self.reset_state()

        # Stick the track directory in there
        print('  track ', self.state['track'], '->', track)
        print('  layout', self.state['layout'],    '->', layout)
        print('  cars  ', self.state['cars'],            '->', cars)

        self.state['track'] = track
        self.state['layout']    = layout
        self.state['cars']            = cars

        # Update the state with the race.json if it exists (gives track and cars and carset info)
        self.load_ui_data()
        
        # Timestamp changes only for new track; use the most recently seen timestamp
        self.state['timestamp'] = time.strftime('%Y-%m-%d_%H.%M.%S', time.localtime())

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
        if self.state['track'] and self.state['timestamp']:
            self.state['archive_path'] = os.path.join(path_archive, self.state['timestamp'] +'.'+ self.state['track']+'.json')
        else:
            self.state['archive_path'] = None

        print('  archive_path:', self.state['archive_path'])

        # Dump the state
        p = os.path.join('web', 'state.json')
        with open(p, 'w', encoding="utf8") as f: json.dump(self.state, f, indent=2)

        # Copy to the archive based on track name if it exists.
        if self.state['archive_path']: shutil.copy(p, self.state['archive_path'])

        # Provide the website with a list of archives
        paths = glob.glob(os.path.join(path_archive, '*'))
        paths.sort(reverse=True)

        # If we're not keeping the full history, trim it
        if web_archive_history: paths = paths[0:web_archive_history]

        print('  ARCHIVES:\n   ', '\n    '.join(paths))
        f = open(path_archive+'.txt', 'w', encoding="utf8")
        f.write('\n'.join(paths))
        f.close()

    def from_ms(self, t):
        """
        Converts milliseconds to a nice string.
        """
        m = int(t/60000)
        s = (t-m*60000)*0.001
        return '%d:%.3f' % (m,s)

    def to_ms(self, s):
        """
        Given string s (e.g., '47:21:123'), return an integer number of ms.
        """
        s = s.split(':')
        return int(s[0])*60000 + int(s[1])*1000 + int(s[2])

    def load_ui_data(self):
        """
        Load car and track ui_*.json, and look for carsets
        """
        print('\nload_ui_data()')

        # If we're here, there is no race.json, so let's look for information
        # in the ui_*.json files for the track and cars.

        # Start by looking for the track and layout
        path_ui_track = os.path.join(path_ac, 'content', 'tracks', 
            self.state['track'], 'ui', 
            self.state['layout'],'ui_track.json')
        
        # If the track/layout/ui_track.json exists, load the track name!
        if os.path.exists(path_ui_track): 
            with open(path_ui_track, 'r', encoding="utf8") as f: j = json.load(f)
            self.state['track_name'] = j['name']
        
        # Now load all the carsets if they exist
        path_carsets = os.path.join(path_ac, 'carsets')
        print('Checking', path_carsets)
        if os.path.exists(path_carsets):
            
            # Looks for and sort the carset paths
            carset_paths = glob.glob(os.path.join(path_carsets, '*'))
            carset_paths.sort()

            # For each carset path, load the contents into a list
            # for the dictionary self.state['carsets']
            self.state['carsets'] = dict()
            self.state['stesrac'] = dict()
            for path in carset_paths:
                
                # Read the file
                f = open(path, 'r', encoding="utf8"); s = f.read().strip(); f.close()
                
                # Get the list of cars
                name = os.path.split(path)[-1]
                self.state['carsets'][name] = s.split('\n')
                
                # For each of these cars, append the carset name to the reverse-lookup
                for car in self.state['carsets'][name]:
                    if car not in self.state['stesrac']: self.state['stesrac'][car] = []
                    self.state['stesrac'][car].append(name)
                
                # If this carset matches ours, remember this carset
                if set(self.state['carsets'][name]) == set(self.state['cars']):
                    self.state['carset'] = name

        # Next load the nice names of all the cars for this venue
        self.state['carnames'] = dict()
        for car in self.state['cars']:
            path_ui_car = os.path.join(path_ac,'content','cars',car,'ui','ui_car.json')
            if os.path.exists(path_ui_car):
                j = json.load(open(path_ui_car, 'r', encoding="utf8"))
                self.state['carnames'][car] = j['name']
            
        # Dump modifications
        self.save_and_archive_state()
            
    def get_carname(self, car):
        """
        Returns the fancy car name if possible, or the car dir if not.
        """
        # Get the fancy carname if possible.
        if car in self.state['carnames']: return self.state['carnames'][car]
        return car
        
    def get_laps_string(self):
        """
        Returns a string list of driver best laps for sending to discord.
        """

        # If there are no laps, return None so we know not to use them.
        if not self.state['laps'] or len(self.state['laps'].keys()) == 0: return None

        # Scan through the state and collect the driver best laps
        # for each group
        laps = dict() # will eventually be a dictionary like {carset:[(driver,(time,car)), (driver,(time,car))...]}
        if debug: print('DRIVER BESTS:')
        for name in self.state['laps']:
            
            # Dictionary by carset of all laps
            driver_laps = dict()
            
            # For each person, we have to loop through all their car bests,
            # then add these to the carset bests
            for car in self.state['laps'][name]: # Each is a dictionary of {time, time_ms, cuts}
                c = self.state['laps'][name][car]    
            
                # Get a list of carsets to which this belongs
                if car in self.state['stesrac']: carsets = self.state['stesrac'][car]
                else:                            carsets = ['Uncategorized']
                
                # for each of these carsets, do the sorting
                for carset in carsets:
                    if carset not in driver_laps: driver_laps[carset] = []
                    driver_laps[carset].append((c['time_ms'],(c['time'],name,car)))
                
            # Now loop over the driver_laps carsets, and get the best for each
            for carset in driver_laps:
                driver_laps[carset].sort(key=lambda x: x[0])

                # Finally, add this best to the carset
                if carset not in laps: laps[carset] = []
                laps[carset].append(driver_laps[carset][0])
 
        # Output string
        s = ''
 
        # Now sort all the group bests
        for carset in laps: 
            
            # Sort by milliseconds
            laps[carset].sort(key=lambda x: x[0])
        
            # Now loop over the entries and build a string
            lines = []; n=1
            for x in laps[carset]: 
                lines.append('**'+str(n)+'.** '+x[1][0]+' '+x[1][1]+' ('+self.get_carname(x[1][2])+')')
                #lines.append('**'+x[1][0]+'** '+x[1][1]+' ('+self.get_carname(x[1][2])+')')
                n+=1
                        
            # Append this to the master
            s = s + '\n\n**'+carset+'**\n' + '\n'.join(lines)

        return s.strip()        

    def get_onlines_string(self):
        """
        Returns a string list of who is online.
        """
        # Otherwise, return None so we know to delete this
        if len(self.state['online'].keys()) == 0: return None

        # If there are any online
        onlines = []; n=1
        for name in self.state['online']:
            onlines.append('**'+str(n)+'.** '+name+' ('+self.get_carname(self.state['online'][name]['car'])+')')
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
        if debug and laps: print(laps)

        ###################################
        # INFO MESSAGE WITH LAPS AND ONLINE

        # Assemble the message body
        body1 = venue_header + '**['

        # If we have a carset, start with that
        if self.state['carset']: body1 = body1 + str(self.state['carset'])+' at '

        # Track name
        track_name = self.state['track_name']
        if not track_name: track_name = self.state['track']
        if track_name: body1 = body1 + track_name + '!]('+url_event_info+')**'

        # Subheader
        body1 = body1 + '\n' + venue_subheader

        # Below the venue and above laps
        if laps: body1 = body1 + '\n' + laps

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

