#!/usr/bin/env python3
# -*- coding: utf-8 -*-

##################################################################
# This script monitors AC server for key events,                 #
# sending messages for people joining/leaving and lap times.     #
# See monitor.ini for configuration!                             #
##################################################################

import os
import json
import discord
import time
import datetime
import urllib
import dateutil.parser
import socket
import requests
import ipaddress
from numpy import median
from copy import deepcopy
from typing import Dict, List, Optional, Tuple, Any

# Change to the directory of this script
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Load configuration
def load_config():
    """Load configuration from monitor.ini files"""
    config = {}
    
    # Default values
    defaults = {
        'tcp_data_port': None,
        'http_port': None,
        'no_down_warning': False,
        'path_live_timings': None,
        'path_race_json': None,
        'url_registration': None,
        'registration_name': None,
        'path_ac': None,
        'url_webhook_online': None,
        'online_header': '',
        'online_footer': '',
        'session_complete_header': '**Session complete.**',
        'online_timeout': 10*60,
        'color_onlines': 10181046,
        'color_server_up': 5763719,
        'bot_name': None,
        'url_webhook_info': None,
        'url_event_info': '',
        'venue_header': '',
        'venue_subheader': '',
        'venue_recycle_message': True,
        'laps_footer': '',
        'leaderboard_mode': 0,
        'hotlap_title': 'Apex-Nerd',
        'hotlap_titles': 'Apex-Nerd(s)',
        'one_hour_message': None,
        'qualifying_message': None,
        'timestamp_qual_start': None,
        'qual_minutes': 60,
        'join_link_finish': None,
        'server_ip': None,
        'script_one_hour': None,
        'script_qualifying': None,
        'script_server_down': None,
        'script_server_up': None,
        'debug': False,
        'uncategorized': 'Uncategorized'
    }
    
    # Apply defaults first
    for key, value in defaults.items():
        config[key] = value
    
    # Load from ini files (will override defaults)
    if os.path.exists('monitor.ini'):
        exec(open('monitor.ini', 'r', encoding="utf8").read(), {}, config)
    if os.path.exists('monitor.ini.private'):
        exec(open('monitor.ini.private', 'r', encoding="utf8").read(), {}, config)
    
    return config

# Global configuration
CONFIG = load_config()

# Global server_ip for persistence
server_ip = CONFIG['server_ip']

def log(*args):
    """Print with timestamp"""
    ts = str(datetime.datetime.now())
    print(ts, *args)

def load_json(path: str, suppress_warning: bool = False) -> Optional[dict]:
    """Safely load JSON file"""
    if path is None:
        return None
    
    if not os.path.exists(path):
        if not suppress_warning:
            log('load_json: could not find', path)
        return None
    
    try:
        with open(path, 'r', encoding='utf8', errors='replace') as f:
            return json.load(f, strict=False)
    except Exception as e:
        log('ERROR: Could not load', path)
        log(e)
        return None

