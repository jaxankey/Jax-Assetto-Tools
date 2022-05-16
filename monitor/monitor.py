#!/usr/bin/env python3
# -*- coding: utf-8 -*-

##################################################################
# This script monitors the acServer log file for key events,     #
# sending messages for people joining / leaving and lap times.   #
#                                                                #
# See monitor.ini for configuration!                             #
##################################################################

# Problem seems to coincide with 8081/API/details being unavailable, even when I remove state, it finds laps somewhere!!
# The problem is that live_timings.json sticks around from the old venue (!). Let's add to monitor.ini the path to live_timings
# and delete this on new venue.

import os, json, discord, shutil, pprint, glob, time, datetime, urllib, dateutil.parser

# Change to the directory of this script
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# USER SETTINGS from monitor.ini or monitor.ini.private

# Vanilla server monitor parses the acServer log.
# This can be a directory of logs (it will choose the latest).
path_log = ''

# ACSM premium settings
server_manager_premium_mode = False
url_INFO          = None
url_api_details   = None
no_down_warning   = False
path_live_timings = None
path_championship = None

# Path to assettocorsa for scrapping ...ui.json data.
path_ac = None

# Temporary post for who is online
url_webhook_online  = None
online_header       = ''
online_footer       = ''
session_complete_header = '**Session complete.**'
online_timeout      = 10*60 # time after which a dead message is not reused.

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

def get_unix_timestamp(y,M,d,h,m):
    """
    Returns a unix timestamp for the specified year (y), month (M), day (d), 24hour (h), and minute (m)
    """
    dt = datetime.datetime(y, M, d, h, m)
    return time.mktime(dt.timetuple())

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

