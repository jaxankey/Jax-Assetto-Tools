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
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

# Change to the directory of this script
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Load configuration
def load_config():
    """Load configuration from monitor.ini files"""
    config = {}
    
    # Default values
    defaults = {
        'server_manager_premium_mode': True,
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
    
    # Load from ini files
    exec(open('monitor.ini', 'r', encoding="utf8").read(), {}, config)
    if os.path.exists('monitor.ini.private'):
        exec(open('monitor.ini.private', 'r', encoding="utf8").read(), {}, config)
    
    # Apply defaults for missing values
    for key, value in defaults.items():
        if key not in config:
            config[key] = value
    
    return config

CONFIG = load_config()

class Logger:
    """Simple logger with timestamp"""
    @staticmethod
    def log(*args):
        print(datetime.datetime.now(), *args)

class TimeUtils:
    """Utility class for time-related operations"""
    
    @staticmethod
    def from_ms(t: float, decimals: int = 3) -> str:
        """Convert milliseconds to formatted string (M:SS.mmm)"""
        t = round(t * 0.1**(3-decimals)) * 10**(3-decimals)
        m = int(t / 60000)
        s = (t - m * 60000) * 0.001
        s_int = int(s)
        s_frac = round((s % 1) * 10**decimals)
        return '%d:%02d.%0*d' % (m, s_int, decimals, s_frac)
    
    @staticmethod
    def to_ms(s: str) -> int:
        """Convert time string (M:SS:mmm) to milliseconds"""
        parts = s.split(':')
        return int(parts[0]) * 60000 + int(parts[1]) * 1000 + int(parts[2])
    
    @staticmethod
    def auto_week(t0: float, qual_minutes: int) -> float:
        """Auto-increment week for recurring events"""
        now = time.time()
        dt = (qual_minutes + 30) * 60
        
        if t0 + dt > now:
            return t0
        
        week = datetime.timedelta(days=7)
        tc = datetime.datetime.fromtimestamp(t0)
        original_hour = tc.hour
        
        while tc.timestamp() + dt > now:
            tc -= week
        while tc.timestamp() + dt < now:
            tc += week
        
        # Handle daylight savings
        hour = datetime.timedelta(hours=1)
        for t in [tc, tc + hour, tc - hour]:
            if t.hour == original_hour:
                return t.timestamp()
        
        return tc.timestamp()

class FileUtils:
    """Utility class for file operations"""
    
    @staticmethod
    def load_json(path: str, suppress_warning: bool = False) -> Optional[dict]:
        """Safely load JSON file"""
        if path is None:
            return None
        
        if not os.path.exists(path):
            if not suppress_warning:
                Logger.log('load_json: could not find', path)
            return None
        
        try:
            with open(path, 'r', encoding='utf8', errors='replace') as f:
                return json.load(f, strict=False)
        except Exception as e:
            Logger.log('ERROR: Could not load', path)
            Logger.log(e)
            return None
    
    @staticmethod
    def save_json(path: str, data: dict):
        """Save dictionary to JSON file"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding="utf8") as f:
            json.dump(data, f, indent=2)

class NetworkUtils:
    """Utility class for network operations"""
    
    @staticmethod
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
    
    @staticmethod
    def get_public_ip(fallback: Optional[str] = None) -> Optional[str]:
        """Get public IP address with fallback"""
        try:
            new_ip = requests.get('https://api.ipify.org', timeout=3).text
            ipaddress.ip_address(new_ip)  # Validate
            return new_ip
        except:
            return fallback

@dataclass
class ServerState:
    """Container for server state data"""
    online: Dict[str, dict] = field(default_factory=dict)
    online_message_id: Optional[int] = None
    one_hour_message_id: Optional[int] = None
    qualifying_message_id: Optional[int] = None
    timestamp: Optional[str] = None
    qual_timestamp: Optional[float] = None
    race_timestamp: Optional[float] = None
    number_slots: Optional[int] = None
    number_registered: Optional[int] = None
    registration: Dict[str, list] = field(default_factory=dict)
    track_name: Optional[str] = None
    track: Optional[str] = None
    layout: Optional[str] = None
    laps_message_id: Optional[int] = None
    down_message_id: Optional[int] = None
    laps: Dict[str, dict] = field(default_factory=dict)
    naughties: Dict[str, dict] = field(default_factory=dict)
    carset: Optional[str] = None
    carsets: Dict[str, list] = field(default_factory=dict)
    stesrac: Dict[str, list] = field(default_factory=dict)
    cars: List[str] = field(default_factory=list)
    carnames: Dict[str, str] = field(default_factory=dict)
    seen_namecars: Dict[str, float] = field(default_factory=dict)
    session_end_time: float = 0
    script_one_hour_done: bool = False
    script_qualifying_done: bool = False
    tcp_data_port_open: bool = False
    server_is_up: bool = False
    session_type: Optional[str] = None

class LapProcessor:
    """Handles lap time processing and statistics"""
    
    def __init__(self, state: ServerState):
        self.state = state
    
    def process_live_timing_lap(self, guid: str, driver_data: dict, cars_data: dict) -> bool:
        """Process lap from live timing data. Returns True if lap was updated."""
        name = driver_data['CarInfo']['DriverName']
        lap_updated = False
        
        for car in cars_data:
            if car not in self.state.cars:
                continue
            
            best = cars_data[car]['BestLap'] * 1e-6  # Convert from nanoseconds
            count = cars_data[car]['NumLaps']
            
            if best and best > 100:  # Minimum 100ms to catch glitches
                if self._should_update_lap(name, car, best, count):
                    self._update_lap(name, car, best, count)
                    lap_updated = True
        
        return lap_updated
    
    def _should_update_lap(self, name: str, car: str, best: float, count: int) -> bool:
        """Check if lap should be updated"""
        if name not in self.state.laps:
            return True
        if car not in self.state.laps[name]:
            return True
        
        existing = self.state.laps[name][car]
        return (best < existing['time_ms'] or 
                'count' not in existing or 
                existing['count'] != count)
    
    def _update_lap(self, name: str, car: str, best: float, count: int):
        """Update lap record"""
        if name not in self.state.laps:
            self.state.laps[name] = {}
        
        self.state.laps[name][car] = {
            'time': TimeUtils.from_ms(best),
            'time_ms': best,
            'cuts': 0,
            'count': count,
            'track': self.state.track,
            'layout': self.state.layout
        }
        Logger.log('Lap:', name, car, self.state.laps[name][car])
    
    def get_sorted_laps_by_carset(self) -> dict:
        """Get laps sorted by carset for leaderboard display"""
        laps = {}
        
        for name in self.state.laps:
            driver_laps = {}
            
            for car in self.state.laps[name]:
                c = self.state.laps[name][car]
                
                # Get carsets for this car
                carsets = self.state.stesrac.get(car, [CONFIG['uncategorized']])
                
                for carset in carsets:
                    if carset not in driver_laps:
                        driver_laps[carset] = []
                    driver_laps[carset].append(
                        (c['time_ms'], (c['time'], name, car, c['count']))
                    )
            
            # Sort each carset and add best to main laps
            for carset in driver_laps:
                driver_laps[carset].sort(key=lambda x: x[0])
                if carset not in laps:
                    laps[carset] = []
                laps[carset].append(driver_laps[carset][0])
        
        # Sort all carsets
        for carset in laps:
            laps[carset].sort(key=lambda x: x[0])
        
        # Order carsets (venue first, uncategorized last)
        carsets_sorted = sorted(laps.keys())
        
        # Move uncategorized to end
        if CONFIG['uncategorized'] in carsets_sorted:
            carsets_sorted.remove(CONFIG['uncategorized'])
            carsets_sorted.append(CONFIG['uncategorized'])
        
        # Move venue carset to front
        for carset in carsets_sorted[:]:
            if carset in self.state.carsets and set(self.state.cars) == set(self.state.carsets[carset]):
                carsets_sorted.remove(carset)
                carsets_sorted.insert(0, carset)
                break
        
        return {carset: laps[carset] for carset in carsets_sorted if carset in laps}
    
    def get_sorted_laps_by_carset(self) -> dict:
        """Get laps sorted by carset for leaderboard display"""
        laps = {}
        
        for name in self.state.laps:
            driver_laps = {}
            
            for car in self.state.laps[name]:
                c = self.state.laps[name][car]
                
                # Get carsets for this car
                carsets = self.state.stesrac.get(car, [CONFIG['uncategorized']])
                
                for carset in carsets:
                    if carset not in driver_laps:
                        driver_laps[carset] = []
                    driver_laps[carset].append(
                        (c['time_ms'], (c['time'], name, car, c['count']))
                    )
            
            # Sort each carset and add best to main laps
            for carset in driver_laps:
                driver_laps[carset].sort(key=lambda x: x[0])
                if carset not in laps:
                    laps[carset] = []
                laps[carset].append(driver_laps[carset][0])
        
        # Sort all carsets
        for carset in laps:
            laps[carset].sort(key=lambda x: x[0])
        
        # Order carsets (venue first, uncategorized last)
        carsets_sorted = sorted(laps.keys())
        
        # Move uncategorized to end
        if CONFIG['uncategorized'] in carsets_sorted:
            carsets_sorted.remove(CONFIG['uncategorized'])
            carsets_sorted.append(CONFIG['uncategorized'])
        
        # Move venue carset to front
        for carset in carsets_sorted[:]:
            if carset in self.state.carsets and set(self.state.cars) == set(self.state.carsets[carset]):
                carsets_sorted.remove(carset)
                carsets_sorted.insert(0, carset)
                break
        
        return {carset: laps[carset] for carset in carsets_sorted if carset in laps}
    
    def get_sorted_laps(self, min_laps: int = 10) -> Tuple[List[float], Dict[str, List[float]], int]:
        """Get sorted lap times by driver and car"""
        all_bests = []
        car_bests = {}
        min_count = 0
        
        # Calculate minimum lap count
        for name in self.state.laps:
            for car in self.state.laps[name]:
                min_count = max(min_count, min(self.state.laps[name][car]['count'], min_laps))
        
        # Collect best laps
        for name in self.state.laps:
            for car in self.state.laps[name]:
                lap_data = deepcopy(self.state.laps[name][car])
                
                if lap_data['count'] >= min_count:
                    # Track overall best for this driver
                    all_bests.append(lap_data['time_ms'])
                    
                    # Track car-specific bests
                    if car not in car_bests:
                        car_bests[car] = []
                    car_bests[car].append(lap_data['time_ms'])
        
        # Sort everything
        all_bests.sort()
        for car in car_bests:
            car_bests[car].sort()
        
        return all_bests, car_bests, min_count

class MessageFormatter:
    """Handles message formatting for Discord"""
    
    def __init__(self, state: ServerState, lap_processor: LapProcessor):
        self.state = state
        self.lap_processor = lap_processor
    
    def fix_naughty_characters(self, s: str) -> str:
        """Escape Discord formatting characters"""
        for char in ['*', '_', '`']:
            s = s.replace(char, '\\' + char)
        return s
    
    def get_carname(self, car: str) -> str:
        """Get fancy car name or fallback to directory name"""
        return self.state.carnames.get(car, car)
    
    def get_onlines_string(self) -> Optional[str]:
        """Format list of online players"""
        if not self.state.online:
            return None
        
        onlines = []
        online_namecars = []
        
        # Current online players
        for n, name in enumerate(self.state.online, 1):
            namecar = f"{name} ({self.get_carname(self.state.online[name]['car'])})"
            onlines.append(f"{n}. {self.fix_naughty_characters(namecar)}")
            online_namecars.append(namecar)
            self.state.seen_namecars[namecar] = time.time()
        
        # Previously online players
        recents = []
        for n, namecar in enumerate(
            (nc for nc in self.state.seen_namecars if nc not in online_namecars), 1
        ):
            recents.append(f"{n}. {self.fix_naughty_characters(namecar)}")
        
        result = '**' + '\n'.join(onlines) + '**'
        if recents:
            result += '\nPreviously Online:\n' + '\n'.join(recents)
        
        return result.strip()
    
    def get_laps_string(self, max_chars: int) -> Optional[str]:
        """Generate formatted lap times string for Discord"""
        if not self.state.laps:
            return None
        
        laps = self.lap_processor.get_sorted_laps_by_carset()
        
        lines = []
        for carset in laps:
            lines.append(f'\n**{carset}**')
            
            for n, (_, (time, name, car, _)) in enumerate(laps[carset], 1):
                namecar = f"{time} {name} ({self.get_carname(car)})"
                lines.append(f'**{n}.** {self.fix_naughty_characters(namecar)}')
        
        # Trim to fit character limit
        while lines and len('\n'.join(lines)) > max_chars - 4:
            lines.pop(-1)
        
        if not lines:
            return '\n...'
        
        if lines and lines[-1] not in ['...', '']:
            lines.append('...')
        
        return '\n'.join(lines).strip()
    
    def get_stats_string(self, max_chars: int) -> Optional[str]:
        """Generate statistics string for lap times"""
        if not self.state.laps:
            return None
        
        all_bests, car_bests, min_lap_count = self.lap_processor.get_sorted_laps(10)
        
        if not all_bests:
            return None
        
        lines = []
        lines.append(f'\n**Mid-Pace ({min_lap_count}+ laps)**')
        
        # Overall median
        if len(car_bests) > 1:
            tm = TimeUtils.from_ms(median(all_bests), 1)
            lines.append(f'`{tm}` Driver Best ({len(all_bests)})')
        
        # Car-specific medians
        car_medians = sorted(
            [(median(car_bests[car]), car, len(car_bests[car])) 
             for car in car_bests],
            key=lambda x: x[0]
        )
        
        for tm_ms, car, count in car_medians:
            tm = TimeUtils.from_ms(tm_ms, 1)
            lines.append(f'`{tm}` {self.get_carname(car)} ({count})')
        
        # Hotlap section
        lines.append(f'\n**{CONFIG["hotlap_titles"] if len(car_bests) > 1 else CONFIG["hotlap_title"]}**')
        
        if len(car_bests) > 1:
            tm = TimeUtils.from_ms(min(all_bests), 3)
            lines.append(f'`{tm}` Driver Best')
        
        # Car-specific minimums
        car_mins = sorted(
            [(min(car_bests[car]), car) for car in car_bests],
            key=lambda x: x[0]
        )
        
        for tm_ms, car in car_mins:
            tm = TimeUtils.from_ms(tm_ms, 3)
            lines.append(f'`{tm}` {self.get_carname(car)}')
        
        # Trim to fit character limit
        while lines and len('\n'.join(lines)) > max_chars - 4:
            lines.pop(-1)
        
        if lines and lines[-1] != '...':
            lines.append('...')
        
        return '\n'.join(lines)
    
    def get_join_link(self) -> str:
        """Generate join link for the server"""
        if not CONFIG['join_link_finish']:
            return ''
        
        if not self.state.server_is_up:
            return '**Join**'
        
        server_ip = NetworkUtils.get_public_ip(CONFIG['server_ip'])
        if server_ip:
            CONFIG['server_ip'] = server_ip
            return f'**[Join](<https://acstuff.ru/s/q:race/online/join?ip={server_ip}{CONFIG["join_link_finish"]}>)**'
        
        return '**Join**'

class DiscordMessenger:
    """Handles Discord webhook messaging"""
    
    def __init__(self):
        self.webhook_online = None
        self.webhook_info = None
        self.message_failure_timestamps = {}
        
        if CONFIG['url_webhook_online']:
            self.webhook_online = discord.SyncWebhook.from_url(CONFIG['url_webhook_online'])
        if CONFIG['url_webhook_info']:
            self.webhook_info = discord.SyncWebhook.from_url(CONFIG['url_webhook_info'])
    
    def send_message(self, webhook, message: str = '', body: str = '', 
                    message_id: Optional[int] = None, color: int = 15548997,
                    username: Optional[str] = None) -> Optional[int]:
        """Send or edit Discord message"""
        if not webhook:
            return None
        
        # Trim message to Discord limits
        if len(body) > 4070:
            body = body[:4067] + '...'
        if len(message) > 2000:
            message = message[:1997] + '...'
        
        embed = discord.Embed(color=color, description=body) if body else None
        embeds = [embed] if embed else []
        
        if message_id:
            try:
                webhook.edit_message(message_id, content=message, embeds=embeds)
                self.message_failure_timestamps.pop(message_id, None)
                return message_id
            except Exception as e:
                Logger.log(f'Could not edit message {message_id}: {e}')
                
                # Retry logic
                if message_id not in self.message_failure_timestamps:
                    self.message_failure_timestamps[message_id] = time.time()
                
                if time.time() - self.message_failure_timestamps[message_id] > 10:
                    self.message_failure_timestamps.pop(message_id)
                    message_id = None
                else:
                    return None
        
        # Send new message
        if not message_id:
            try:
                response = webhook.send(message, embeds=embeds, username=username, wait=True)
                return response.id
            except Exception as e:
                Logger.log(f'Could not send message: {e}')
                return None
    
    def delete_message(self, webhook, message_id: Optional[int]):
        """Delete Discord message"""
        if webhook and message_id:
            try:
                webhook.delete_message(message_id)
            except:
                pass

class ACServerMonitor:
    """Main monitor class for AC server"""
    
    def __init__(self):
        self.state = ServerState()
        self.lap_processor = LapProcessor(self.state)
        self.formatter = MessageFormatter(self.state, self.lap_processor)
        self.messenger = DiscordMessenger()
        self.first_run = True
        self.old_registration = {}
        self.live_timings = None
        self.time_last_live_timings_fail = 0
        
        # Load existing state if available
        self.load_state()
        
        # Start monitoring
        self.run()
    
    def load_state(self):
        """Load saved state from disk"""
        state_path = os.path.join('web', 'state.json')
        if os.path.exists(state_path):
            try:
                saved_state = FileUtils.load_json(state_path)
                if saved_state:
                    # Update state attributes from saved data
                    for key, value in saved_state.items():
                        if hasattr(self.state, key):
                            setattr(self.state, key, value)
                    
                    self.old_registration = self.state.registration.copy()
                    Logger.log('Loaded state.json')
                    self.load_ui_data()
            except Exception as e:
                Logger.log(f'Error loading state.json: {e}')
    
    def save_state(self):
        """Save current state to disk"""
        state_dict = {
            key: getattr(self.state, key) 
            for key in vars(self.state) 
            if not key.startswith('_')
        }
        FileUtils.save_json(os.path.join('web', 'state.json'), state_dict)
        Logger.log('Saved state')
    
    def reset_state(self):
        """Reset state to defaults"""
        self.end_session()
        
        # Preserve certain values
        down_message_id = self.state.down_message_id
        laps_message_id = self.state.laps_message_id if CONFIG['venue_recycle_message'] else None
        
        # Reset state
        self.state = ServerState()
        self.state.down_message_id = down_message_id
        self.state.laps_message_id = laps_message_id
    
    def run(self):
        """Main monitoring loop"""
        Logger.log('Starting monitor in premium mode')
        
        # Initial sync
        self.get_latest_data()
        if self.state.number_registered is not None:
            self.send_state_messages()
            self.first_run = False
        
        # Main loop
        while True:
            self.get_latest_data()
            time.sleep(3)
    
    def get_latest_data(self):
        """Get latest data from server and update state"""
        changes = {
            'laps_or_onlines': False,
            'event_time_slots': False,
            'track': False,
            'carset': False,
            'server_state': False
        }
        
        # Check server status
        self.state.tcp_data_port_open = NetworkUtils.port_is_open('localhost', CONFIG['tcp_data_port'])
        
        if not self.state.tcp_data_port_open:
            self.handle_server_down(changes)
        else:
            self.handle_server_up(changes)
        
        # Check for any changes and update messages
        if self.first_run or any(changes.values()):
            self.send_state_messages()
            self.first_run = False
    
    def handle_server_down(self, changes: dict):
        """Handle server down state"""
        if not CONFIG['no_down_warning'] and not self.state.down_message_id:
            self.state.down_message_id = self.messenger.send_message(
                self.messenger.webhook_info,
                body='Server is down. I need an adult! :(',
                username=CONFIG['bot_name']
            )
            self.save_state()
        
        if self.state.server_is_up:
            Logger.log('SERVER IS NOW DOWN!')
            changes['server_state'] = True
            self.end_session()
            self.state.online_message_id = None
            
            if CONFIG['script_server_down']:
                Logger.log(f'Running server down script: {CONFIG["script_server_down"]}')
                try:
                    os.system(CONFIG['script_server_down'])
                except Exception as e:
                    Logger.log(f'Error running script: {e}')
            
            self.state.seen_namecars = {}
            self.state.online = {}
        
        self.state.server_is_up = False
        
        # Still process race.json if available
        if CONFIG['path_race_json']:
            self.process_race_json(changes)
    
    def handle_server_up(self, changes: dict):
        """Handle server up state"""
        if not self.state.server_is_up:
            Logger.log('SERVER IS BACK UP!')
            changes['server_state'] = True
            
            if CONFIG['script_server_up']:
                Logger.log(f'Running server up script: {CONFIG["script_server_up"]}')
                try:
                    os.system(CONFIG['script_server_up'])
                except Exception as e:
                    Logger.log(f'Error running script: {e}')
        
        self.state.server_is_up = True
        
        if self.state.down_message_id:
            self.messenger.delete_message(self.messenger.webhook_info, self.state.down_message_id)
            self.state.down_message_id = None
            self.save_state()
        
        # Get server details
        details = self.get_server_details()
        if details:
            self.process_online_players(details, changes)
        
        # Process race.json
        race_json = self.process_race_json(changes)
        
        # Update venue if needed
        self.update_venue(details, race_json, changes)
        
        # Process live timings
        self.process_live_timings(changes)
        
        # Handle scheduled messages
        self.handle_scheduled_messages()
    
    def get_server_details(self) -> Optional[dict]:
        """Get details from server API"""
        if not CONFIG['http_port']:
            return None
        
        url = f'http://localhost:{CONFIG["http_port"]}/api/details'
        try:
            response = urllib.request.urlopen(url, timeout=5).read()
            return json.loads(response, strict=False)
        except Exception as e:
            Logger.log(f'Could not get server details: {e}')
            return None
    
    def process_online_players(self, details: dict, changes: dict):
        """Process online player information"""
        old_online = set((name, self.state.online[name]['car']) for name in self.state.online)
        new_online = set()
        
        for car in details.get('players', {}).get('Cars', []):
            if car['IsConnected'] and not car['DriverName'].startswith('[Not Connected]'):
                new_online.add((car['DriverName'], car['Model']))
        
        if new_online != old_online:
            Logger.log(f'Online players changed: {new_online}')
            changes['laps_or_onlines'] = True
            
            self.state.online = {
                name: {'car': car} for name, car in new_online
            }
    
    def process_race_json(self, changes: dict) -> Optional[dict]:
        """Process race.json file for registration and event info"""
        race_json = FileUtils.load_json(CONFIG['path_race_json'])
        if not race_json:
            return None
        
        if 'SignUpForm' not in race_json:
            return race_json
        
        # Process registrations
        current_registrants = {}
        
        if race_json.get('SignUpForm', {}).get('Enabled') and 'Responses' in race_json['SignUpForm']:
            for r in race_json['SignUpForm']['Responses']:
                if r.get('Status') == 'Accepted' and r.get('GUID'):
                    current_registrants[r['GUID']] = [
                        r['Name'],
                        r.get('Car', r.get('Model', 'unknown'))
                    ]
        elif race_json.get('Classes') and race_json['Classes']:
            for key, r in race_json['Classes'][0].get('Entrants', {}).items():
                if r.get('GUID'):
                    current_registrants[r['GUID']] = [r['Name'], r['Model']]
        
        # Announce new registrations
        old_reg = self.old_registration if hasattr(self, 'old_registration') else self.state.registration
        for guid in set(current_registrants.keys()) - set(old_reg.keys()):
            driver = current_registrants[guid]
            carname = self.formatter.get_carname(driver[1])
            article = 'an ' if carname[0].lower() in 'aeiou' else 'a '
            
            self.messenger.send_message(
                self.messenger.webhook_online,
                f"{driver[0]} registered in {article}{carname}",
                username=CONFIG['bot_name']
            )
        
        if hasattr(self, 'old_registration'):
            del self.old_registration
        
        self.state.registration = current_registrants
        
        # Update event parameters
        if race_json.get('Events'):
            event = race_json['Events'][0]
            tq = dateutil.parser.parse(event['Scheduled']).timestamp()
            qual_minutes = event['RaceSetup']['Sessions']['QUALIFY']['Time']
            tr = tq + qual_minutes * 60
            nr = len(current_registrants)
            ns = len(event['EntryList'])
            
            if (tq != self.state.qual_timestamp or 
                tr != self.state.race_timestamp or 
                nr != self.state.number_registered or 
                ns != self.state.number_slots):
                
                changes['event_time_slots'] = True
                self.state.qual_timestamp = tq
                self.state.race_timestamp = tr
                self.state.number_registered = nr
                self.state.number_slots = ns
        
        return race_json
    
    def update_venue(self, details: Optional[dict], race_json: Optional[dict], changes: dict):
        """Update venue information if changed"""
        # Get track and cars info
        track, layout, cars = self.extract_venue_info(details, race_json)
        
        # Check for changes
        carset_changed = len(set(cars).intersection(self.state.cars)) == 0
        track_changed = (track != self.state.track or layout != self.state.layout)
        
        if track_changed or carset_changed:
            if track_changed:
                Logger.log('Track changed')
            if carset_changed:
                Logger.log('Carset changed')
            
            changes['track'] = track_changed
            changes['carset'] = carset_changed
            
            self.new_venue(track, layout, cars)
            
            if not self.first_run and CONFIG['path_live_timings']:
                if os.path.exists(CONFIG['path_live_timings']):
                    os.remove(CONFIG['path_live_timings'])
            self.live_timings = None
        
        self.state.cars = cars
    
    def extract_venue_info(self, details: Optional[dict], race_json: Optional[dict]) -> Tuple[str, str, List[str]]:
        """Extract track, layout and cars from available data"""
        track = 'Unknown Track'
        layout = ''
        cars = []
        
        if race_json is None:
            # Use details if available
            if details:
                track_layout = details['track'].split('-')
                if len(track_layout) >= 2:
                    layout = track_layout.pop(-1)
                else:
                    layout = ''
                track = '-'.join(track_layout)
                cars = details.get('cars', [])
        else:
            # Use race_json for more reliable info
            if 'Events' in race_json:
                rs = race_json['Events'][0]['RaceSetup']
            else:
                rs = race_json['RaceConfig']
            
            cars = rs['Cars'].split(';') if rs.get('Cars') else []
            track = rs.get('Track', 'Unknown Track')
            layout = rs.get('TrackLayout', '')
        
        # Handle CSP/ACSM path additions
        if '/' in track:
            track = track.split('/')[-1]
        
        return track, layout, cars
    
    def new_venue(self, track: str, layout: str, cars: List[str]):
        """Initialize new venue"""
        Logger.log(f'New venue: {track} - {layout}')
        
        # Save current state before reset
        self.save_state()
        
        # Reset state preserving certain values
        down_message_id = self.state.down_message_id
        laps_message_id = self.state.laps_message_id if CONFIG['venue_recycle_message'] else None
        
        self.reset_state()
        
        self.state.down_message_id = down_message_id
        self.state.laps_message_id = laps_message_id
        self.state.track = track
        self.state.layout = layout
        self.state.cars = cars
        self.state.timestamp = time.strftime('%Y-%m-%d_%H.%M.%S', time.localtime())
        
        self.load_ui_data()
        self.save_state()
    
    def load_ui_data(self):
        """Load UI data for track and cars"""
        Logger.log('Loading UI data')
        
        if not os.path.exists(CONFIG['path_ac']):
            Logger.log(f'ERROR: path_ac does not exist: {CONFIG["path_ac"]}')
            return
        
        # Load track UI data
        if self.state.layout:
            path_ui_track = os.path.join(
                CONFIG['path_ac'], 'content', 'tracks',
                self.state.track, 'ui', self.state.layout, 'ui_track.json'
            )
        else:
            path_ui_track = os.path.join(
                CONFIG['path_ac'], 'content', 'tracks',
                self.state.track, 'ui', 'ui_track.json'
            )
        
        ui_track = FileUtils.load_json(path_ui_track, suppress_warning=True)
        if ui_track:
            self.state.track_name = ui_track.get('name', self.state.track)
        else:
            self.state.track_name = self.state.track
        
        # Load carsets
        self.load_carsets()
        
        # Load car names
        self.state.carnames = {}
        for car in self.state.cars:
            path_ui_car = os.path.join(
                CONFIG['path_ac'], 'content', 'cars', car, 'ui', 'ui_car.json'
            )
            ui_car = FileUtils.load_json(path_ui_car, suppress_warning=True)
            if ui_car:
                self.state.carnames[car] = ui_car.get('name', car)
                Logger.log(f'  {car}: {self.state.carnames[car]}')
            else:
                self.state.carnames[car] = car
        
        self.save_state()
    
    def load_carsets(self):
        """Load carset information"""
        path_carsets = os.path.join(CONFIG['path_ac'], 'carsets')
        if not os.path.exists(path_carsets):
            return
        
        import glob
        carset_paths = sorted(glob.glob(os.path.join(path_carsets, '*.json')))
        
        self.state.carsets = {}
        self.state.stesrac = {}  # Reverse lookup
        
        for path in carset_paths:
            carset_data = FileUtils.load_json(path)
            if not carset_data:
                continue
            
            name = os.path.splitext(os.path.basename(path))[0]
            self.state.carsets[name] = list(carset_data.get('cars', []))
            
            # Build reverse lookup
            for car in self.state.carsets[name]:
                if car not in self.state.stesrac:
                    self.state.stesrac[car] = []
                self.state.stesrac[car].append(name)
            
            # Check if this matches current carset
            if set(self.state.carsets[name]) == set(self.state.cars):
                self.state.carset = name
    
    def process_live_timings(self, changes: dict):
        """Process live timing data"""
        if not CONFIG['path_live_timings']:
            return
        
        # Skip if recently failed
        if time.time() - self.time_last_live_timings_fail < 600:
            return
        
        self.live_timings = FileUtils.load_json(CONFIG['path_live_timings'], suppress_warning=True)
        if not self.live_timings:
            self.time_last_live_timings_fail = time.time()
            return
        
        # Bootstrap venue from live_timings if needed
        if (not self.state.laps or not self.state.track) and self.live_timings.get('Track'):
            if not self.state.track:
                Logger.log('Bootstrapping venue from live_timings')
                self.state.track = self.live_timings['Track']
                self.state.layout = self.live_timings.get('TrackLayout', '')
        
        # Process if track matches
        if (self.live_timings.get('Track') == self.state.track and 
            self.live_timings.get('TrackLayout') == self.state.layout):
            
            for guid, driver_data in self.live_timings.get('Drivers', {}).items():
                if self.lap_processor.process_live_timing_lap(
                    guid, driver_data, driver_data.get('Cars', {})
                ):
                    changes['laps_or_onlines'] = True
    
    def handle_scheduled_messages(self):
        """Handle time-based messages and scripts"""
        if not self.state.qual_timestamp or not self.state.race_timestamp:
            # Set timestamps from config if available
            if CONFIG['timestamp_qual_start']:
                self.state.qual_timestamp = CONFIG['timestamp_qual_start']
                self.state.race_timestamp = CONFIG['timestamp_qual_start'] + CONFIG['qual_minutes'] * 60
            else:
                return
        
        # Auto-week mode
        if CONFIG['timestamp_qual_start']:
            self.state.qual_timestamp = TimeUtils.auto_week(
                self.state.qual_timestamp, CONFIG['qual_minutes']
            )
            self.state.race_timestamp = self.state.qual_timestamp + 60 * CONFIG['qual_minutes']
        
        current_time = time.time()
        tq = self.state.qual_timestamp
        tr = self.state.race_timestamp
        
        # One hour before qual
        if tq - 3600 < current_time < tq:
            if CONFIG['one_hour_message'] and not self.state.one_hour_message_id:
                self.state.one_hour_message_id = self.messenger.send_message(
                    self.messenger.webhook_info,
                    CONFIG['one_hour_message'],
                    message_id=self.state.one_hour_message_id,
                    username=CONFIG['bot_name']
                )
            
            if CONFIG['script_one_hour'] and not self.state.script_one_hour_done:
                Logger.log(f'Running one hour script: {CONFIG["script_one_hour"]}')
                try:
                    os.system(CONFIG['script_one_hour'])
                except Exception as e:
                    Logger.log(f'Error: {e}')
                self.state.script_one_hour_done = True
        else:
            if self.state.one_hour_message_id:
                self.messenger.delete_message(self.messenger.webhook_info, self.state.one_hour_message_id)
                self.state.one_hour_message_id = None
            self.state.script_one_hour_done = False
        
        # During qualifying
        if tq < current_time < tr:
            if CONFIG['qualifying_message'] and not self.state.qualifying_message_id:
                self.state.qualifying_message_id = self.messenger.send_message(
                    self.messenger.webhook_info,
                    CONFIG['qualifying_message'],
                    message_id=self.state.qualifying_message_id,
                    username=CONFIG['bot_name']
                )
            
            if CONFIG['script_qualifying'] and not self.state.script_qualifying_done:
                Logger.log(f'Running qualifying script: {CONFIG["script_qualifying"]}')
                try:
                    os.system(CONFIG['script_qualifying'])
                except Exception as e:
                    Logger.log(f'Error: {e}')
                self.state.script_qualifying_done = True
        else:
            if self.state.qualifying_message_id:
                self.messenger.delete_message(self.messenger.webhook_info, self.state.qualifying_message_id)
                self.state.qualifying_message_id = None
            self.state.script_qualifying_done = False
    
    def send_state_messages(self):
        """Send all state messages to Discord"""
        Logger.log('Sending state messages')
        
        # Check for session timeout
        if (self.state.session_end_time and 
            time.time() - self.state.session_end_time > CONFIG['online_timeout']):
            self.state.online_message_id = None
            self.state.seen_namecars = {}
        
        # Get formatted strings
        onlines = self.formatter.get_onlines_string()
        join_link = self.formatter.get_join_link()
        
        # Build info message
        self.send_info_message(onlines, join_link)
        
        # Send online message if needed
        if onlines:
            self.send_online_message(onlines, join_link)
        else:
            self.end_session()
        
        self.save_state()
    
    def send_info_message(self, onlines: Optional[str], join_link: str):
        """Send venue/laps info message"""
        # Build registration info
        reg_string = ''
        timestamp_info = ''
        
        if self.state.qual_timestamp and self.state.qual_timestamp > 0:
            tq = str(int(self.state.qual_timestamp))
            tr = str(int(self.state.race_timestamp))
            
            name_time = f'<t:{tq}:D>'
            if CONFIG['registration_name']:
                name_time = f"{CONFIG['registration_name']} {name_time}"
            
            timestamp_info = (
                f"\n{name_time}"
                f"\n`Qual:` <t:{tq}:t> (<t:{tq}:R>)"
                f"\n`Race:` <t:{tr}:t> (<t:{tr}:R>)\n"
            )
            
            if CONFIG['url_registration'] and self.state.number_slots:
                reg_string = (
                    f"**[Register ({self.state.number_registered}/"
                    f"{self.state.number_slots})]({CONFIG['url_registration']})**"
                )
        
        # Build title
        title = ''
        carset = self.state.carset or (
            list(self.state.carnames.values())[0] 
            if len(self.state.carnames) == 1 else None
        )
        
        if carset:
            title = f"{carset.upper()} @ "
        if self.state.track_name:
            title += self.state.track_name.upper()
        
        if CONFIG['url_event_info']:
            title = f"[{title}]({CONFIG['url_event_info']})"
        
        # Build body
        body = f"{CONFIG['venue_header']}**__{title}__**{timestamp_info}{CONFIG['venue_subheader']}"
        
        # Add laps if configured
        footer = f"\n{reg_string}{CONFIG['laps_footer']}{join_link}"
        
        laps_str = None
        max_chars = 4070 - len(body) - len(footer)
        if onlines:
            max_chars -= len(f"\n**{CONFIG['online_header']}**\n{onlines}")
        
        if CONFIG['leaderboard_mode'] == 1:
            laps_str = self.formatter.get_laps_string(max_chars)
        elif CONFIG['leaderboard_mode'] == 2:
            laps_str = self.formatter.get_stats_string(max_chars)
        
        if laps_str:
            body += f"\n{laps_str}\n"
        
        # Add online info
        if onlines:
            body += f"\n**{CONFIG['online_header']}**\n{onlines}"
        
        # Determine color
        if onlines:
            color = CONFIG['color_onlines']
        elif self.state.server_is_up:
            color = CONFIG['color_server_up']
        else:
            color = 0
        
        # Send message
        self.state.laps_message_id = self.messenger.send_message(
            self.messenger.webhook_info,
            body=body + footer,
            message_id=self.state.laps_message_id,
            color=color,
            username=CONFIG['bot_name']
        )
    
    def send_online_message(self, onlines: str, join_link: str):
        """Send online players message"""
        self.state.session_end_time = 0
        
        body = f"**{CONFIG['online_header']}**\n{onlines}\n{CONFIG['online_footer']}{join_link}"
        
        self.state.online_message_id = self.messenger.send_message(
            self.messenger.webhook_online,
            body=body,
            message_id=self.state.online_message_id,
            username=CONFIG['bot_name']
        )
    
    def end_session(self):
        """End the current session"""
        if not self.state.online_message_id:
            return
        
        Logger.log('Ending session')
        
        participants = []
        for n, namecar in enumerate(self.state.seen_namecars.keys(), 1):
            participants.append(f"{n}. {namecar}")
        
        if participants:
            body = (
                f"{CONFIG['session_complete_header']}\n\n"
                f"Participants:\n" + '\n'.join(participants) + 
                f"\n{CONFIG['online_footer']}{self.formatter.get_join_link()}"
            )
            
            self.state.online_message_id = self.messenger.send_message(
                self.messenger.webhook_online,
                body=body,
                message_id=self.state.online_message_id,
                color=0,
                username=CONFIG['bot_name']
            )
            
            self.state.session_end_time = time.time()
        else:
            self.messenger.delete_message(
                self.messenger.webhook_online, 
                self.state.online_message_id
            )
            self.state.online_message_id = None
            self.state.session_end_time = 0

# Entry point
if __name__ == "__main__":
    monitor = ACServerMonitor()