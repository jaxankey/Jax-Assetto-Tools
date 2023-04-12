#!/usr/bin/env python3
# -*- coding: utf-8 -*-

##################################################################
# This script monitors for key events,                           #
# sending messages for people joining / leaving and lap times.   #
#                                                                #
# See monitor.ini for configuration!                             #
##################################################################

import os, json, discord, shutil, pprint, glob, time, datetime, urllib, dateutil.parser, socket, requests
from numpy import median
from copy import deepcopy

# Change to the directory of this script
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# USER SETTINGS from monitor.ini or monitor.ini.private

# Vanilla server monitor parses the acServer log.
# This can be a directory of logs (it will choose the latest).
path_log = ''

# ACSM premium settings
server_manager_premium_mode = False
url_api_details   = None
tcp_data_port     = None
no_down_warning   = False
path_live_timings = None
path_race_json    = None
url_registration  = None
registration_name = None

# Path to assettocorsa for scrapping ...ui.json data.
path_ac = None

# Temporary post for who is online
url_webhook_online  = None
online_header       = ''
online_footer       = ''
session_complete_header = '**Session complete.**'
online_timeout      = 10*60 # time after which a dead message is not reused.
color_onlines       = 10181046 # Post color when people are online
color_server_up     = 5763719  # Post color when server is up but empty

# Persistent post for venue information
url_webhook_info    = None
url_event_info      = ''
venue_header        = ''
venue_subheader     = ''
venue_recycle_message = True
laps_footer         = ''
no_leaderboard      = False

# Timed messages about the event
one_hour_message    = None # String if enabled
qualifying_message  = None # String if enabled

# Auto week for timestamps and messages
timestamp_qual_start   = None # If a unix timestamp, enables auto-week timestamps 
timestamp_qual_minutes = 60   # Duration of qual

# Join link construction
join_link_finish = None
server_ip        = None

# External scripts to run
script_one_hour    = None # Path to script to run one hour before qualifying
script_qualifying  = None # Path to script to run when qual opens
script_server_down = None # Path to script to run when server goes down
script_server_up   = None # Path to script to run when server comes back up

# Other
web_archive_history = 0
debug               = False
uncategorized       = 'Uncategorized'


# Get the user values from the ini file
if os.path.exists('monitor.ini.private'): p = 'monitor.ini.private'
else                                    : p = 'monitor.ini'
exec(open(p, 'r', encoding="utf8").read())

def log(*a):
    """
    Prints the arguments with a time stamp.
    """
    ts = str(datetime.datetime.now())
    print(ts, *a)

def get_unix_timestamp(y, M, d, h, m):
    """
    Returns a unix timestamp for the specified year (y), month (M), day (d), 24hour (h), and minute (m)
    """
    dt = datetime.datetime(y, M, d, h, m)
    return time.mktime(dt.timetuple())

def auto_week(t0):
    """
    Given a unix timestamp, increments the week until the first instance ahead of now,
    taking into acount daylight savings.

    Returns a unix timestamp
    """
    # Get the current timestamp
    now = time.time()

    # How much time past qual we should wait before flipping to the next week
    dt = (timestamp_qual_minutes+30)*60 

    # If the transition time (ideally after the race has started) is ahead of us, 
    # don't increment the week
    if t0 + dt > now: return t0

    # Parse the scheduled timestamp and add the qualifying time.
    # We do the algorithm for the current time +/- an hour to allow for timezone shenanigans
    hour = datetime.timedelta(hours=1)
    tc = datetime.datetime.fromtimestamp(t0)

    # We remember the "center" hour for later, to make absolutely sure it matches after 
    # we increment by a week. Daylight savings is too finicky to worry about, and
    # we can't be guaranteed that everything is timezone aware.
    original_hour = tc.hour
    
    # Reverse until we reach a few hours from now, just to be safe
    # then increment until we find the next weekly event
    week = datetime.timedelta(days=7)
    while tc.timestamp() + dt > now: tc -= week
    while tc.timestamp() + dt < now: tc += week
    
    # Get the same time minus and plus an hour
    tp = tc + hour
    tm = tc - hour
    ts = [tc,tp,tm]

    # Find out which of the three has the same hour as the original
    tf = tc
    for t in ts: 
        #print(t.day, t.hour, original_hour)
        if t.hour == original_hour: 
            tf = t
            break
    
    # Return the timestamp
    return tf.timestamp()

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


def load_json(path, suppress_warning=False):
    """
    Load the supplied path with all the safety measures and encoding etc.
    """
    if path is None: return None

    if not os.path.exists(path): 
        if not suppress_warning: log('load_json: could not find', path)
        return
    try:
        f = open(path, 'r', encoding='utf8', errors='replace')
        j = json.load(f, strict=False)
        f.close()
        return j
    except Exception as e:
        log('ERROR: Could not load', path)
        log(e)


def port_is_open(host, port, timeout=5):

    # Try to connect
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.close()

    except: return False

    return True