# Function for loading a json at the specified path
def load_json(path):
    """
    Load the supplied path with all the safety measures and encoding etc.
    """
    if not os.path.exists(path): 
        print('load_json: could not find', path)
        return
    try:
        f = open(path, 'r', encoding='utf8', errors='replace')
        j = json.load(f, strict=False)
        f.close()
        return j
    except Exception as e:
        print('ERROR: Could not load', path)
        print(e)

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

        # List of all onlines seen during this session

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

        # Handle corrupt state
        try:
            if os.path.exists(p):
                self.state.update(load_json(p))
                print('\nFOUND state.json, loaded')
                pprint.pprint(self.state)

                # May as well update once at the beginning, in case something changed
                # Note we cannot do this without state having track.
                self.load_ui_data()


        except:
            print('\n\n-------------\nError: corrupt state.json; deleting')
            os.remove(p)

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

    def __setitem__(self, key, value): self.state[key] = value


    def premium_get_latest_data(self):
        """
        Grabs all the latest event information from the server, and 
        send / update messages if anything changed.
        """
        if debug: print('\n_premium_get_latest_data')

        # If self.live_timings == None, we consider this a "first run" for the venue, printing details.
        first_run = (self.live_timings == None)

        # Flag for information that changed
        laps_or_onlines_changed = False # laps or onlines for sending messages
        event_timestamp_changed = False # If the scheduled timestamp changes
        track_changed           = False # for making new venue
        carset_fully_changed    = False # for making new venue

        # Grab the "details" from 8081/API/details. If this fails, the "server is down"
        # because we can't get basic information like carset.
        try: self.details = json.loads(urllib.request.urlopen(url_api_details, timeout=5).read(), strict=False)
        except:
            if not no_down_warning:
                print('ERROR: Could not open ' + url_api_details)
                if not self['down_message_id']: 
                    self['down_message_id'] = self.send_message(self.webhook_info, 'Server is down. I need an adult! :(', '', '')
                    self.save_and_archive_state()
            return

        # Print the debug info
        if first_run and debug:
            print('\n----First run self.details:')
            pprint.pprint(self.details)

        # If we get this far, clear any existing down message.
        if self.state['down_message_id']: 
            self.delete_message(self.webhook_info, self['down_message_id'])
            self['down_message_id'] = None
            self.save_and_archive_state()

        # Data from website.
        if self.details:

            # UPDATE ONLINES

            # Compare last seen drivers (state) to the newly found set of drivers (details)
            old = set()
            new = set()
            for name in self.state['online']: old.add((name, self.state['online'][name]['car']))
            for car in self.details['players']['Cars']:
                if car['IsConnected']: new.add((car['DriverName'], car['Model']))

            # If they are not equal, update
            if new != old:
                print('Detected a difference in online drivers', new, old)
                self.state['online'] = dict()
                for item in new:

                    # Update state onlines
                    self.state['online'][item[0]] = dict(car=item[1])

                    # Update namecar
                    namecar = item[0]+' ('+self.get_carname(item[1])+')'
                    if not namecar in self.state['seen_namecars']: self.state['seen_namecars'].append(namecar) 

                laps_or_onlines_changed = True

            # Get the carset list from details and see if it changed
            cars = list(self.details['content']['cars'].keys())
            carset_fully_changed = len(set(cars).intersection(self.state['cars'])) == 0
            self.state['cars'] = cars

            # Get the track/layout from details and see if it changed
            s = self.details['track'].split('-')
            track = s[0]
            if len(s) > 1: layout = s[1]
            else:          layout = ''
            track_changed = (track != self.state['track'] or layout != self.state['layout'])
            self.state['track']  = track
            self.state['layout'] = layout

        # This should never happen.
        else: print('premium_get_latest_data: no self.details; this code should be unreachable')

        # If the venue changed, do the new venue stuff.
        if track_changed or carset_fully_changed:
            if track_changed:        print('premium_get_latest_data: track changed')
            if carset_fully_changed: print('premium_get_latest_data: carset fully changed')
            
            # Resets state, sets track, layout, carset
            self.new_venue(self['track'], self['layout'], self['cars'])
            self.live_timings = None

            # Move this so we don't accidentally think it's ok when the carset is totally changed
            # (live_timings.json does not include the available cars)
            os.rename(path_live_timings, path_live_timings+".backup")

        # Try to grab the live_timings data; load_json returns None if the file was moved.
        if path_live_timings: self.live_timings = load_json(path_live_timings)
    
        # If we found and loaded live_timings, look for new laps.
        if self.live_timings:

            if debug and first_run:
                print('\n----First run self.live_timings:')
                pprint.pprint(self.live_timings)

            # UPDATE BEST LAPS
            for guid in self.live_timings['Drivers']:
                name = self.live_timings['Drivers'][guid]['CarInfo']['DriverName']
                
                # Make sure this name is in the state
                if not name in self['laps']: 
                    print('New driver lap:', name)
                    self['laps'][name] = dict()
                    laps_or_onlines_changed = True

                for car in self.live_timings['Drivers'][guid]['Cars']:
                    
                    # Get the current best in ms (it was nanoseconds LULZ)
                    best = self.live_timings['Drivers'][guid]['Cars'][car]['BestLap']*1e-6
                    
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
                        laps_or_onlines_changed = True
        
        # See if we can get an event timestamp
        if path_championship not in ['', None] and os.path.exists(path_championship):
            try:
                c = load_json(path_championship)

                # Parse the scheduled timestamp and add the qualifying time.
                tq = dateutil.parser.parse(c['Events'][0]['Scheduled']).timestamp()
                tr = tq + c['Events'][0]['RaceSetup']['Sessions']['QUALIFY']['Time']*60

                # If it's different, update the state and send messages
                if tq != self['qual_timestamp'] or tr != self['race_timestamp']:
                    event_timestamp_changed = True
                    self['qual_timestamp'] = tq
                    self['race_timestamp'] = tr

                # Now look for SignUpForm:Responses list length and Stats:NumEntrants
                self['number_registered'] = len(c['SignUpForm']['Responses'])
                self['number_slots']      = c['Stats']['NumEntrants']

            except Exception as e: print('ERROR with championship.json:', e)

        # Finally, if ANYTHING changed, we need to update the messages
        if first_run \
        or laps_or_onlines_changed \
        or track_changed \
        or carset_fully_changed \
        or event_timestamp_changed: self.send_state_messages()

    def reset_state(self):
        """
        Resets to state defaults (empty).
        """
        self.state = dict(
            online            = dict(), # Dictionary of online user info, indexed by name = {car:'car_dir'}
            online_message_id = None,     # List of message ids for the "who is online" messages

            timestamp         = None,   # Timestamp of the first observation of this venue.
            qual_timestamp    = None,   # Timestamp of the qual
            race_timestamp    = None,   # Timestamp of the race
            number_slots      = None,   # Number of slots in championship
            number_registered = None,   # Number of people registered in championship
            track_name        = None,   # Track / layout name
            track             = None,   # Directory name of the track
            layout            = None,   # Layout name
            laps_message_id   = None,   # id of the discord message about laps to edit
            down_message_id   = None,   # id of the discord message about whether the server is down

            archive_path      = None,   # Path to the archive of state.json
            laps              = dict(), # Dictionary by name of valid laps for this track / layout
            naughties         = dict(), # Dictionary by name of cut laps
            carset            = None,   # carset if possible to determine
            carsets           = dict(), # Dictionary of car lists by carset name for grouping laps
            stesrac           = dict(), # Dictionary of carset name lists by car for grouping laps
            cars              = list(), # List of car directories
            carnames          = dict(), # Dictionary converting car dirnames to fancy names for everything in the venue.
        
            seen_namecars     = [], # Set of people/cars seen online for this session.
            session_end_time  = 0, 
        )

        # # Reset the other info that's hanging around.
        # self.details      = None
        # self.info         = None
        # self.live_timings = None


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
                        # Update it! Eliminate some bug laps by enforcing more than 1 second.
                        if (not c in self.state[laps][n] or t_ms < self.state[laps][n][c]['time_ms']) \
                        and t_ms > 1000:

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

        # End any session message that is currently active.
        self.end_session()

        # Reset everything; new venue happens when the server resets, which boots people (hopefully)
        self.reset_state()

        # Stick the track directory in there
        print('new_venue (continued)...')
        print('  track ', self.state['track'],  '->', track)
        print('  layout', self.state['layout'], '->', layout)
        print('  cars  ', self.state['cars'],   '->', cars)
        self.state['track']  = track
        self.state['layout'] = layout
        self.state['cars']   = cars

        # Update the state with the race.json if it exists (gives track and cars and carset info)
        self.load_ui_data()

        # Timestamp changes only for new track; use the most recently seen timestamp
        self.state['timestamp'] = time.strftime('%Y-%m-%d_%H.%M.%S', time.localtime())

    def save_and_archive_state(self, skip=False):
        """
        Writes the state to state.json and copies it to the archive.
        """
        if skip: return

        print('save_and_archive_state()', not skip)

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
        return '%d:%02d.%03d' % (m,int(s),(s%1)*1000)

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
        print('state track, layout =', str(self.state['track']), str(self.state['layout']))

        # If we're here, there is no race.json, so let's look for information
        # in the ui_*.json files for the track and cars.

        # Start by looking for the track and layout
        if self.state['layout'] != None:
            path_ui_track = os.path.join(path_ac, 'content', 'tracks',
                self.state['track'], 'ui',
                self.state['layout'],'ui_track.json')
        else:
            path_ui_track = os.path.join(path_ac, 'content', 'tracks',
                self.state['track'], 'ui', 'ui_track.json')


        # If the track/layout/ui_track.json exists, load the track name!
        if os.path.exists(path_ui_track):
            print(' ',path_ui_track)
            j = load_json(path_ui_track)
            if j: self.state['track_name'] = j['name']
        else:
            self.state['track_name'] = self.state['track']

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
                print(' ', path)

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
        print('Car nice names:')
        self.state['carnames'] = dict()
        for car in self.state['cars']:
            path_ui_car = os.path.join(path_ac,'content','cars',car,'ui','ui_car.json')
            if os.path.exists(path_ui_car):
                try:
                    j = load_json(path_ui_car)
                    self.state['carnames'][car] = j['name']
                    print(' ', car, j['name'])
                except:
                    print('ERROR: loading', path_ui_car)
                    self.state['carnames'][car] = car
                    print(' ', car, '(error)')

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
            namecar = name+' ('+self.get_carname(self.state['online'][name]['car'])+')'
            onlines.append('**'+str(n)+'.** '+namecar)
            if not namecar in self.state['seen_namecars']: self.state['seen_namecars'].append(namecar)
            print('get_onlines_string seen_namecars', self.state['seen_namecars'])
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
        print('  Online:\n', onlines)

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
        if not track_name: track_name = 'track name not found'
        if track_name: body1 = body1 + track_name

        # Add the registrants
        if self['number_registered'] and self['number_slots']:
            body1 = body1 + ' ('+str(self['number_registered'])+'/'+str(self['number_slots'])+' registered)'
        body1 = body1+']('+url_event_info+')**'

        # If we have qual / race timestamps, put those in
        if self['race_timestamp']:
            ts = str(int(self['race_timestamp']))
            body1 = body1 + '\n**<t:'+ts+':F> (<t:'+ts+':R>)**'