def port_is_open(host: str, port: int, timeout: int = 5) -> bool:
    """Check if a port is open"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.close()
        return True
    except:
        return False

def get_unix_timestamp(y, M, d, h, m):
    """Returns a unix timestamp for the specified date/time"""
    dt = datetime.datetime(y, M, d, h, m)
    return time.mktime(dt.timetuple())

def auto_week(t0: float) -> float:
    """Auto-increment week for recurring events"""
    global CONFIG
    
    now = time.time()
    dt = (CONFIG['qual_minutes'] + 30) * 60
    
    if t0 + dt > now:
        return t0
    
    tc = datetime.datetime.fromtimestamp(t0)
    original_hour = tc.hour
    
    week = datetime.timedelta(days=7)
    while tc.timestamp() + dt > now:
        tc -= week
    while tc.timestamp() + dt < now:
        tc += week
    
    # Handle daylight savings
    hour = datetime.timedelta(hours=1)
    tp = tc + hour
    tm = tc - hour
    ts = [tc, tp, tm]
    
    for t in ts:
        if t.hour == original_hour:
            return t.timestamp()
    
    return tc.timestamp()

class Monitor:
    """Main monitor class for AC server"""
    
    def __init__(self):
        """Initialize the monitor"""
        global CONFIG, server_ip
        
        self.first_run = True
        self.info = None
        self.live_timings = None
        self.time_last_live_timings_fail = 0
        
        # Discord webhooks
        self.webhook_online = None
        self.webhook_info = None
        self.message_failure_timestamps = {}
        
        # Create webhooks
        if CONFIG['url_webhook_online']:
            self.webhook_online = discord.SyncWebhook.from_url(CONFIG['url_webhook_online'])
        
        if CONFIG['url_webhook_info']:
            self.webhook_info = discord.SyncWebhook.from_url(CONFIG['url_webhook_info'])
        
        # Reset state
        self.reset_state()
        
        # Load existing state if available
        state_path = os.path.join('web', 'state.json')
        try:
            if os.path.exists(state_path):
                saved_state = load_json(state_path)
                if saved_state:
                    self.state.update(saved_state)
                    log('\nFOUND state.json, loaded')
                    import pprint
                    pprint.pprint(self.state)                    
                    self.load_ui_data()

        except Exception as e:
            log('\n\n-------------\nError: corrupt state.json; deleting', e)
            os.remove(state_path)
            
        # Start premium mode monitoring
        log('Performing initial data sync...')
        self.get_latest_data()
        
        if self['number_registered'] is not None:
            log('Forcing initial state message update...')
            self.send_state_messages()
            self.first_run = False
        
        log('Initial sync complete. Starting main loop.')
        
        # Main monitoring loop
        if not CONFIG['debug']:
            while True:
                self.get_latest_data()
                time.sleep(3)
        else:
            log('DEBUG MODE: Not starting main loop')
    
    def __getitem__(self, key):
        return self.state[key]
    
    def __setitem__(self, key, value):
        self.state[key] = value
    
    def reset_state(self):
        """Reset state to defaults"""
        self.end_session()
        
        self.state = dict(
            online=dict(),
            online_message_id=None,
            one_hour_message_id=None,
            qualifying_message_id=None,
            timestamp=None,
            qual_timestamp=None,
            race_timestamp=None,
            number_slots=None,
            number_registered=None,
            registration=dict(),
            track_name=None,
            track=None,
            layout=None,
            laps_message_id=None,
            down_message_id=None,
            laps=dict(),
            naughties=dict(),
            carset=None,
            carsets=dict(),
            stesrac=dict(),
            cars=list(),
            carnames=dict(),
            seen_namecars=dict(),
            session_end_time=0,
            script_one_hour_done=False,
            script_qualifying_done=False,
            tcp_data_port_open=False,
            server_is_up=False,
            session_type=None,
        )
    
    def get_latest_data(self):
        """Get latest data from server and process changes"""
        global CONFIG, server_ip
        
        if CONFIG['debug']:
            log('\n_premium_get_latest_data')
        
        # Track what changed
        server_state_changed = False
        server_state_changed = False
        track_changed = False
        carset_fully_changed = False
        server_state_changed = False
        
        # Check server status
        self['tcp_data_port_open'] = port_is_open('localhost', CONFIG['tcp_data_port'])

        # Server is down
        if not self['tcp_data_port_open']:
            
            # Send down warning
            if not CONFIG['no_down_warning'] and not self['down_message_id']:
                self['down_message_id'] = self.send_message(
                    self.webhook_info, '', 'Server is down. I need an adult! :(', 
                    '', '', username=CONFIG['bot_name']
                )
                self.save_state()
            
            # Server just went down
            if self['server_is_up']:
                log('SERVER IS NOW DOWN!')
                server_state_changed = True
                
                self.end_session()
                self['online_message_id'] = None
                
                # Run server down script
                if CONFIG['script_server_down']:
                    log('RUNNING SERVER DOWN SCRIPT\n  ', CONFIG['script_server_down'])
                    try:
                        os.system(CONFIG['script_server_down'])
                    except Exception as e:
                        print('OOPS!', e)
                
                self['seen_namecars'] = dict()
                self['online'] = dict()
            
            self['server_is_up'] = False
            details = None
            
            # Quit if no race.json to process
            if not CONFIG['path_race_json'] or len(CONFIG['path_race_json']) == 0:
                if server_state_changed:
                    self.send_state_messages()
                return

        # Server is up
        else:
            # Server just came up
            if not self['server_is_up']:
                log('SERVER IS BACK UP!')
                server_state_changed = True
                
                # Run server up script
                if CONFIG['script_server_up']:
                    log('RUNNING SERVER UP SCRIPT\n  ', CONFIG['script_server_up'])
                    try:
                        os.system(CONFIG['script_server_up'])
                    except Exception as e:
                        print('OOPS!', e)
            
            self['server_is_up'] = True
            
            # Clear down message
            if self['down_message_id']:
                self.delete_message(self.webhook_info, self['down_message_id'])
                self['down_message_id'] = None
                self.save_state()
            
            # Get server details
            details = None
            if CONFIG['http_port']:
                url_api_details = 'http://localhost:' + str(CONFIG['http_port']) + '/api/details'
                try:
                    details = json.loads(
                        urllib.request.urlopen(url_api_details, timeout=5).read(), 
                        strict=False
                    )
                except Exception as e:
                    log('WARNING: Could not open', url_api_details, e)
                    details = None
                    # Don't change server_is_up state here - TCP port is still open
                    # This just means we don't have detailed info
        
        # Process online players
        old = set()
        for name in self['online']:
            old.add((name, self['online'][name]['car']))
        
        new = set()
        if details:
            for car in details['players']['Cars']:
                if car['IsConnected'] and not car['DriverName'].startswith('[Not Connected]'):
                    new.add((car['DriverName'], car['Model']))
        
        if new != old:
            log('Detected a difference in online drivers', new, old)
            server_state_changed = True
            
            self['online'] = dict()
            for item in new:
                self['online'][item[0]] = dict(car=item[1])
        




        # Load race.json
        race_json = load_json(CONFIG['path_race_json'])
        
        
        # Get track and cars info
        track = 'Unknown Track'
        layout = ''
        cars = []
        
        # Without race_json we don't get much info.
        if race_json is None:
            if details:
                track_layout = details['track'].split('-')
                if len(track_layout) >= 2:
                    layout = track_layout.pop(-1)
                else:
                    layout = ''
                track = '-'.join(track_layout)
                cars = details['cars']
        
        # More detailed info from race.json
        else:
            if 'Events' in race_json:
                rs = race_json['Events'][0]['RaceSetup']
            else:
                rs = race_json['RaceConfig']
            
            cars = rs['Cars'].split(';') if rs['Cars'] else []
            track = rs['Track']
            layout = rs['TrackLayout']

            # Event schedule
            tq = dateutil.parser.parse(race_json['Events'][0]['Scheduled']).timestamp()
            CONFIG['qual_minutes'] = race_json['Events'][0]['RaceSetup']['Sessions']['QUALIFY']['Time']
            tr = tq + CONFIG['qual_minutes'] * 60
            
            if (tq != self['qual_timestamp'] or 
                tr != self['race_timestamp']):
                server_state_changed = True
                schedule_changed = True
                self['qual_timestamp'] = tq
                self['race_timestamp'] = tr
        
        # Handle CSP/ACSM paths
        if '/' in track: track = track.split('/')[-1]
        
        # Check for venue changes
        carset_fully_changed = len(set(cars).intersection(self['cars'])) == 0
        self['cars'] = cars
        
        track_changed = (track != self['track'] or layout != self['layout'])
        self['track'] = track
        self['layout'] = layout
        
        # Set timestamps from config if needed
        if not self['qual_timestamp'] and CONFIG['timestamp_qual_start']:
            self['qual_timestamp'] = CONFIG['timestamp_qual_start']
            self['race_timestamp'] = CONFIG['timestamp_qual_start'] + CONFIG['qual_minutes'] * 60
        
        # Handle scheduled messages
        if self['qual_timestamp'] and self['race_timestamp']:
            
            # Auto-week mode
            if CONFIG['timestamp_qual_start']:
                self['qual_timestamp'] = auto_week(self['qual_timestamp'])
                self['race_timestamp'] = self['qual_timestamp'] + 60 * CONFIG['qual_minutes']
            
            t = time.time()
            tq = self['qual_timestamp']
            tr = self['race_timestamp']
            
            # One hour window
            if tq - 3600 < t < tq:
                if CONFIG['one_hour_message'] and not self['one_hour_message_id']:
                    self['one_hour_message_id'] = self.send_message(
                        self.webhook_info, CONFIG['one_hour_message'],
                        message_id=self['one_hour_message_id'],
                        username=CONFIG['bot_name']
                    )
                
                if CONFIG['script_one_hour'] and not self['script_one_hour_done']:
                    print('RUNNING ONE HOUR SCRIPT\n  ' + CONFIG['script_one_hour'])
                    try:
                        os.system(CONFIG['script_one_hour'])
                    except Exception as e:
                        print('OOPS!', e)
                    self['script_one_hour_done'] = True
            else:
                if self['one_hour_message_id']:
                    self.delete_message(self.webhook_info, self['one_hour_message_id'])
                    self['one_hour_message_id'] = None
                
                self['script_one_hour_done'] = False
            
            # Qualifying window
            if tq < t < tr:
                if CONFIG['qualifying_message'] and not self['qualifying_message_id']:
                    self['qualifying_message_id'] = self.send_message(
                        self.webhook_info, CONFIG['qualifying_message'],
                        message_id=self['qualifying_message_id'],
                        username=CONFIG['bot_name']
                    )
                
                if CONFIG['script_qualifying'] and not self['script_qualifying_done']:
                    print('RUNNING QUALI SCRIPT\n  ' + CONFIG['script_qualifying'])
                    try:
                        os.system(CONFIG['script_qualifying'])
                    except Exception as e:
                        print('OOPS!', e)
                    self['script_qualifying_done'] = True
            else:
                if self['qualifying_message_id']:
                    self.delete_message(self.webhook_info, self['qualifying_message_id'])
                    self['qualifying_message_id'] = None
                
                self['script_qualifying_done'] = False
        
        # Handle venue changes
        if (track_changed or carset_fully_changed or schedule_changed) and \
           self['track'] is not None and \
           self['layout'] is not None and \
           len(self['cars']) != 0:
            
            if track_changed:
                log('premium_get_latest_data: track changed')
            if carset_fully_changed:
                log('premium_get_latest_data: carset fully changed')
            
            self.new_venue(self['track'], self['layout'], self['cars'])
            
            if not self.first_run and CONFIG['path_live_timings'] and os.path.exists(CONFIG['path_live_timings']):
                os.remove(CONFIG['path_live_timings'])
            self.live_timings = None
        
        # Process live timings
        if time.time() - self.time_last_live_timings_fail > 10 * 60:
            if CONFIG['path_live_timings'] and CONFIG['path_live_timings'] != '':
                self.live_timings = load_json(CONFIG['path_live_timings'], True)
                if not self.live_timings:
                    log('WARNING: INVALID live_timing.json: ' + str(CONFIG['path_live_timings']) + 
                        '\nNot checking again for 10 minutes...')
                    self.time_last_live_timings_fail = time.time()
        
        # Process live timing laps
        if self.live_timings:
            
            # Bootstrap venue if needed
            if (not self['laps'] or len(self['laps']) == 0) and \
               self.live_timings['Track'] and self.live_timings['TrackLayout']:
                if not self['track'] or not self['layout']:
                    log('Bootstrapping venue from live_timings.json')
                    self['track'] = self.live_timings['Track']
                    self['layout'] = self.live_timings['TrackLayout']
            
            # Process laps if track matches
            if self.live_timings['Track'] == self['track'] and \
               self.live_timings['TrackLayout'] == self['layout']:
                
                for guid in self.live_timings['Drivers']:
                    name = self.live_timings['Drivers'][guid]['CarInfo']['DriverName']
                    
                    for car in self.live_timings['Drivers'][guid]['Cars']:
                        if car not in self['cars']:
                            continue
                        
                        best = self.live_timings['Drivers'][guid]['Cars'][car]['BestLap'] * 1e-6
                        count = self.live_timings['Drivers'][guid]['Cars'][car]['NumLaps']
                        
                        if best and best > 100:
                            if name not in self['laps']:
                                self['laps'][name] = dict()
                            
                            if car not in self['laps'][name] or \
                               best < self['laps'][name][car]['time_ms'] or \
                               'count' not in self['laps'][name][car] or \
                               self['laps'][name][car]['count'] != count:
                                
                                ts = self.from_ms(best)
                                
                                self['laps'][name][car] = dict(
                                    time=ts,
                                    time_ms=best,
                                    cuts=0,
                                    count=count,
                                    track=self['track'],
                                    layout=self['layout']
                                )
                                
                                log('Lap:', name, car, self['laps'][name][car])
                                server_state_changed = True
        
        # Process registration and timestamps
        if race_json and 'SignUpForm' in race_json:
            
            # Get current registrants
            new_registrants = dict()
            
            # Better place to look
            if race_json.get('Classes') and len(race_json['Classes']):
                for key, r in race_json['Classes'][0]['Entrants'].items():
                    if r.get('GUID', '') != '' and r.get('Name', '') != '':
                        new_registrants[r['GUID']] = [r['Name'], r['Model']]
            
            # Fallback bullshit
            elif 'Responses' in race_json['SignUpForm']:
                for r in race_json['SignUpForm']['Responses']:
                    if r.get('Status') == 'Accepted' and r.get('GUID', '') != '':
                        new_registrants[r['GUID']] = [
                            r['Name'], 
                            r.get('Car', r.get('Model', 'unknown'))
                        ]
            
            # Announce new registrations
            for guid in set(new_registrants.keys()) - set(self['registration']):
                new_driver = new_registrants[guid]
                carname = new_driver[1]
                if carname in self['carnames']:
                    carname = self['carnames'][carname]
                
                a = 'a '
                if carname and carname[0].lower() in ['a','e','i','o','u']:
                    a = 'an '
            
                print('REGISTER ANNOUNCEMENT:', new_driver, carname)
                # self.send_message(
                #     self.webhook_online, 
                #     new_driver[0] + ' registered in ' + a + carname,
                #     username=CONFIG['bot_name']
                # )
            
            self['registration'] = new_registrants
            
            # Update event parameters
            ns = len(race_json['Events'][0]['EntryList'])
            if ns != self['number_slots']: 
                server_state_changed = True
                self['number_slots'] = ns
            
            nr = len(new_registrants)
            if nr != self['number_registered']:
                server_state_changed = True
                self['number_registered'] = nr
            
            
                
                


        # Send messages if anything changed
        if self.first_run or track_changed or carset_fully_changed or server_state_changed:
            self.send_state_messages()
            self.first_run = False
    
    def new_venue(self, track, layout, cars):
        """Initialize new venue"""
        log('\nnew_venue()')
        
        self.save_state()
        
        down_message_id = self['down_message_id']
        laps_message_id = self['laps_message_id']
        self.reset_state()
        self['down_message_id'] = down_message_id
        if CONFIG['venue_recycle_message']:
            self['laps_message_id'] = laps_message_id
        
        log('new_venue (continued)...')
        log('  track ', self['track'], '->', track)
        log('  layout', self['layout'], '->', layout)
        log('  cars  ', self['cars'], '->', cars)
        
        self['track'] = track
        self['layout'] = layout
        self['cars'] = cars
        
        self.load_ui_data()
        
        self['timestamp'] = time.strftime('%Y-%m-%d_%H.%M.%S', time.localtime())
        
        log(self['laps'])
        self.save_state()
    
    def save_state(self, skip=False):
        """Save state to disk"""
        if skip:
            return
        
        log('save_state()', not skip)
        
        if not os.path.exists('web'):
            os.mkdir('web')
        
        p = os.path.join('web', 'state.json')
        with open(p, 'w', encoding="utf8") as f:
            json.dump(self.state, f, indent=2)
    
    def from_ms(self, t, decimals=3):
        """Convert milliseconds to time string"""
        t = round(t * 0.1**(3-decimals)) * 10**(3-decimals)
        m = int(t / 60000)
        s = (t - m * 60000) * 0.001
        s_int = int(s)
        s_frac = round((s % 1) * 10**decimals)
        return '%d:%02d.%0*d' % (m, s_int, decimals, s_frac)
    
    def to_ms(self, s):
        """Convert time string to milliseconds"""
        s = s.split(':')
        return int(s[0]) * 60000 + int(s[1]) * 1000 + int(s[2])
    
    def load_ui_data(self):
        """Load UI data for track and cars"""
        log('\nload_ui_data()')
        log('state track, layout =', str(self['track']), str(self['layout']))
        
        if not os.path.exists(CONFIG['path_ac']):
            raise Exception('ERROR: path_ac does not exist\n  ' + CONFIG['path_ac'])
        
        # Load track UI
        if self['layout'] is not None:
            path_ui_track = os.path.join(
                CONFIG['path_ac'], 'content', 'tracks',
                self['track'], 'ui', self['layout'], 'ui_track.json'
            )
        else:
            path_ui_track = os.path.join(
                CONFIG['path_ac'], 'content', 'tracks',
                self['track'], 'ui', 'ui_track.json'
            )
        
        if os.path.exists(path_ui_track):
            log(' ', path_ui_track)
            j = load_json(path_ui_track)
            if j:
                self['track_name'] = j['name']
        else:
            self['track_name'] = self['track']
        
        # Load carsets
        import glob
        path_carsets = os.path.join(CONFIG['path_ac'], 'carsets')
        log('Checking', path_carsets)
        if os.path.exists(path_carsets):
            carset_paths = glob.glob(os.path.join(path_carsets, '*.json'))
            carset_paths.sort()
            
            self['carsets'] = dict()
            self['stesrac'] = dict()
            
            for path in carset_paths:
                log(' ', path)
                j = load_json(path)
                
                name = os.path.split(os.path.splitext(path)[0])[-1]
                self['carsets'][name] = list(j['cars'])
                
                for car in self['carsets'][name]:
                    if car not in self['stesrac']:
                        self['stesrac'][car] = []
                    self['stesrac'][car].append(name)
                
                if set(self['carsets'][name]) == set(self['cars']):
                    self['carset'] = name
        
        # Load car names
        log('Car nice names:')
        self['carnames'] = dict()
        for car in self['cars']:
            path_ui_car = os.path.join(
                CONFIG['path_ac'], 'content', 'cars', 
                car, 'ui', 'ui_car.json'
            )
            if os.path.exists(path_ui_car):
                try:
                    j = load_json(path_ui_car)
                    self['carnames'][car] = j['name']
                    log(' ', car, j['name'])
                except Exception as e:
                    log('ERROR: loading', path_ui_car, e)
                    self['carnames'][car] = car
                    log(' ', car, '(error)')
        
        self.save_state()
    
    def get_carname(self, car):
        """Get fancy car name or fallback"""
        if car in self['carnames']:
            return self['carnames'][car]
        return car
    
    def sort_best_laps_by_carset(self):
        """Sort laps by carset for display"""
        laps = dict()
        
        for name in self['laps']:
            driver_laps = dict()
            
            for car in self['laps'][name]:
                c = self['laps'][name][car]
                
                if car in self['stesrac']:
                    carsets = self['stesrac'][car]
                else:
                    carsets = [CONFIG['uncategorized']]
                
                for carset in carsets:
                    if carset not in driver_laps:
                        driver_laps[carset] = []
                    
                    driver_laps[carset].append(
                        (c['time_ms'], (c['time'], name, car, c['count']))
                    )
            
            for carset in driver_laps:
                driver_laps[carset].sort(key=lambda x: x[0])
                
                if carset not in laps:
                    laps[carset] = []
                laps[carset].append(driver_laps[carset][0])
        
        for carset in laps:
            laps[carset].sort(key=lambda x: x[0])
        
        carsets_sorted = list(laps.keys())
        carsets_sorted.sort()
        
        # Move uncategorized to end
        for n in range(len(carsets_sorted)):
            if carsets_sorted[n] == CONFIG['uncategorized']:
                x = carsets_sorted.pop(n)
                carsets_sorted.append(x)
                break
        
        # Move venue carset to front
        for n in range(len(carsets_sorted)):
            if set(self['cars']) == set(self['carsets'][carsets_sorted[n]]):
                x = carsets_sorted.pop(n)
                carsets_sorted.insert(0, x)
                break
        
        laps_sorted = {i: laps[i] for i in carsets_sorted}
        
        return laps_sorted
    
    def sort_best_laps_by_name_and_car(self, min_laps=10):
        """Sort laps by name and car"""
        laps_by_car = dict()
        laps_by_name = dict()
        min_count = 0
        
        # Find min count threshold
        for name in self['laps']:
            for car in self['laps'][name]:
                min_count = max(min_count, min(self['laps'][name][car]['count'], min_laps))
        
        # Collect laps
        for name in self['laps']:
            for car in self['laps'][name]:
                c = deepcopy(self['laps'][name][car])
                c['car'] = car
                
                if c['count'] >= min_count:
                    if car not in laps_by_car:
                        laps_by_car[car] = dict()
                    
                    if name not in laps_by_car[car] or c['time_ms'] < laps_by_car[car][name]['time_ms']:
                        laps_by_car[car][name] = c
                    
                    if name not in laps_by_name or c['time_ms'] < laps_by_name[name]['time_ms']:
                        laps_by_name[name] = c
        
        # Build final lists
        all_bests = []
        for name in laps_by_name:
            all_bests.append(laps_by_name[name]['time_ms'])
        
        car_bests = dict()
        for car in laps_by_car:
            car_bests[car] = []
            for name in laps_by_car[car]:
                car_bests[car].append(laps_by_car[car][name]['time_ms'])
        
        # Sort everything
        laps_by_name = {k: v for k, v in sorted(laps_by_name.items(), key=lambda item: item[1]['time_ms'])}
        all_bests.sort()
        for car in laps_by_car:
            laps_by_car[car] = {k: v for k, v in sorted(laps_by_car[car].items(), key=lambda item: item[1]['time_ms'])}
            car_bests[car].sort()
        
        return all_bests, car_bests, min_count
    
    def get_stats_string(self, chars):
        """Generate statistics string"""
        if not self['laps'] or len(self['laps'].keys()) == 0:
            return None
        
        all_bests, car_bests, min_lap_count = self.sort_best_laps_by_name_and_car(10)
        
        lines = []
        N = len(all_bests)
        
        if N > 0:
            # Medians section
            tm = self.from_ms(median(all_bests), 1)
            lines.append('\n**Mid-Pace (' + str(min_lap_count) + '+ laps)**')
            
            if len(car_bests) > 1:
                lines.append('`' + tm + '` Driver Best (' + str(N) + ')')
            
            car_medians = []
            for car in car_bests:
                tm_ms = median(car_bests[car])
                tm = self.from_ms(tm_ms, 1)
                
                if car in self['carnames']:
                    car_medians.append((tm_ms, '`' + tm + '` ' + self['carnames'][car] + ' (' + str(len(car_bests[car])) + ')'))
                else:
                    log('ERROR: WTF extra car', car, 'not in self["carnames"]')
            
            car_medians.sort(key=lambda x: x[0])
            
            for tm_ms, line_string in car_medians:
                lines.append(line_string)
            
            # Trim if needed
            popped = False
            while len(lines) > 0 and len('\n'.join(lines)) > chars - 4:
                lines.pop(-1)
                popped = True
            
            if popped:
                lines.append('...')
            
            # Hotlap section
            all_bests, car_bests, min_lap_count = self.sort_best_laps_by_name_and_car(0)
            
            tm = self.from_ms(min(all_bests), 3)
            
            if len(car_bests) == 1:
                lines.append('\n**' + CONFIG['hotlap_title'] + '**')
            elif len(car_bests) > 1:
                lines.append('\n**' + CONFIG['hotlap_titles'] + '**')
                lines.append('`' + tm + '` Driver Best')
            
            car_mins = []
            for car in car_bests:
                tm_ms = min(car_bests[car])
                tm = self.from_ms(tm_ms, 3)
                
                if car in self['carnames']:
                    car_mins.append((tm_ms, '`' + tm + '` ' + self['carnames'][car]))
                else:
                    log('ERROR: WTF extra car', car, 'not in self["carnames"]')
            
            car_mins.sort(key=lambda x: x[0])
            
            for tm_ms, line_string in car_mins:
                lines.append(line_string)
            
            # Trim again if needed
            popped = False
            while len(lines) > 0 and len('\n'.join(lines)) > chars - 4:
                lines.pop(-1)
                popped = True
            
            if popped:
                lines.append('...')
        
        return '\n'.join(lines)
    
    def get_laps_string(self, chars):
        """Generate laps leaderboard string"""
        if not self['laps'] or len(self['laps'].keys()) == 0:
            return None
        
        laps = self.sort_best_laps_by_carset()
        
        lines = []
        for carset in laps:
            lines.append('\n**' + carset + '**')
            
            n = 1
            for x in laps[carset]:
                lines.append('**' + str(n) + '.** ' + self.fix_naughty_characters(
                    x[1][0] + ' ' + x[1][1] + ' (' + self.get_carname(x[1][2]) + ')'))
                n += 1
        
        # Trim to fit
        popped = False
        while len(lines) > 0 and len('\n'.join(lines)) > chars - 4:
            lines.pop(-1)
            popped = True
        
        if len(lines) == 0:
            return '\n...'
        
        if popped:
            lines.append('...')
        
        return ('\n'.join(lines)).strip()
    
    def get_onlines_string(self):
        """Generate online players string"""
        if len(self['online'].keys()) == 0:
            return None
        
        onlines = []
        n = 1
        online_namecars = []
        
        for name in self['online']:
            namecar = self.get_namecar_string(name, self['online'][name]['car'])
            onlines.append(str(n) + '. ' + self.fix_naughty_characters(namecar))
            online_namecars.append(namecar)
            
            self['seen_namecars'][namecar] = time.time()
            
            n += 1
        
        # Add previously online
        recents = []
        n = 1
        for namecar in self['seen_namecars'].keys():
            if not namecar in online_namecars:
                recents.append(str(n) + '. ' + self.fix_naughty_characters(namecar))
                n += 1
        
        s = '**' + '\n'.join(onlines) + '**'
        if len(recents):
            s = s + '\nPreviously Online:\n' + '\n'.join(recents)
        
        return s.strip()
    
    def get_namecar_string(self, name, car):
        """Format name + car string"""
        return name + ' (' + self.get_carname(car) + ')'
    
    def fix_naughty_characters(self, s):
        """Escape Discord formatting characters"""
        naughty = ['*', '_', '`']
        for n in naughty:
            s = s.replace(n, '\\' + n)
        return s
    
    def get_join_link(self):
        """Generate server join link"""
        global server_ip
        
        join_link = ''
        if CONFIG['join_link_finish']:
            join_link = '**Join**'
            
            if self['server_is_up']:
                try:
                    new_ip = requests.get('https://api.ipify.org', timeout=3).text
                    ipaddress.ip_address(new_ip)
                    server_ip = new_ip
                except Exception as e:
                    pass
                
                if server_ip:
                    join_link = '**[Join](<https://acstuff.ru/s/q:race/online/join?ip=' + server_ip + CONFIG['join_link_finish'] + '>)**'
        
        return join_link
    
    def send_state_messages(self):
        """Send all Discord messages"""
        log('send_state_messages()')
        
        join_link = self.get_join_link()
        
        # Check session timeout
        if self['session_end_time'] and \
           time.time() - self['session_end_time'] > CONFIG['online_timeout']:
            self['online_message_id'] = None
            self['seen_namecars'] = dict()
        
        onlines = self.get_onlines_string()
        
        # Build info message
        reg_string1 = ''
        top_timestamp = ''
        
        if self['qual_timestamp'] is not None and self['race_timestamp'] is not None:
            if self['qual_timestamp'] not in [0, None] and self['qual_timestamp'] > 0:
                tq = str(int(self['qual_timestamp']))
                tr = str(int(self['race_timestamp']))
                
                nametime1 = '<t:' + tq + ':D>'
                if CONFIG['registration_name']:
                    nametime1 = CONFIG['registration_name'] + ' ' + nametime1
                
                top_timestamp = '\n' + nametime1 + \
                               '\n`Qual:` ' + ' <t:' + tq + ':t>' + ' (<t:' + tq + ':R>)' + \
                               '\n`Race:` ' + ' <t:' + tr + ':t>' + ' (<t:' + tr + ':R>)' + \
                               '\n'
            
            if type(CONFIG['url_registration']) is str and self['number_slots']:
                nametime1 = '**[Register (' + str(self['number_registered']) + '/' + str(self['number_slots']) + ')](' + CONFIG['url_registration'] + ')**'
                reg_string1 = nametime1
        
        footer = '\n' + reg_string1 + CONFIG['laps_footer'] + join_link
        
        track_name = self['track_name']
        if not track_name:
            track_name = self['track']
        if not track_name:
            track_name = 'Unknown Track?'
        
        title = ''
        carset = None
        if self['carset']:
            carset = str(self['carset'])
        elif len(self['carnames']) == 1:
            carset = str(list(self['carnames'].values())[0])
        
        if carset:
            title = title + carset.upper() + ' @ '
        if track_name:
            title = title + track_name.upper()
        if CONFIG['url_event_info'] not in [None, False, '']:
            title = '[' + title + '](' + CONFIG['url_event_info'] + ')'
        
        body1 = CONFIG['venue_header'] + '**__' + title + '__**'
        body1 = body1 + top_timestamp + CONFIG['venue_subheader']
        
        body2 = ''
        if onlines:
            body2 = '\n**' + CONFIG['online_header'] + '**\n' + onlines
            color = CONFIG['color_onlines']
        elif self['server_is_up']:
            color = CONFIG['color_server_up']
        else:
            color = 0
        
        # Get laps string based on mode
        N = 4070 - len(body1 + body2 + footer)
        if CONFIG['leaderboard_mode'] == 1:
            laps = self.get_laps_string(N)
        elif CONFIG['leaderboard_mode'] == 2:
            laps = self.get_stats_string(N)
        else:
            laps = None
        
        if CONFIG['debug'] and laps:
            log('LAPS\n' + laps)
        
        if laps and len(laps):
            body1 = body1 + '\n' + laps + '\n'
        
        # Send info message
        self['laps_message_id'] = self.send_message(
            self.webhook_info, '', body1, body2, footer,
            self['laps_message_id'], color=color,
            username=CONFIG['bot_name']
        )
        
        if self['laps_message_id'] is None:
            log('DID NOT EDIT OR SEND LAPS MESSAGE')
        
        # Send online message if needed
        if onlines:
            self['session_end_time'] = 0
            
            body1 = '**' + CONFIG['online_header'] + '**\n' + onlines + '\n'
            
            self['online_message_id'] = self.send_message(
                self.webhook_online, '', body1, '',
                CONFIG['online_footer'] + join_link, self['online_message_id'],
                username=CONFIG['bot_name']
            )
            
            if self['online_message_id'] is None:
                log('DID NOT EDIT OR SEND ONLINES')
        else:
            self.end_session()
        
        self.save_state()
    
    def end_session(self):
        """End the current session"""
        if not hasattr(self, 'state'):
            return
        
        log('end_session()', self['seen_namecars'].keys(), self['online_message_id'])
        
        if self['online_message_id']:
            errbody = []
            n = 1
            for namecar in self['seen_namecars'].keys():
                errbody.append(str(n) + '. ' + namecar)
                n += 1
            
            if len(errbody):
                body1 = CONFIG['session_complete_header'] + '\n\nParticipants:\n' + '\n'.join(errbody) + '\n'
                
                self['online_message_id'] = self.send_message(
                    self.webhook_online, '', body1, '', '\n' + CONFIG['online_footer'] + self.get_join_link(),
                    self['online_message_id'], 0, username=CONFIG['bot_name']
                )
                
                self['session_end_time'] = time.time()
            else:
                log('**** GOSH DARN IT, LOST THE SEEN_NAMECARS AGAIN! WTF.', self['seen_namecars'].keys())
                self.delete_message(self.webhook_online, self['online_message_id'])
                self['online_message_id'] = None
                self['session_end_time'] = 0
    
    def delete_message(self, webhook, message_id):
        """Delete Discord message"""
        if not type(message_id) == int or not message_id:
            return
        
        log('delete_message()')
        if webhook and message_id:
            try:
                webhook.delete_message(message_id)
            except:
                pass
    
    def send_message(self, webhook, message='', body1='', body2='', footer='', 
                    message_id=None, color=15548997, username=None):
        """Send or edit Discord message with truncation logic"""
        log('\nsend_message()')
        
        if not webhook:
            return
        
        # Handle truncation exactly like original
        if len(body1 + body2 + footer) > 4070:
            if len(body2 + footer) > 4070:
                body = body2[0:4070 - len(footer)] + ' ...' + footer
            else:
                body = body1[0:4070 - len(body2) - len(footer)] + ' ...' + body2 + footer
        else:
            body = body1 + body2 + footer
        
        if len(message) > 2000:
            message = message[0:1995] + '\n...'
        
        if CONFIG['debug']:
            log(message)
            log(body)
        
        e = discord.Embed()
        e.color = color
        e.description = body
        
        if message_id:
            try:
                if len(e.description):
                    webhook.edit_message(message_id, content=message, embeds=[e])
                else:
                    webhook.edit_message(message_id, content=message, embeds=[])
                
                if message_id in self.message_failure_timestamps.keys():
                    self.message_failure_timestamps.pop(message_id)
            
            except Exception as x:
                if not message_id in self.message_failure_timestamps.keys():
                    self.message_failure_timestamps[message_id] = time.time()
                
                log('WHOOPS could not edit message', message_id, e, x, 'dt =',
                    time.time() - self.message_failure_timestamps[message_id])
                
                if time.time() - self.message_failure_timestamps[message_id] > 10:
                    log('  Timeout! Popping id...')
                    self.message_failure_timestamps.pop(message_id)
                    
                    try:
                        log('  Trying to send a new message...')
                        
                        if len(e.description):
                            message_id = webhook.send(message, embeds=[e],
                                                     username=username, wait=True).id
                        else:
                            message_id = webhook.send(message, embeds=[],
                                                     username=username, wait=True).id
                        
                        log('  Sent id', message_id)
                    
                    except Exception as x:
                        log('  WHOOPS (CRITICAL) could not send ', x)
                        message_id = None
                
                else:
                    time.sleep(3)
                    message_id = self.send_message(
                        webhook, message, body1, body2,
                        footer, message_id, color,
                        username=username
                    )
        
        else:
            try:
                if len(e.description):
                    message_id = webhook.send(message, embeds=[e], username=username, wait=True).id
                else:
                    message_id = webhook.send(message, embeds=[], username=username, wait=True).id
            except Exception as x:
                log('WHOOPS could not send message', message_id, e, x)
                message_id = None
        
        return message_id

# Create and run the monitor
if __name__ == "__main__":
    self = Monitor()