class Monitor:

    def __init__(self):
        """
        Class for watching the AC server and reacting to various events
        """
        global url_webhook_online, path_log

        # Set to false after first messages sent
        self.first_run = True

        # json's from premium server manager
        self.info          = None
        self.live_timings  = None

        # Server status
        self.tcp_data_port_open = True # This is the 9600 port that is open when the server is "up". Stays open after a race.
        self.server_is_up       = True # This is whether we have access to api_details (sever is actually up)

        # Discord webhook objects
        self.webhook_online  = None # List of webhooks
        self.webhook_info    = None
        self.message_failure_timestamps = dict() # when it times out or whatever this increments.

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
                log('\nFOUND state.json, loaded')
                pprint.pprint(self.state)

                # May as well update once at the beginning, in case something changed
                # Note we cannot do this without state having track.
                self.load_ui_data()

        except Exception as e:
            log('\n\n-------------\nError: corrupt state.json; deleting', e)
            os.remove(p)

        # Premium mode
        if server_manager_premium_mode: 
            log('Monitoring for updates...')

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
                log('\nMONITORING FOR CHANGES...')
                self.vanilla_parse_lines(tail(open(path_log, 'r', encoding="utf8"), True))

        return

    def __getitem__(self, key): return self.state[key]

    def __setitem__(self, key, value): self.state[key] = value

    def reset_state(self):
        """
        Resets to state defaults (empty).
        """
        self.state = dict(
            online=dict(),  # Dictionary of online user info, indexed by name = {car:'car_dir'}
            online_message_id=None,  # Message id for the "who is online" messages
            one_hour_message_id = None, # Message id for "qual in an hour" message
            qualifying_message_id = None, # Message id for "qual open" message

            timestamp=None,  # Timestamp of the first observation of this venue.
            qual_timestamp=None,  # Timestamp of the qual
            race_timestamp=None,  # Timestamp of the race
            number_slots=None,    # Number of slots in race_json if it is a championship
            number_registered=None,  # Number of people registered in race_json if it is a championship
            track_name=None,  # Track / layout name
            track=None,  # Directory name of the track
            layout=None,  # Layout name
            laps_message_id=None,  # id of the discord message about laps to edit
            down_message_id=None,  # id of the discord message about whether the server is down

            archive_path=None,  # Path to the archive of state.json
            laps=dict(),  # Dictionary by name of valid laps for this track / layout
            naughties=dict(),  # Dictionary by name of cut laps
            carset=None,  # carset if possible to determine
            carsets=dict(),  # Dictionary of car lists by carset name for grouping laps
            stesrac=dict(),  # Dictionary of carset name lists by car for grouping laps
            cars=list(),  # List of car directories
            carnames=dict(), # Dictionary converting car dirnames to fancy names for everything in the venue.

            seen_namecars=dict(), # Set of people/cars seen online for this session.
            session_end_time=0,

            # Flags to prevent running the script many times in the time window
            script_one_hour_done   = False, 
            script_qualifying_done = False, 

            session_type=None,
        )


    def premium_get_latest_data(self):
        """
        Grabs all the latest event information from the server, and 
        send / update messages if anything changed.
        """
        if debug: log('\n_premium_get_latest_data')

        # Flag for information that changed
        laps_or_onlines_changed  = False  # laps or onlines for sending messages
        event_time_slots_changed = False  # If the scheduled timestamp or registrants changes
        track_changed            = False  # for making new venue
        carset_fully_changed     = False  # for making new venue
        session_changed          = False  # If the session changes
        server_state_changed     = False  # If the server has changed state

        # Test if the server is up
        self.tcp_data_port_open = port_is_open('localhost', tcp_data_port)

        # If we're down.
        if not self.tcp_data_port_open:

            # Send a warning message to discord
            if not no_down_warning and not self['down_message_id']:
                self['down_message_id'] = self.send_message(self.webhook_info, 
                    '', 'Server is down. I need an adult! :(', '', '')
                self.save_and_archive_state()

            # If the server state changed, note this
            if self.server_is_up: 
                
                # Flag to remember to send a message at the end.
                print('\n\nSERVER IS NOW DOWN!')
                server_state_changed = True

                # Run the server down->up script ONCE
                print('RUNNING SERVER DOWN SCRIPT\n  ', script_server_down)
                try: os.system(script_server_down)
                except Exception as e: print('OOPS!', e)
                
                # Also clear out the online drivers list
                self['seen_namecars'] = dict()
                self['online']        = dict()

            # Flag so we know it's down.
            self.server_is_up = False
            
            # Don't bother querying for api/details
            details = None

            # If we don't have a race_json to parse, quit out to avoid looping.
            if not path_race_json or len(path_race_json) == 0: 
            
                # Quick check to avoid cpu cycles and quit out: If the server
                # was previously up and went down, send state messages once.
                if server_state_changed: self.send_state_messages()

                # This is the only return in this method.
                return
            
            # Otherwise we parse the race_json and then send state messages

        # SERVER IS UP
        else:
            
            # See if it changed
            if not self.server_is_up: 
                print('\n\nSERVER IS BACK UP!')
                server_state_changed = True

                # Run the server down->up script ONCE
                print('RUNNING SERVER UP SCRIPT\n  ', script_server_up)
                try: os.system(script_server_up)
                except Exception as e: print('OOPS!', e)

            # Toggle it to up (it's up!)
            self.server_is_up = True
            
            # If there is a down message, clear it
            if self['down_message_id']:
                self.delete_message(self.webhook_info, self['down_message_id'])
                self['down_message_id'] = None
                self.save_and_archive_state()

            # Try to load the details from the server port
            try: details = json.loads(urllib.request.urlopen(url_api_details, timeout=5).read(), strict=False)
            except Exception as e:
                log('\n\nERROR: Could not open', url_api_details, e)
                details = None
                if self.server_is_up: 
                    print('\n\nWEIRD: SERVER IS UP BUT API DETAILS DOWN')
                    server_state_changed = True
                self.server_is_up = False

        # Get the previous set of onlines
        old = set()
        for name in self['online']: old.add((name, self['online'][name]['car']))

        # Get the new set of onlines
        new = set()
        if details:
            for car in details['players']['Cars']:
                if car['IsConnected']: new.add((car['DriverName'], car['Model']))
        # Otherwise, we know nothing, so assume no one is online.

        # If the sets are not equal, update
        if new != old:
            log('Detected a difference in online drivers', new, old)

            # remember to send the messages
            laps_or_onlines_changed = True

            # Redo the onlines in the state.
            self['online'] = dict()
            for item in new: self['online'][item[0]] = dict(car=item[1])

        # If we do not have timestamps but DO have timestamp_qual_start set it
        if not self['qual_timestamp'] and timestamp_qual_start:
            self['qual_timestamp'] = timestamp_qual_start
            self['race_timestamp'] = timestamp_qual_start + timestamp_qual_minutes*60

        # Now load the race json data
        try:
            race_json = c = load_json(path_race_json)
            
            # c comes back None if path_race_json is None
            # If it's NOT None, we get timestamp information.
            if c is not None:

                # We only get timestamps and registration warnings etc for championships,
                # which have a sign-up form in the top level.
                if 'SignUpForm' in c:

                    # Parse the scheduled timestamp and add the qualifying time, and registered
                    tq = dateutil.parser.parse(c['Events'][0]['Scheduled']).timestamp()
                    
                    # Special case: if tq < 0, it means the race already started and it is meaningless
                    if tq < 0 and self['qual_timestamp']: tq = self['qual_timestamp']
                    
                    # Get the race time from the duration of qualifying
                    tr = tq + c['Events'][0]['RaceSetup']['Sessions']['QUALIFY']['Time'] * 60
                    ns = len(c['Events'][0]['EntryList'])

                    # Have to manually count these since people can cancel registrations
                    nr = 0
                    if c['Classes'] and len(c['Classes']):
                        for r in c['Classes'][0]['Entrants'].values():
                            if r['GUID'] != '' or r['Name'] != '': nr += 1

                    # If it's different, update the state and send messages
                    if tq != self['qual_timestamp']    or tr != self['race_timestamp'] \
                    or nr != self['number_registered'] or ns != self['number_slots']:
                        event_time_slots_changed = True
                        self['qual_timestamp']    = tq
                        self['race_timestamp']    = tr
                        self['number_registered'] = nr
                        self['number_slots']      = ns
            
            # Get the track, layout, and cars from the website if there is no race_json
            track  = 'Unknown Track'
            layout = ''
            cars   = []
            #
            # With no race_json, we use details (if we got them above!)
            if race_json is None:

                # We already got the details above; these can be out of date sometimes, which is why we use
                # the race_json when available (below)
                if details:
                    track_layout = details['track'].split('-')
                    if len(track_layout) >= 2: layout = track_layout.pop(-1)
                    else:                      layout = ''
                    track = '-'.join(track_layout)
                    cars = details['cars']

            # Otherwise we use the more reliable race_json information
            else:
                
                # If this is a championship json or custom race, we get the race info differently.
                if 'Events' in race_json: rs = race_json['Events'][0]['RaceSetup']
                else:                     rs = race_json['RaceConfig']
                
                # Get the race info
                cars   = rs['Cars'].split(';') if rs['Cars'] else []
                track  = rs['Track']
                layout = rs['TrackLayout']

            # See if the carset fully changed
            carset_fully_changed = len(set(cars).intersection(self['cars'])) == 0
            self['cars'] = cars

            # See if the track or layout changed
            track_changed = (track != self['track'] or layout != self['layout'])
            self['track']  = track
            self['layout'] = layout

        except Exception as e:
            log('ERROR with race_json.json(s):', e)

        # If, after all that nonsense, we have a qual_timestamp and race_timestamp, 
        # then get the current time and send the messages warning about the event if we're within windows
        if self['qual_timestamp'] and self['race_timestamp']:

            # If we're in auto-week mode, find the next qual start time for this week
            if timestamp_qual_start:
                self['qual_timestamp'] = auto_week(self['qual_timestamp'])
                self['race_timestamp'] = self['qual_timestamp'] + 60*timestamp_qual_minutes

            # Get the times for comparison
            t = time.time()
            tq = self['qual_timestamp']
            tr = self['race_timestamp']

            # If we're within the one hour window
            if tq-3600 < t < tq: 

                # If we're giving one hour messages, send it ONCE.
                if one_hour_message and not self['one_hour_message_id']:
                    self['one_hour_message_id'] = self.send_message(self.webhook_info, one_hour_message, message_id=self['one_hour_message_id'])

                # If we're running a one hour script, do so ONCE.
                if script_one_hour and not self['script_one_hour_done']:
                    print('RUNNING ONE HOUR SCRIPT\n  '+script_one_hour)
                    try: os.system(script_one_hour)
                    except Exception as e: print('OOPS!', e)
                    self['script_one_hour_done'] = True

            # Outside the one hour window.
            else:

                # If we have a message, clean it up
                if self['one_hour_message_id']: 
                    self.delete_message(self.webhook_info, self['one_hour_message_id'])
                    self['one_hour_message_id'] = None

                # Reset the script flag for this window so we can run it again next time.
                self['script_one_hour_done'] = False

            # If we're within the qualifying window
            if tq < t < tr:
            
                # If we're doing the quali message, send it ONCE
                if qualifying_message and not self['qualifying_message_id']:
                    self['qualifying_message_id'] = self.send_message(self.webhook_info, qualifying_message, message_id=self['qualifying_message_id'])

                # If we're running a quali script, do so ONCE
                if script_qualifying and not self['script_qualifying_done']:
                    print('RUNNING QUALI SCRIPT\n  '+script_qualifying)
                    try: os.system(script_qualifying)
                    except Exception as e: print('OOPS!', e)
                    self['script_qualifying_done'] = True

            # Otherwise, we are outside the qual window.
            else: 

                # If we have a message, clean it up
                if self['qualifying_message_id']: 
                    self.delete_message(self.webhook_info, self['qualifying_message_id'])
                    self['qualifying_message_id'] = None
                
                # Make sure we arm the flag for the next time we enter the window
                self['script_qualifying_done'] = True


        # If the venue changed, do the new venue stuff.
        if track_changed or carset_fully_changed \
        and not self['track'] is None \
        and not self['layout'] is None \
        and not len(self['cars']) == 0:
            if track_changed:        log('premium_get_latest_data: track changed')
            if carset_fully_changed: log('premium_get_latest_data: carset fully changed')

            # Resets state, sets track, layout, carset
            self.new_venue(self['track'], self['layout'], self['cars'])
            
            # Move this so we don't accidentally think it's ok when the carset is totally changed
            # (live_timings.json does not include the available cars)
            if os.path.exists(path_live_timings): os.remove(path_live_timings)
            self.live_timings = None

        # Try to grab the live_timings data; load_json returns None if the file was moved.
        if path_live_timings and path_live_timings != '': 
            self.live_timings = load_json(path_live_timings, True)
            # if not self.live_timings: 
            #     print('\n\nINVALID live_timing.json?', path_live_timings, repr(self.live_timings))
        
        # If we found and loaded live_timings, and the track / layout matches (i.e., it's not old!)
        if self.live_timings and self.live_timings['Track'] == self['track'] and self.live_timings['TrackLayout'] == self['layout']:
            
            # guid = 123456767889
            for guid in self.live_timings['Drivers']:
                name = self.live_timings['Drivers'][guid]['CarInfo']['DriverName']

                # car = ac_legends_corvette_blah
                for car in self.live_timings['Drivers'][guid]['Cars']:

                    # If the car isn't in the venue, skip
                    if car not in self['cars']: continue

                    # Get the current best in ms (it was nanoseconds LULZ)
                    best  = self.live_timings['Drivers'][guid]['Cars'][car]['BestLap']*1e-6
                    count = self.live_timings['Drivers'][guid]['Cars'][car]['NumLaps'] 

                    # self['laps'][name][car] = {'time': '12:32:032', 'time_ms':12345, 'cuts': 3, 'laps': 23}
                    # If best exists and either 
                    #   the car doesn't exist in state,
                    #   this is better than what's in state, 
                    #   There is no 'count' key, or
                    #   the lap count is different
                    # update the laps for this car and driver.
                    if best and best > 100: # 100 ms minimum time to catch glitches.
                        if name not in self['laps']: self['laps'][name] = dict()

                        if car not in self['laps'][name]   \
                        or best < self['laps'][name][car]['time_ms'] \
                        or 'count' not in self['laps'][name][car]    \
                        or self['laps'][name][car]['count'] != count:

                            # Get the string time
                            ts = self.from_ms(best)

                            self['laps'][name][car] = dict(
                                time    = ts,
                                time_ms = best,
                                cuts    = 0,
                                count   = count,
                                track   = self['track'],
                                layout  = self['layout']
                            )

                            log('Lap:', name, car, self['laps'][name][car])

                            # Remember to update the messages
                            laps_or_onlines_changed = True


        # Finally, if ANYTHING changed, we need to update the messages
        if self.first_run \
        or laps_or_onlines_changed \
        or track_changed \
        or carset_fully_changed \
        or event_time_slots_changed \
        or session_changed \
        or server_state_changed:
            self.send_state_messages()
            self.first_run = False



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
                log('\n'+line.strip())

                # Get the car directory
                car = line[14:].replace('*','').strip()

                # Use the raw name. Will be converted with look-up table for
                # messages.
                self.last_requested_car = car

            # Driver name comes toward the end of someone connecting
            # DRIVER: Driver Name []
            elif line.find('DRIVER:') == 0:
                log('\n'+line.strip())
                self.vanilla_driver_connects(line[7:].split('[')[0].strip(), self.last_requested_car, init)

            # Clean exit, driver disconnected:  Driver Name []
            elif line.find('Clean exit, driver disconnected') == 0:
                log('\n'+line.strip())
                self.vanilla_driver_disconnects(line[33:].split('[')[0].strip(), init)

            # Connection is now closed for Driver Name []
            elif line.find('Connection is now closed') == 0:
                log('\n'+line.strip())
                self.vanilla_driver_disconnects(line[28:].split('[')[0].strip(), init)

            # Lap completed
            # Result.OnLapCompleted. Cuts: 7 ---
            elif line.find('Result.OnLapCompleted') == 0:
                log('\n'+line.strip())

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

                        log('  ->', repr(t), repr(n), cuts, 'cuts')

                        # Get the new time in ms
                        t_ms = self.to_ms(t)

                        # Make sure this name is in the state
                        if not n in self[laps]: self[laps][n] = dict()

                        # Should never happen, but if the person is no longer online, poop out.
                        if not n in self['online']:
                            log('  WEIRD: DRIVER OFFLINE NOW??')
                            break

                        # Get the car for the online person with this name
                        c = self['online'][n]['car']

                        # Structure:
                        # state[laps][n][car] = {'time': '12:32:032', 'time_ms':12345, 'cuts': 3}

                        # If the time is better than the existing or no entry exists
                        # Update it! Eliminate some bug laps by enforcing more than 1 second.
                        if (not c in self[laps][n] or t_ms < self[laps][n][c]['time_ms']) \
                        and t_ms > 1000:

                            self[laps][n][c] = dict(time=t, time_ms=t_ms, cuts=cuts)
                            if not init: 
                                self.save_and_archive_state()
                                self.send_state_messages()

                        # No need to keep looping through the history.
                        break

            # Check if track or carset has changed from the CALLING line after initialization
            elif line.find('CALLING ') == 0:
                log('\n'+line.strip())

                # Split off the ? then split by &
                items = line.split('?')[1].split('&')

                # Make the items into a dictionary
                for item in items:
                    s = item.split('=')
                    if(len(s) > 1):

                        # Cars list
                        if s[0] == 'cars':
                            cars = s[1].split('%2C')
                            log('  Cars:', cars)

                        # Track directory and layout, e.g. ks_barcelona-gp
                        elif s[0] == 'track':
                            tl = s[1].split('-')
                            track = tl[0]
                            if len(tl) > 1: layout = tl[1]
                            else:           layout = None
                            log('  Track:', track, layout)

                # If we have (entirely!) new cars or new track, initialize that.
                if len(set(cars).intersection(self['cars'])) == 0 \
                or track != self['track']     \
                or layout    != self['layout']:
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
                self['cars'] = cars

            # Attempt to catch a new log file; clear out onlines
            elif line.find('Assetto Corsa Dedicated Server') == 0:
                self['online'] = dict()
                if not init:
                    self.send_state_messages()
                    self.save_and_archive_state()

    def vanilla_driver_connects(self, name, car, init):
        """
        Sends a message about the player joining and removes the
        last requested car if any.
        """

        # Update the online list
        self['online'][name] = dict(car=car)

        # Send the message & save
        if not init: 
            self.send_state_messages()
            self.save_and_archive_state()

    def vanilla_driver_disconnects(self, name, init):
        """
        Sends a message about the player leaving.
        """

        # Only do anything if the name is in the list
        if not name in self['online']: return

        # Pop it
        self['online'].pop(name)

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
        log('\nnew_venue()')

        # Dump the existing state and copy to the archive before we update the timestamp
        self.save_and_archive_state()

        # End any session message that is currently active.
        self.end_session()

        # Reset everything; new venue happens when the server resets, which boots people (hopefully)
        # When the venue changes, the server may be down, and we want to remember the down message id.
        down_message_id = self['down_message_id']
        laps_message_id = self['laps_message_id']
        self.reset_state()
        self['down_message_id'] = down_message_id
        if venue_recycle_message: self['laps_message_id'] = laps_message_id

        # Stick the track directory in there
        log('new_venue (continued)...')
        log('  track ', self['track'],  '->', track)
        log('  layout', self['layout'], '->', layout)
        log('  cars  ', self['cars'],   '->', cars)
        self['track']  = track
        self['layout'] = layout
        self['cars']   = cars

        # Update the state with the race.json if it exists (gives track and cars and carset info)
        self.load_ui_data()

        # Timestamp changes only for new track; use the most recently seen timestamp
        self['timestamp'] = time.strftime('%Y-%m-%d_%H.%M.%S', time.localtime())
        
        # Save and archive the state for good measure?
        log(self['laps'])
        self.save_and_archive_state()

    def save_and_archive_state(self, skip=False):
        """
        Writes the state to state.json and copies it to the archive.
        """
        if skip: return

        log('save_and_archive_state()', not skip)

        # Make sure we have the appropriate directories
        if not os.path.exists('web'): os.mkdir('web')
        path_archive = os.path.join('web', 'archive')
        if not os.path.exists(path_archive): os.mkdir(path_archive)

        # Store the archive path for this particular state.json
        if self['track'] and self['timestamp']:
            self['archive_path'] = os.path.join(path_archive, self['timestamp'] +'.'+ self['track']+'.json')
        else:
            self['archive_path'] = None

        log('  archive_path:', self['archive_path'])

        # Dump the state
        p = os.path.join('web', 'state.json')
        with open(p, 'w', encoding="utf8") as f: json.dump(self.state, f, indent=2)

        # Copy to the archive based on track name if it exists.
        if self['archive_path']: shutil.copy(p, self['archive_path'])

        # Provide the website with a list of archives
        paths = glob.glob(os.path.join(path_archive, '*'))
        paths.sort(reverse=True)

        # If we're not keeping the full history, trim it
        if web_archive_history: paths = paths[0:web_archive_history]

        log('  ARCHIVES:\n   ', '\n    '.join(paths))
        f = open(path_archive+'.txt', 'w', encoding="utf8")
        f.write('\n'.join(paths))
        f.close()

    def from_ms(self, t, decimals=3):
        """
        Converts milliseconds to a nice string.
        """
        
        # Round to the appropriate decimals first
        t = round(t*0.1**(3-decimals)) * 10**(3-decimals)
        m = int(t/60000)
        s = (t-m*60000)*0.001
        return '%d:%02d.%d' % (m,int(s),s%1*10**decimals)

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
        log('\nload_ui_data()')
        log('state track, layout =', str(self['track']), str(self['layout']))

        # If we're here, there is no race.json, so let's look for information
        # in the ui_*.json files for the track and cars.

        # Start by looking for the track and layout
        if not self['layout'] is None:
            path_ui_track = os.path.join(path_ac, 'content', 'tracks',
                self['track'], 'ui',
                self['layout'],'ui_track.json')
        else:
            path_ui_track = os.path.join(path_ac, 'content', 'tracks',
                self['track'], 'ui', 'ui_track.json')

        # If the track/layout/ui_track.json exists, load the track name!
        if os.path.exists(path_ui_track):
            log(' ',path_ui_track)
            j = load_json(path_ui_track)
            if j: self['track_name'] = j['name']
        else:
            self['track_name'] = self['track']

        # Now load all the carsets if they exist
        path_carsets = os.path.join(path_ac, 'carsets')
        log('Checking', path_carsets)
        if os.path.exists(path_carsets):

            # Looks for and sort the carset paths
            carset_paths = glob.glob(os.path.join(path_carsets, '*'))
            carset_paths.sort()

            # For each carset path, load the contents into a list
            # for the dictionary self['carsets']
            self['carsets'] = dict()
            self['stesrac'] = dict()
            for path in carset_paths:
                log(' ', path)

                # Read the file
                f = open(path, 'r', encoding="utf8"); s = f.read().strip(); f.close()

                # Get the list of cars
                name = os.path.split(path)[-1]
                self['carsets'][name] = s.split('\n')

                # For each of these cars, append the carset name to the reverse-lookup
                for car in self['carsets'][name]:
                    if car not in self['stesrac']: self['stesrac'][car] = []
                    self['stesrac'][car].append(name)

                # If this carset matches ours, remember this carset
                if set(self['carsets'][name]) == set(self['cars']):
                    self['carset'] = name

        # Next load the nice names of all the cars for this venue
        log('Car nice names:')
        self['carnames'] = dict()
        for car in self['cars']:
            path_ui_car = os.path.join(path_ac,'content','cars',car,'ui','ui_car.json')
            if os.path.exists(path_ui_car):
                try:
                    j = load_json(path_ui_car)
                    self['carnames'][car] = j['name']
                    log(' ', car, j['name'])
                except Exception as e:
                    log('ERROR: loading', path_ui_car, e)
                    self['carnames'][car] = car
                    log(' ', car, '(error)')

        # Dump modifications
        self.save_and_archive_state()

    def get_carname(self, car):
        """
        Returns the fancy car name if possible, or the car dir if not.
        """
        # Get the fancy carname if possible.
        if car in self['carnames']: return self['carnames'][car]
        return car
    
    def sort_best_laps_by_carset(self):
        """
        Returns a dictionary with carset keys and an ordered list of driver laps, e.g.:

        {carset:[(time_ms,(time,name,car,count)), (time_ms,(time,name,car,count))...]}
        """   

        # Scan through the state and collect the driver best laps
        # laps will be {carset:[(time_ms,(time,name,car,count)), (time_ms,(time,name,car,count)), ...]}
        laps = dict() 
        for name in self['laps']:
            
            # Dictionary by carset of all laps for this driver name
            # will be {carset:[(time_ms,(time,name,car,count)), (time_ms,(time,name,car,count)), ...]}
            driver_laps = dict()
            
            # Loop through all their CAR bests, then add these to the CARSET bests
            for car in self['laps'][name]: # Each is a dictionary of {time, time_ms, cuts}
                c = self['laps'][name][car]    
            
                # Get a list of carsets to which this belongs
                if   car in self['stesrac']: carsets = self['stesrac'][car]
                else:                        carsets = [uncategorized]
                
                # for each of these carsets, append the driver name, time, etc
                for carset in carsets:

                    # Make sure it's in the driver_laps dictionary
                    if carset not in driver_laps: driver_laps[carset] = []

                    # Append it.
                    driver_laps[carset].append((c['time_ms'],(c['time'],name,car,c['count'])))

            # Now loop over each of this driver's carsets, and sort them
            for carset in driver_laps:

                # Sort eh carset
                driver_laps[carset].sort(key=lambda x: x[0])

                # Add this best to the MAIN laps carset
                if carset not in laps: laps[carset] = []
                laps[carset].append(driver_laps[carset][0]) # Best of this carset = 0 after sorting
        
        # Now sort all the different driver bests
        for carset in laps: laps[carset].sort(key=lambda x: x[0])
        
        # Sort the carsets alphabetically
        carsets_sorted = laps.keys()
        carsets_sorted.sort()

        # Pop the venue set to the top and the uncategorized to the bottom
        # for n in range(len(carsets)): 
        #     if carset == uncategorized: 
        #         x = carsets.pop
                
        #     if set(self['carsets'][carset]) == set(self['cars']):
        #         x = laps.pop(carset)
        
        laps_sorted = {i: laps[i] for i in carsets_sorted}

        return laps_sorted

    def sort_best_laps_by_name_and_car(self):
        """
        Returns a dictionary with car keys and an ordered list of driver laps, e.g.:

        {car:[(time_ms,(time,name,count)), (time_ms,(time,name,count))...]}
        """   

        # Scan through the state and collect the driver best laps
        # for each group
        laps_by_car   = dict() # car -indexed list of best laps
        laps_by_name  = dict() # name-indexed list of best laps
        car_bests     = dict() # car-indexed lists of all best lap times
        all_bests     = []     # everyone's bests in one list (any car)
        min_count     = 0      # minimum number of laps required to include
        
        # First get the min laps cutoff
        for name in self['laps']:
            for car in self['laps'][name]:
                # Use the highest count that isn't over 10
                min_count = max(min_count, min(self['laps'][name][car]['count'], 10))
        
        for name in self['laps']:

            # For each person, we have to loop through all their car bests,
            # then add these to the carset bests
            for car in self['laps'][name]: # Each is a dictionary of {time, time_ms, cuts}

                # Get the laps info, e.g.
                # "time": "2:04.461",
                # "time_ms": 124461.0,
                # "cuts": 0,
                # "count": 9
                # "car": porsche_whatever      # added
                c = deepcopy(self['laps'][name][car])
                c['car']  = car

                # Only consider this lap if the driver has turned enough laps
                if c['count'] >= min_count: 

                    # Make sure the car exists in laps as a dictionary by name
                    if car not in laps_by_car : laps_by_car[car] = dict()
                    if car not in car_bests   : car_bests[car]   = []

                    # Car-specific bests
                    if name not in laps_by_car[car] or c['time_ms'] < laps_by_car[car][name]['time_ms']: 
                        laps_by_car[car][name] = c
                        car_bests[car].append(c['time_ms'])
                    
                    # Any car bests
                    if name not in laps_by_name     or c['time_ms'] < laps_by_name    [name]['time_ms']: 
                        laps_by_name[name] = c
                        all_bests.append(c['time_ms'])

        # Sort laps JACK: Do we need to remove those not meeting min_laps here?
        laps_by_name = {k: v for k, v in sorted(laps_by_name.items(), key=lambda item: item[1]['time_ms'])}    
        all_bests.sort()
        for car in laps_by_car: 
            laps_by_car[car] = {k: v for k, v in sorted(laps_by_car[car].items(), key=lambda item: item[1]['time_ms'])}
            car_bests[car].sort()

        return all_bests, car_bests, min_count

    def get_stats_string(self, chars):
        """
        Returns a string with just some basic stats about lap times.
        """

        # If there are no laps, return None so we know not to use them.
        if not self['laps'] or len(self['laps'].keys()) == 0: return None

        # Get the sorted laps by name and car
        all_bests, car_bests, min_lap_count = self.sort_best_laps_by_name_and_car()

        # Loop over all the carsets
        lines = []
        
        # Get the number of participants
        N = len(all_bests)

        # If we have none, do nothing
        if N > 0:

            # Get the median time string
            tm = self.from_ms(median(all_bests), True)

            # Append this to the string
            lines.append('\n**Mid-Pace ('+str(min_lap_count)+' lap minimum)**')
        
            # If N > 1, add a summary
            if len(car_bests) > 1: lines.append('`' + tm + '` Driver Best ('+str(N)+')')

        # Do the same per car
        car_medians = dict() # {time_ms: line_string}

        for car in car_bests:
            N = len(car_bests[car])

            # Get the median in ms and the string
            tm_ms = median(car_bests[car])
            tm = self.from_ms(tm_ms, True)
            
            # Store by ms for sorting
            if car in self['carnames']:
                car_medians[tm_ms] = '`'+ tm + '` ' + self['carnames'][car]  + ' ('+str(N)+')'
            else:
                log('ERROR: WTF extra car', car, 'not in self["carnames"]')

        # Sort car_medians by time
        car_medians = {k: v for k, v in sorted(car_medians.items(), key=lambda item: item[0])}

        # Append to lines if there are more than one (to avoid double-information)
        for tm_ms in car_medians: lines.append(car_medians[tm_ms])
        
        # Make sure we don't have too many characters
        popped = False
        while len(lines) > 0 and len('\n'.join(lines)) > chars-4: # -4 for \n... 
            lines.pop(-1)
            popped = True

        # If we removed some lines, hint that there are more.
        if popped: lines.append('...')

        return '\n'.join(lines)

    def get_laps_string(self, chars):
        """
        Returns a string list of driver best laps for sending to discord. chars is
        the number of characters remaining.
        """

        # If there are no laps, return None so we know not to use them.
        if not self['laps'] or len(self['laps'].keys()) == 0: return None

        # Sort the laps by carset
        laps = self.sort_best_laps_by_carset()

        # Now sort all the group bests
        for carset in laps: 
            
            # Carset title
            title = '\n\n**'+carset+'**\n'
            
            # Now loop over the entries and build a string
            lines = []; n=1
            for x in laps[carset]: 
                lines.append('**'+str(n)+'.** '+self.fix_naughty_characters(
                 x[1][0]+' '+x[1][1]+' ('+self.get_carname(x[1][2])+')'))
                #lines.append('**'+x[1][0]+'** '+x[1][1]+' ('+self.get_carname(x[1][2])+')')
                n+=1
            
            # Pop lines until the message is short enough to fit
            popped = False
            while len(lines) > 0 and len(s+title+'\n'.join(lines)) > chars-4: # -4 for \n... 
                lines.pop(-1)
                popped = True

            # If we have no lines, don't bother
            if len(lines) == 0: 
                s = s + '\n...'
                break

            # If we removed some lines, hint that there are more.
            if popped: lines.append('...')
                      
            # Append this to the master
            s = title + '\n'.join(lines)

        return s.strip()       

    def get_onlines_string(self):
        """
        Returns a string list of who is online.
        """
        # If there are no onlines, return None, which prevents printing and 
        # sets the message color to gray.
        if len(self['online'].keys()) == 0: return None

        # If there are any online
        onlines = []; n=1
        online_namecars = []
        for name in self['online']:

            # Add the online namecar to the list
            namecar = self.get_namecar_string(name, self['online'][name]['car'])
            onlines.append('**'+str(n)+'. '+self.fix_naughty_characters(namecar)+'**')
            online_namecars.append(namecar)

            # Remember all the namecars we've seen and update the time stamps
            self['seen_namecars'][namecar] = time.time()

            # Next!
            n += 1

        # Now assemble the recents list
        recents = []; n=1
        to_pop = []
        for namecar in self['seen_namecars'].keys():
            
            # Trim out those that are too old (10 minutes)
            if time.time() - self['seen_namecars'][namecar] > 10*60:
                to_pop.append(namecar)
            
            # Otherwise, add it to the list of recents
            elif not namecar in online_namecars:
                recents.append(str(n)+'. '+self.fix_naughty_characters(namecar))
                n += 1
        
        # Prune; we do this separately to not change the keys size in the above loop
        for namecar in to_pop: self['seen_namecars'].pop(namecar)

        # Return the string
        s = '\n'.join(onlines)
        if len(recents): s = s + '\n\nRecently Online:\n' + '\n'.join(recents)
        return s.strip()
    
    def get_namecar_string(self, name, car):
        """
        Returns the nice-looking name + car string.
        """
        return name + ' (' + self.get_carname(car) + ')'

    def fix_naughty_characters(self, s):
        """
        Gets rid of characters that screw with discord's formatting.
        """
        
        # List of naughty characters
        naughty = ['*', '_', '`']
        
        for n in naughty: s = s.replace(n, '\\'+n)
        
        return s
        
    def get_join_link(self):
        """
        Generates a join link string.
        """
        # Generate the join link if we're supposed to
        join_link = ''
        if join_link_finish:
            
            # If the server is up, return the full join link etc.
            if self.server_is_up:
                try: 
                    server_ip = requests.get('https://ifconfig.me', timeout=3).text
                    join_link = '**[Join](<https://acstuff.ru/s/q:race/online/join?ip=' + server_ip + join_link_finish + '>)**'
                except Exception as e: 
                    log('  WARNING: no join link', e)

            # Otherwise return an unlinked "join" so people know where it WILL be when the server is up.
            else:
                join_link = '**Join**'

        return join_link

    def prune_laps(self):
        """
        Remove all the laps from previous venues, should there be any.
        This is useful if, e.g., server manager hasn't changed live_timings.json
        after an upload.
        """

        # Loop over player names in laps
        for name in list(self['laps'].keys()):
            for car in list(self['laps'][name].keys()):

                # If the car, track, or layout is not in the venue, pop it.
                if car not in self['cars'] \
                or 'track'  in self['laps'][name][car] and self['laps'][name][car]['track']  != self['track'] \
                or 'layout' in self['laps'][name][car] and self['laps'][name][car]['layout'] != self['layout']:
                    
                    # Pop it
                    log('  pruning', name, car)
                    self['laps'][name].pop(car)
                    
                    # If we popped the last element, pop the name.
                    if not len(self['laps'][name]): 
                        log('pruning', name)
                        self['laps'].pop(name)




    def send_state_messages(self):
        """
        Sends the state to the discord server. This includes a general info
        post with laps and who is online (to be edited when things change)
        and a "hey!" post if people come online.
        """
        log('send_state_messages()')

        # Generate the join link (or returns '' if disabled)
        join_link = self.get_join_link()

        # Rescanning the track and car ui's already happens when the venue changes anyway.
        # self.load_ui_data()

        # If there is session_end_time, that means the last time we
        # were here, we updated an onlines message to "completed" state.
        # It also means we have online_message_id and the self['seen_namecars'].
        # If this "dead post" has timed out, erase this info, which 
        # will generate a new message. This must be done before we get the 
        # onlines string, since that relies on seen_namecars.
        if self['session_end_time'] \
        and time.time()-self['session_end_time'] > online_timeout:
    
            # Reset the session info. Note this is the only place other than
            # new_venue and __init__ that clears seen_namecars
            self['online_message_id'] = None
            self['seen_namecars'] = dict()

        # Get the list of who is online
        onlines = self.get_onlines_string()
        #log('  Online:\n', onlines)

        ################################################################################################
        # INFO MESSAGE WITH LAPS AND ONLINE

        # These are misnamed for historical reasons.
        # They contain the time stamp if there is premium mode.
        reg_string1   = '' # Shorter bottom one
        top_timestamp = '' # Longer top one

        # If we are in premium mode, timestamps will be lists; otherwise, None.
        if self['qual_timestamp'] is not None and self['race_timestamp'] is not None:

            # By default, these are set to None;
            # when the race starts, acsm sets the start time to a negative number
            if self['qual_timestamp'] not in [0, None] and self['qual_timestamp'] > 0:

                # Get the time stamp for this race
                tq = str(int(self['qual_timestamp']))
                tr = str(int(self['race_timestamp']))

                # Create the full timestamp, optionally with name
                nametime1 = '<t:' + tq + ':D>'
                if registration_name: nametime1 = registration_name + ' '+nametime1

                # Create the top_timestamp.
                top_timestamp = '\n' + nametime1 \
                                + '\n`Qual:` ' + ' <t:' + tq + ':t>' + ' (<t:' + tq + ':R>)' \
                                + '\n`Race:` ' + ' <t:' + tr + ':t>' + ' (<t:' + tr + ':R>)'

            # Linkify it if there is registration info
            if type(url_registration) is str and self['number_slots']:
                nametime1 = '**[Register (' + str(self['number_registered']) + '/' + str(self['number_slots']) + ')](' + url_registration + ')**'
                reg_string1 = nametime1  # Bottom registration stylized

        # Get the laps info footer now for later computing the length
        footer = '\n\n'+reg_string1+laps_footer+join_link

        # Track name
        track_name = self['track_name']
        if not track_name: track_name = self['track']
        if not track_name: track_name = 'Unknown Track?'

        title = ''
        carset = None
        if self['carset']: carset = str(self['carset'])
        elif len(self['carnames']) == 1:
            carset = str(list(self['carnames'].values())[0])

        # Add the carset to the title if needed
        if carset: title = title + carset.upper() + ' @ '
        if track_name: title = title + track_name.upper()
        if url_event_info not in [None, False, '']:
            title = '[' + title +']('+url_event_info+')'

        # Assemble the message body
        body1 = venue_header + '**__'+title+'__**'

        # Subheader
        body1 = body1 + top_timestamp + venue_subheader
        
        # Separate body for who's online (laps get cut first)
        body2 = ''
        if onlines:
            body2 = '\n\n**' + online_header + '**\n' + onlines
            color = color_onlines
        elif self.server_is_up: color = color_server_up
        else:                   color = 0

        # Get the list of driver best laps 4070 leaves a little buffer for ... and stuff.
        N = 4070-len(body1+body2+footer)
        #self.prune_laps() # I believe the new code for adding laps from live_timings fixes the need for this.
        if no_leaderboard: laps = self.get_stats_string(N)
        else:              laps = self.get_laps_string(N)
        if debug and laps: log('LAPS\n'+laps)

        # Below the venue and above laps
        if laps: body1 = body1 + '\n' + laps

        # Send the main info message. Body 1 is the laps list, body 2 includes previous onlines
        self['laps_message_id'] = self.send_message(self.webhook_info, '', body1, body2, footer, self['laps_message_id'], color=color)
        if self['laps_message_id'] is None: log('DID NOT EDIT OR SEND LAPS MESSAGE')


        #############################################################################################
        # HAY MESSAGE WITH JUST ONLINES

        # If there is anyone currently online send / update the message about it
        # onlines is either a string or None if there isn't anyone online
        if onlines:

            # We have onlines so the session is live. 0 will preclude the above message shutdown
            self['session_end_time'] = 0

            # Assemble the message body
            body1 = '**' + online_header + '**\n' + onlines

            # Send the message
            self['online_message_id'] = self.send_message(self.webhook_online, '', body1, '', '\n\n'+online_footer+join_link, self['online_message_id'])
            if self['online_message_id'] is None: log('DID NOT EDIT OR SEND ONLINES')

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
        log('end_session()', self['seen_namecars'].keys(), self['online_message_id'])
        if self['online_message_id']: 

            # Get a list of the seen namecars from this session
            errbody = []; n=1
            for namecar in self['seen_namecars'].keys():
                errbody.append(str(n)+'. '+namecar)
                n += 1
            
            # This is a hack; I'm not sure why sometimes seen_namecars is empty but there
            # is an online_message_id, except on startup or new venue.
            if len(errbody):
                body1 = session_complete_header+'\n\nParticipants:\n'+'\n'.join(errbody)
                self['online_message_id'] = self.send_message(self.webhook_online, '', body1, '', '\n\n'+online_footer+self.get_join_link(), self['online_message_id'], 0)
                
                # Remember the time this message was "closed". If a new session
                # starts within a little time of this, use the same message id
                # Otherwise it will make a new session message.
                self['session_end_time'] = time.time()
            
            else: 
                log('**** GOSH DARN IT, LOST THE SEEN_NAMECARS AGAIN! WTF.', self['seen_namecars'].keys())
                self.delete_message(self.webhook_online, self['online_message_id'])
                self['online_message_id'] = None
                self['session_end_time'] = 0
            
            

    def delete_message(self, webhook, message_id):
        """
        Deletes the supplied message.
        """
        # Make sure we actually have a message id
        if not type(message_id) == int or not message_id: return

        log('delete_message()')
        if webhook and message_id:
            try: webhook.delete_message(message_id)
            except: pass

    def send_message(self, webhook, message='', body1='', body2='', footer='', message_id=None, color=15548997):
        """
        Sends a message (message, 2000 character limit) and an embed
        (body1, body2, footer, 4096 characters total). Returns the message id
        """
        log('\nsend_message()')

        # We can call this with None webhook without fail
        if not webhook: return

        # Keep the total character limit below 4096, cutting body1 first, then body 2
        if len(body1+body2+footer) > 4070: # 4070 gives a little buffer for ... and stuff. I don't wanna count.

            # If body2 and footer are already over the limit, just trim body2 and be done
            if len(body2+footer) > 4070: body = body2[0:4070-len(footer)] + ' ...' + footer

            # Otherwise, we trim body1
            else:                        body = body1[0:4070-len(body2)-len(footer)] + ' ...' + body2 + footer

        # Otherwise just use the whole thing
        else: body = body1 + body2 + footer

        # Keep the message characters below 2000
        if len(message) > 2000: message = message[0:1995] + '\n...'

        if debug: 
            log(message)
            log(body)

        # Sending by embed makes it prettier and larger
        e = discord.Embed()
        e.color       = color
        e.description = body

        # If we have a message_id it means we should edit the existing post
        if message_id:
            
            # First try to edit the existing method
            try:    
                # Try to edit the message
                if len(e.description): webhook.edit_message(message_id, content=message, embeds=[e])
                else:                  webhook.edit_message(message_id, content=message, embeds=[] )
                
                # If it works, remove the failure timestamp.
                if message_id in self.message_failure_timestamps.keys(): 
                    self.message_failure_timestamps.pop(message_id)
            
            # It didn't work. Count the failures and then give up / send a new one
            except Exception as x:
                
                # If we need to start counting, create a counter.
                if not message_id in self.message_failure_timestamps.keys(): self.message_failure_timestamps[message_id] = time.time()
                
                # Let the user know
                log('WHOOPS could not edit message', message_id, e, x, 'dt =', 
                    time.time() - self.message_failure_timestamps[message_id])

                # If it's been awhile since the first failure, try again
                if time.time() - self.message_failure_timestamps[message_id] > 10:
                    
                    # Get rid of the entry for this
                    log('  Timeout! Popping id...')
                    self.message_failure_timestamps.pop(message_id)
                    
                    # Now try to get a new one...
                    try: 
                        log('  Trying to send a new message...')
                        
                        if len(e.description): message_id = webhook.send(message, embeds=[e], wait=True).id
                        else:                  message_id = webhook.send(message, embeds=[],  wait=True).id
                        
                        log('  Sent id', message_id)
                    
                    # Couldn't send
                    except Exception as x: 
                        log('  WHOOPS (CRITICAL) could not send ', x)
                        message_id = None
                
                # Otherwise try again
                else:
                    time.sleep(3)
                    message_id = self.send_message(webhook, message, body1, body2, footer, message_id, color)
        
        # If we don't have a message_id, just try to send a new one.
        else:
            
            # Try to send it
            try: 
                if len(e.description): message_id = webhook.send(message, embeds=[e], wait=True).id
                else:                  message_id = webhook.send(message, embeds=[ ], wait=True).id
            except Exception as x:
                log('WHOOPS could not send message', message_id, e, x)
                message_id = None

        # Return it.
        return message_id


# Create the object
self = Monitor()