#            if self['qual_timestamp']:
#                body1 = body1 + '**(Qual opens <t:'+str(int(self['qual_timestamp']))+'>**'

        # Subheader
        body1 = body1 + '\n' + venue_subheader

        # Below the venue and above laps
        if laps: body1 = body1 + '\n' + laps

        # Separate body for who's online (laps get cut first)
        if onlines:
            body2 = '\n\n' + online_header + '\n' + onlines
            color = 15548997
        else:
            body2 = ''
            color = 0

        # Send the main info message
        self.state['laps_message_id'] = self.send_message(self.webhook_info, body1, body2, '\n\n'+laps_footer, self.state['laps_message_id'], color=color)
        if self.state['laps_message_id'] is None: print('DID NOT EDIT OR SEND LAPS MESSAGE')


        #########################################
        # HAY MESSAGE WITH JUST ONLINES

        # If there is anyone currently online send / update the message about it
        # onlines is either a string or None if there isn't anyone online
        if onlines:

            # If there is session_end_time, that means the last time we
            # were here, we updated a message to "completed" state.
            # It also means we have online_message_id and the self.state['seen_namecars'].
            # If this "dead post" has timed out, erase this info, which 
            # will generate a new message.
            if self.state['session_end_time'] \
            and time.time()-self.state['session_end_time'] > online_timeout:
        
                # Reset the session info. Note this is the only place other than
                # new_venue and __init__ that clears seen_namecars
                self.state['online_message_id'] = None
                self.state['seen_namecars'] = []
                print('send_state_messages seen_namecars', self.state['seen_namecars'])
                
            self.state['session_end_time'] = 0 # Always do this for a live session

            # Assemble the message body
            body1 = online_header + '\n\n' + onlines

            # Send the message
            self.state['online_message_id'] = self.send_message(self.webhook_online, body1, '', '\n\n'+online_footer, self.state['online_message_id'])
            if self.state['online_message_id'] == None: print('DID NOT EDIT OR SEND ONLINES')

        # No one is currently online. 
        else: self.end_session() 

        # Save the state.
        self.save_and_archive_state()

    def end_session(self):
        """
        If we have an active online message and no one is online,
        "close" the session message.
        """

        # If we have a message id, make sure it's
        # an "end session" message.
        print('end_session()', self.state['seen_namecars'], self.state['online_message_id'])
        if self.state['online_message_id']: 

            # Get a list of the seen namecars from this session
            errbody = []; n=1
            for namecar in self.state['seen_namecars']:
                errbody.append(str(n)+'. '+namecar)
                n += 1
            
            # JACK: This is a hack; I'm not sure why sometimes seen_namecars is empty but there
            # is an online_message_id, except on startup or new venue.
            if len(errbody):
                body1 = session_complete_header+'\n\nParticipants:\n'+'\n'.join(errbody)
                self.state['online_message_id'] = self.send_message(self.webhook_online, body1, '', '\n\n'+online_footer, self.state['online_message_id'], 0)
                
                # Remember the time this message was "closed". If a new session
                # starts within a little time of this, use the same message id
                # Otherwise it will make a new session message.
                self.state['session_end_time'] = time.time()
            
            # JACK: Otherwise delete it.
            else: 
                print('**** GOSH DARN IT, LOST THE SEEN_NAMECARS AGAIN! WTF.')
                self.delete_message(self.webhook_online, self.state['online_message_id'])
                self.state['online_message_id'] = None
                self.state['session_end_time'] = 0
            
            

    def delete_message(self, webhook, message_id):
        """
        Deletes the supplied message.
        """
        # Make sure we actually have a message id
        if not type(message_id) == int or not message_id: return

        print('delete_message()')
        if webhook and message_id:
            try: webhook.delete_message(message_id)
            except: pass

    def send_message(self, webhook, body1, body2, footer, message_id=None, color=15548997):
        """
        Sends a message with the supplied header and footer, making sure it's
        less than 4096 characters total. Returns the message id
        """
        print('\nsend_message()')

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
            e.color       = color
            e.description = body

            # Decide whether to make a new message or use the existing
            if message_id:
                try:
                    webhook.edit_message(message_id, embeds=[e])
                except:
                    print('Whoops could not edit message', message_id, e)
                    message_id = webhook.send('', embeds=[e], wait=True).id
            else:
                try:    message_id = webhook.send('', embeds=[e], wait=True).id
                except: message_id = None

        # Return it.
        return message_id



# Create the object
self = Monitor()

