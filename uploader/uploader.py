#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, random, codecs
import discord
from PIL import Image # Cannot seem to save dds as DXT3 yet.
from importlib import util
from datetime import timedelta, datetime, timezone
from time import time, sleep
from subprocess import run
from dateutil import parser
from stat import S_IWUSR
from webbrowser import open as webbrowser_open
from pyperclip import copy as pyperclip_copy
from json import load, dump
from glob import glob
from shutil import copy, copytree, ignore_patterns
from codecs import open as codecs_open
import paramiko
from numpy import round
# importing required modules
from zipfile import ZipFile, ZIP_DEFLATED
import os

###JJJJJJJJJJJJJJJACK
# Problems with starting from scratch.
# First time new server can't connect for some reason until close / re-open

SERVER_MODE_PREMIUM = 0
SERVER_MODE_VANILLA = 1

# List of files not to include in zips
zip_excludes = ['.idea', 'desktop.ini', '.git']

# Change to the directory of this script depending on whether this is a "compiled" version or run as script
if os.path.split(sys.executable)[-1] == 'uploader.exe': os.chdir(os.path.dirname(sys.executable)) # For executable version
else:                                                   os.chdir(os.path.dirname(os.path.abspath(__file__)))
print('WORKING DIRECTORY:')
print(os.getcwd())

import spinmob as sm
import spinmob.egg as egg

error_timer = egg.gui.TimerExceptions()
error_timer.start()

_default_layout = '[default layout]'
_unsaved_carset = '[Unsaved Carset]'
_create_new_profile = '[Create New Profile]'

# Get the last argument, which can be used to automate stuff
if len(sys.argv): print('LAST ARGUMENT:', sys.argv[-1])

# Clear the terminal
print('\n\n\n------------------------------')



def get_all_file_paths(directory, excludes=[]):
  
    # initializing empty file paths list
    paths = []
  
    # crawling through directory and subdirectories
    for root, directories, files in os.walk(directory):
        for filename in files:
            
            # join the two strings in order to form the full filepath.
            path = os.path.join(root, filename)
            s = path.split('\\')

            # Exclude
            naughty=False
            for exclude in excludes:
                if exclude in s: 
                    naughty=True
                    break
            
            # Append
            if not naughty: paths.append(path)
  
    # returning all file paths
    return paths        

def zip_files(paths, zip_path, callback=None):
    # writing files to a zipfile
    try:
        with ZipFile(zip_path,'w',ZIP_DEFLATED) as zip:
            N = len(paths)
            for n in range(N):
                zip.write(paths[n])
                if callback: callback(n, N, paths[n])
    except Exception as e:
        print('ERROR:', e)


def zip_directory(directory, zip_path, excludes, callback=None):
    
    # calling function to get all file paths in the directory
    zip_files(get_all_file_paths(directory, excludes), zip_path, callback)

def zip_directories(directories, zip_path, excludes, callback=None):

    paths = []
    for directory in directories: paths = paths + get_all_file_paths(directory, excludes)
    zip_files(paths, zip_path, callback)

  
    

  
def get_utc_offset(t=None):
    """
    Given timestamp in seconds, return the local utc offset delta
    """
    if t==None: t = time()
    return datetime.fromtimestamp(t) - datetime.utcfromtimestamp(t)

def auto_week(t0):
    """
    Given a datetime object, increments the week until the first instance ahead of now,
    taking into acount daylight savings.

    Returns a datetime object
    """

    # Get the current timestamp
    now = time()

    # Get some useful deltas
    hour = timedelta(hours=1)
    week = timedelta(weeks=1)
    
    # We remember the "center" hour for later, to make absolutely sure it matches after 
    # we increment by a week. Daylight savings is too finicky to worry about, and
    # we can't be guaranteed that everything is timezone aware.
    original_hour = t0.hour

    # Convert it to a timestamp in seconds
    t = t0.timestamp()
    
    # Reverse until we reach a few hours from now, just to be safe
    # then increment until we find the next weekly event
    week = timedelta(days=7).total_seconds()
    while t >  now: t -= week
    while t <= now: t += week

    # Update the utc_offset
    t0 = datetime.fromtimestamp(t,tz=timezone(get_utc_offset(t)))
    
    # And now, the complete paranoia: dither the hour +/- 1 and make 
    # sure the value matches.

    # If the hours match we done.
    if original_hour == t0.hour: 
        # print('----------------OG HOUR')
        return t0
    
    # Check the options
    tp = t0 + hour
    if original_hour == tp.hour: 
        # print('-----------------PLUS HOUR')
        return tp

    tm = t0 - hour
    if original_hour == tm.hour: 
        # print('-----------------MINUS HOUR')
        return tm
 
    # Oh well.
    return t0

# Function for loading a json at the specified path
def load_json(path):
    """
    Load the supplied path with all the safety measures and encoding etc.
    """
    try:
        if os.path.exists(path):
            f = codecs_open(path, 'r', 'utf-8-sig', errors='replace')
            #f = open(path, 'r', encoding='utf8', errors='replace')
            j = load(f, strict=False)
            f.close()
            return j
    except Exception as e:
        print('ERROR: Could not load', path)
        print(e)

def dump_json(json, path, indent=2):
    """
    Opens the file, dumps it, indented.
    """
    f = open(path,'w', encoding="utf8")
    dump(json, f, indent=indent)
    f.close()

def rmtree(top):
    """
    Implemented to take care of chmodding
    """
    for root, dirs, files in os.walk(top, topdown=False):
        for name in files:
            filename = os.path.join(root, name)
            os.chmod(filename, S_IWUSR)
            os.remove(filename)
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    os.rmdir(top)

from PyQt5.QtWidgets import (QApplication, QDialog, QVBoxLayout, 
                             QListWidget, QListWidgetItem, QDialogButtonBox)
from PyQt5.QtCore import QTimer, Qt

class DirectorySelectionDialog(QDialog):
    def __init__(self, base_directory, selected_directories=None, timeout=None, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Select Directories")
        
        # Store the base directory and selected directories
        self.base_directory = base_directory
        self.selected_directories = selected_directories or []

        # Make dialog modal (block interaction with parent window)
        self.setWindowModality(Qt.ApplicationModal)

        # Layout
        layout = QVBoxLayout(self)

        # ListWidget to display directories
        self.directory_list = QListWidget(self)
        self.directory_list.setSelectionMode(QListWidget.MultiSelection)  # Allow multiple selection
        layout.addWidget(self.directory_list)

        # Populate the list with first-level directories
        self.populate_directory_list()

        # OK and Cancel buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Timeout (if provided)
        if timeout:
            QTimer.singleShot(timeout, self.timeout_close)

    def populate_directory_list(self):
        # Populate the QListWidget with directories from the base directory
        try:
            directories = [d for d in os.listdir(self.base_directory) 
                           if os.path.isdir(os.path.join(self.base_directory, d))]
            for directory in directories:
                item = QListWidgetItem(directory)
                self.directory_list.addItem(item)
                
                # Pre-select the directories that were passed as selected
                if directory in self.selected_directories:
                    item.setSelected(True)
                    
        except Exception as e:
            print(f"Error reading base directory: {e}")

    def get_selected_directories(self):
        # Return only the selected directory names
        selected_items = self.directory_list.selectedItems()
        return [item.text() for item in selected_items]

    def timeout_close(self):
        # Handle closing the dialog due to timeout
        print("Dialog timed out!")
        self.reject()  # Close the dialog without accepting

def select_multiple_directories(base_directory, selected_directories=None, timeout=None):
    dialog = DirectorySelectionDialog(base_directory, selected_directories, timeout)
    
    if dialog.exec_() == QDialog.Accepted:
        return dialog.get_selected_directories()
    
    return None

# GUI class for configuring the server
class Uploader:
    """
    GUI class for uploading content and restarting the assetto server.
    """

    def __init__(self, show=True, blocking=False):

        # If we're in executable mode, close the splash screen
        if '_PYIBoot_SPLASH' in os.environ and util.find_spec("pyi_splash"):
            import pyi_splash # IDE warning is ok; we don't get here except in executable mode.
            pyi_splash.update_text('UI Loaded ...')
            pyi_splash.close()
            blocking=True

        # For troubleshooting; may not work
        self.timer_exceptions = egg.gui.TimerExceptions()
        self.timer_exceptions.signal_new_exception.connect(self._signal_new_exception)
        self.timer_exceptions.start()

        # SSH connection object
        self.ssh  = None
        self.sftp = None
        self.transfer_percentage = 0

        # Flag for whether we're in the init phases
        self._init = True
        self._loading_server    = False
        self._loading_uploader  = False
        self._refilling_layouts = False
        self._refilling_tracks  = False
        self._refilling_carsets = False
        self._updating_cars     = False

        # Dictionary to hold all the model names
        self.cars  = dict()
        self.srac  = dict() # Reverse-lookup
        self.tracks = dict() # folder -> fancyname
        self.skcart = dict() # Reverse-lookup (fancyname -> folder)
        self.skins = dict()

        # Make sure we have a carset folder
        if not os.path.exists('carsets'): os.mkdir('carsets')

        # Other variables
        self.server = dict()
        self.track  = dict()
        self.style_category    = 'color:blue; font-size:14pt; font-weight:bold'
        self.style_fancybutton = 'background-color: #BBBBFF; color: blue; font-weight:bold'


        ######################
        # Build the GUI

        # Main window
        self.window = egg.gui.Window('Assetto Corsa Uploader', size=(1200,700), autosettings_path='window')

        self.window.set_column_stretch(1)

        # Top controls for choosing / saving server settings
        self.grid_top = self.window.add(egg.gui.GridLayout(False))
        self.window.new_autorow()

        #self.grid_top.add(egg.gui.Label('Profile:'))
        self.combo_server = self.grid_top.add(egg.gui.ComboBox([],
            tip='Select a server profile.',
            signal_changed=self._combo_server_changed,
            autosettings_path='combo_server')).set_width(150)
        self.combo_server.set_style(self.style_fancybutton)

        self.button_load_server = self.grid_top.add(egg.gui.Button('Load',
            tip='Load the selected server profile.',
            signal_clicked=self._button_load_server_clicked)).hide()

        self.button_save_server = self.grid_top.add(egg.gui.Button('Save',
            tip='Save the current server profile.',
            signal_clicked=self._button_save_server_clicked)).hide()

        self.button_clone_server = self.grid_top.add(egg.gui.Button('Clone',
            tip='Clones the selected server profile.',
            signal_clicked=self._button_clone_server_clicked))

        self.button_delete_server = self.grid_top.add(egg.gui.Button('Delete',
            tip='Delete the selected server profile (and saves it to servers/servername.json.backup in case you bootched it).',
            signal_clicked=self._button_delete_server_clicked))

        self.button_delete_server = self.grid_top.add(egg.gui.Button('Rename',
            tip='Renames the selected server profile.',
            signal_clicked=self._button_rename_server_clicked))

        # Tabs
        self.tabs = self.window.add(egg.gui.TabArea(autosettings_path='tabs'))
        self.tab_settings = self.tabs.add('Settings')
        self.tab_uploader = self.tabs.add('Uploader')

        # Log
        self.window.set_column_stretch(0)
        self.grid_log = self.window.add(egg.gui.GridLayout(False), alignment=0).set_minimum_width(150).set_maximum_width(350)
        self.text_log = self.grid_log.add(egg.gui.TextLog(), alignment=0)
        self.text_log.append_text('Welcome to AC Uploader!')
        self.grid_log.new_autorow()
        self.progress_bar = self.grid_log.add(egg.pyqtgraph.QtWidgets.QProgressBar(), alignment=0)



        #######################
        # SETTINGS

        # Server stuff
        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Mode:'))
        self.combo_mode = self.tab_settings.add(egg.gui.ComboBox(['Server Manager','Steam acServer (obsolete)'],
            signal_changed=self._combo_mode_changed))

        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('SSH Login:'))
        self.text_login = self.tab_settings.add(egg.gui.TextBox('username@ip-or-address.com',
            tip='Your server\'s ssh username@ssh-web-address',
            signal_changed=self._any_server_setting_changed), alignment=0)

        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('SSH Port:'))
        self.text_port = self.tab_settings.add(egg.gui.TextBox('22',
            tip='SSH Port (default is 22)',
            signal_changed=self._any_server_setting_changed), alignment=0)

        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('SSH Password:'))
        self.text_password = self.tab_settings.add(egg.gui.TextBox('',
            tip='SSH password if you have one.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        self.text_password._widget.setEchoMode(egg.pyqtgraph.QtWidgets.QLineEdit.Password)

        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('SSH Key File:'))
        self.text_pem          = self.tab_settings.add(egg.gui.TextBox('C:\\path\\to\\whatever.pem',
            tip='Local path to your key (*.pem) file generated by the server.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        self.button_browse_pem = self.tab_settings.add(egg.gui.Button('Browse',
            tip='Opens a dialog to let you find the key (*.pem) file.',
            signal_clicked=self._button_browse_pem_clicked))

        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Local Assetto Path:'))
        self.text_local          = self.tab_settings.add(egg.gui.TextBox('C:\\path\\to\\assettocorsa',
            tip='Local path to assettocorsa folder.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        self.button_browse_local = self.tab_settings.add(egg.gui.Button('Browse',
            tip='Opens a dialog to let you find the local assettocorsa folder.',
            signal_clicked=self._button_browse_local_clicked))

        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Remote Assetto Path:'))
        self.text_remote = self.tab_settings.add(egg.gui.TextBox('/home/username/path/to/assettocorsa',
            tip='Remote path to assettocorsa folder (where acServer is located).',
            signal_changed=self._any_server_setting_changed), alignment=0)

        ####### Settings for server manager premium
        self.tab_settings.new_autorow()
        self.label_stop = self.tab_settings.add(egg.gui.Label('Stop Server Command:'))
        self.text_stop = self.tab_settings.add(egg.gui.TextBox('/home/username/stop-server my-server',
            tip='Remote command that stops the server prior to modifying / uploading.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        self.button_stop_server = self.tab_settings.add(egg.gui.Button('Stop Server',
            signal_clicked=self._button_stop_server_clicked,
            tip='Run the command using the SSH parameters above.'))

        self.tab_settings.new_autorow()
        self.label_start = self.tab_settings.add(egg.gui.Label('Start Server Command:'))
        self.text_start = self.tab_settings.add(egg.gui.TextBox('/home/username/start-servers',
            tip='Remote command that starts the server again.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        self.button_start_server = self.tab_settings.add(egg.gui.Button('Start Server',
            signal_clicked=self._button_start_server_clicked,
            tip='Run the command using the SSH parameters above.'))

        self.tab_settings.new_autorow()
        self.label_monitor = self.tab_settings.add(egg.gui.Label('Restart Monitor Command:'))
        self.text_monitor = self.tab_settings.add(egg.gui.TextBox('/home/username/restart-monitor',
            tip='Remote path to a script that restarts the monitor.',
            signal_changed=self._any_server_setting_changed), alignment=0)

        self.tab_settings.new_autorow()
        self.label_remote_championship = self.tab_settings.add(egg.gui.Label('Remote Race JSON:'))
        self.text_remote_championship = self.tab_settings.add(egg.gui.TextBox('/home/username/server-manager/json/championships/blah-blah-blah.json',
            tip='Remote path to the race / championship json we wish to update. Requires json mode in\nserver-manager\'s config.yml.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        self.button_download_championship = self.tab_settings.add(egg.gui.Button('Download',
            tip='Download / import the specified race / championship json to initialize the server.',
            signal_clicked = self._button_download_championship_clicked))

        self.tab_settings.new_autorow()
        self.label_remote_live_timings = self.tab_settings.add(egg.gui.Label('Remote Live Timings JSON:'))
        self.text_remote_live_timings = self.tab_settings.add(egg.gui.TextBox('/home/username/server-manager/json/live_timings.json',
            tip='Remote path to the live_timings.json file we will need to delete when uploading a new venue.\n'\
               +'Requires json mode in server-manager\'s config.yml.',
            signal_changed=self._any_server_setting_changed), alignment=0)


        self.tab_settings.set_row_stretch(20)

        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Post-Upload URL 1:'))
        self.text_url = self.tab_settings.add(egg.gui.TextBox('',
            tip='Optional website to open after upload (e.g., the reservation sheet or the site that re-indexes server manager / starts practice).',
            signal_changed=self._any_server_setting_changed), alignment=0)
        self.button_go_url = self.tab_settings.add(egg.gui.Button(
            'Go to URL', tip='Open the supplied URL in your browser.',
            signal_clicked=self._button_go_url_clicked
        ))

        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Post-Upload URL 2:'))
        self.text_url2 = self.tab_settings.add(egg.gui.TextBox('',
             tip='Optional website to open after upload (e.g., the reservation sheet or the site that re-indexes server manager / starts practice).',
             signal_changed=self._any_server_setting_changed),
             alignment=0)
        self.button_go_url2 = self.tab_settings.add(egg.gui.Button(
            'Go to URL', tip='Open the supplied URL in your browser.',
            signal_clicked=self._button_go_url2_clicked
        ))

        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Pre-Command:'))
        self.text_precommand = self.tab_settings.add(egg.gui.TextBox('',
            tip='Optional local command to run before everything begins.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        self.button_browse_precommand = self.tab_settings.add(egg.gui.Button('Browse',
            tip='Opens a dialog to let you select a script file or something.',
            signal_clicked=self._button_browse_precommand_clicked))



        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Post-Command:'))
        self.text_postcommand = self.tab_settings.add(egg.gui.TextBox('',
            tip='Optional local command to run after everything is done.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        self.button_browse_postcommand = self.tab_settings.add(egg.gui.Button('Browse',
            tip='Opens a dialog to let you select a script file or something.',
            signal_clicked=self._button_browse_postcommand_clicked))


        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Custom Skins:'))
        self.text_skins = self.tab_settings.add(egg.gui.TextBox('',
            tip='Optional path to a custom skins uploading / packaging folder.\n' +\
                'Setting this will package the selected carset skins in content folder.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        self.button_browse_skins = self.tab_settings.add(egg.gui.Button('Browse',
            tip='Opens a dialog to let you select the custom skins directory.',
            signal_clicked=self._button_browse_skins_clicked))

        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Latest Skin Pack:'))
        self.text_latest_skins = self.tab_settings.add(egg.gui.TextBox('',
            tip='Optional name of the "latest" skin pack that will be updated every upload,\n'+
                'e.g. "sunday-liveries.zip". Note the skin pack will always be archived by\n'+
                'carset even without this specified. This just makes a copy for easy download.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        
        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Announcement Discord Webhook:'))
        self.text_webhook_announcement = self.tab_settings.add(egg.gui.TextBox('',
            tip='Optional discord webhook for sending the venue announcement.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        self.button_send_discord_announcement = self.tab_settings.add(egg.gui.Button('Send',
            tip='Manually sends the discord announcement message.',
            signal_clicked=self._button_send_discord_announcement_clicked))
        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Announcement Header:'))
        self.text_announcement_pre = self.tab_settings.add(egg.gui.TextBox('This week\'s venue: ',
            tip='Text before the venue string.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Announcement Footer:'))
        self.text_announcement_post = self.tab_settings.add(egg.gui.TextBox('\n\nSee above for information and race times.',
            tip='Text after the venue string.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        

        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Errors Discord Webhook:'))
        self.text_webhook_errors = self.tab_settings.add(egg.gui.TextBox('',
            tip='Optional discord webhook for sending error messages. Currently only for issues with liveries.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        
        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Maximum Texture Resolution:'))
        self.number_max_dds_size = self.tab_settings.add(egg.gui.NumberBox(2048,
            tip='Maximum allowed width / height (in pixels) of uploaded livery dds files. Zero to disable this check.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        
        # self.tab_settings.new_autorow()
        # self.label_test = self.tab_settings.add(egg.gui.Label('Test Remote Command:'))
        # self.text_test = self.tab_settings.add(egg.gui.TextBox('', tip='Remote test command for debugging.'), alignment=0)
        # self.button_test = self.tab_settings.add(egg.gui.Button('Run Command', signal_clicked=self._button_test_clicked, tip='Run the test command.'))

        #############################
        # UPLOADER
        self.tab_uploader.set_row_stretch(6)

        # Refresh button
        self.button_refresh = self.tab_uploader.add(egg.gui.Button('Refresh Tracks and Cars',
            tip='Scans the assettocorsa folder for content.',
            signal_clicked=self._button_refresh_clicked), alignment=0)
        self.button_refresh.set_style(self.style_fancybutton)

        self.tab_uploader.new_autorow()
        self.tab_uploader.add(egg.gui.Label('\nTrack').set_style(self.style_category))

        self.tab_uploader.new_autorow()
        self.grid2a = self.tab_uploader.add(egg.gui.GridLayout(False))

        # Track combo
        self.combo_tracks  = self.grid2a.add(egg.gui.ComboBox([],
            tip='Select a track!',
            signal_changed=self._combo_tracks_changed ), alignment=0).set_minimum_width(200)
        self.combo_layouts = self.grid2a.add(egg.gui.ComboBox([],
            tip='Select a layout (if there is one)!'), alignment=0).set_minimum_width(200)
        self.label_pitboxes= self.grid2a.add(egg.gui.Label('(0 pit boxes)'))
        self.combo_layouts.signal_changed.connect(self._combo_layouts_changed) # WHY??? WHY DOESN'T THE USUAL WAY WORK??

        # Grid for car controls (save/load, etc)
        self.tab_uploader.new_autorow()
        self.tab_uploader.add(egg.gui.Label('\nCar Set').set_style(self.style_category))
        self.tab_uploader.new_autorow()
        self.grid2b = self.tab_uploader.add(egg.gui.GridLayout(False), alignment=0)

        # Save load buttons
        self.combo_carsets = self.grid2b.add(egg.gui.ComboBox([_unsaved_carset],
            signal_changed=self._combo_carsets_changed,
            tip='Select a carset (if you have one saved)!'), alignment=0)
        self.grid2b.set_column_stretch(0)
        self.button_load_carset = self.grid2b.add(egg.gui.Button('Load',
            tip='Load the selected carset.', signal_clicked=self._button_load_carset_clicked))
        self.button_save_carset = self.grid2b.add(egg.gui.Button('Save',
            tip='Save / overwrite the selected carset with the selection below.\nIf [Unsaved Carset] is selected, this pops up a dialog to name the carset.',
            signal_clicked=self._button_save_carset_clicked))
        self.button_delete_carset = self.grid2b.add(egg.gui.Button('Delete',
            tip='Delete the selected carset.',
            signal_clicked=self._button_delete_carset_clicked))
        
        self.tab_uploader.new_autorow()
        self.grid_filter_cars = self.tab_uploader.add(egg.gui.GridLayout(False), alignment=0)
        self.grid_filter_cars.add(egg.gui.Label('Filter Cars:'))
        self.text_filter_cars = self.grid_filter_cars.add(egg.gui.TextBox('', 
            signal_changed=self._text_filter_cars_changed), alignment=0)
        self.button_edit_skins_pack = self.grid_filter_cars.add(egg.gui.Button('Edit Skins Pack',
            signal_clicked=self._button_edit_skins_pack_clicked)).disable()


        # Grid for car list
        self.tab_uploader.new_autorow()
        self.grid2c = self.tab_uploader.add(egg.gui.GridLayout(False), alignment=0)

        # Car folder list
        self.list_cars = self.grid2c.add(egg.pyqtgraph.Qt.QtWidgets.QListWidget(), alignment=0)
        self.list_cars.setSelectionMode(egg.pyqtgraph.Qt.QtWidgets.QAbstractItemView.ExtendedSelection)
        self.list_cars.itemSelectionChanged.connect(self._list_cars_changed)

        # Car fancy name list
        self.list_carnames = self.grid2c.add(egg.pyqtgraph.Qt.QtWidgets.QListWidget(), alignment=0)
        self.list_carnames.setSelectionMode(egg.pyqtgraph.Qt.QtWidgets.QAbstractItemView.ExtendedSelection)
        self.list_carnames.itemSelectionChanged.connect(self._list_carnames_changed)

        # Settings for each car. Auto-populated so no autosettings.
        # self.tree_cars = self.grid2c.add(egg.gui.TreeDictionary(
        #     new_parameter_signal_changed=self._tree_cars_changed), alignment=0).hide()
        
        self.tab_uploader.new_autorow()
        self.grid_tyres = self.tab_uploader.add(egg.gui.GridLayout(False))
        self.grid_tyres.add(egg.gui.Label('Allowed Tyres:'))
        self.text_tyres = self.grid_tyres.add(egg.gui.TextBox('V;H;M;S;ST;SM;SV',
            tip='Allowed tyres list, usually one or two capital characters, separated by semicolons.',
            signal_changed=self._any_server_setting_changed)).set_width(200)

        # Fixed setup
        self.grid_tyres.new_autorow()
        self.grid_tyres.add(egg.gui.Label('Fixed Setup:'))
        self.text_setup = self.grid_tyres.add(egg.gui.TextBox('',
            tip='Fixed setup path, applied to all cars. Needs the subfolder and extension as well, e.g. "generic/LoPeN.ini".',
            signal_changed=self._any_server_setting_changed)).set_width(200)
        self.checkbox_setup = self.grid_tyres.add(egg.gui.CheckBox('Use it.',
            tip='If checked, the fixed setup will be applied to all cars.',
            signal_changed=self._any_server_setting_changed))
        self.button_open_setup_folder = self.grid_tyres.add(egg.gui.Button('Open Folder',
            tip='Open the setups folder in documents.',
            signal_clicked=self._button_open_setup_folder_clicked))

        # Tyre wear 
        self.grid_tyres.new_autorow()
        self.grid_tyres.add(egg.gui.Label('Tyre Wear:'))
        self.number_tyre_wear = self.grid_tyres.add(egg.gui.NumberBox(100, 1, (0,100),
            tip='Tyre wear rate percentage. 0 means no wear, 100 means full.',
            signal_changed=self._any_server_setting_changed)).set_width(50)
        

        # Server stuff
        self.tab_uploader.new_autorow()
        self.tab_uploader.add(egg.gui.Label('\nServer').set_style(self.style_category))
        self.tab_uploader.new_autorow()

        self.grid2s = self.tab_uploader.add(egg.gui.GridLayout(margins=False), alignment=1)
        self.grid2s.add(egg.gui.Label('Max Pit Boxes:'))
        self.number_slots = self.grid2s.add(egg.gui.NumberBox(16,
            tip='Maximum number of pitboxes (will not exceed the track limit).',
            bounds=(1,None), int=True)).set_width(42)

        # Actions
        self.checkbox_pre  = self.grid2s.add(egg.gui.CheckBox(
            'Pre', signal_changed=self._any_server_setting_changed,
            tip='Run the pre-command before everything starts.'))
        self.checkbox_modify  = self.grid2s.add(egg.gui.CheckBox(
            'Config', signal_changed=self._any_server_setting_changed,
            tip='Modify the server files with the above profile.'))
        self.checkbox_autoweek = self.grid2s.add(egg.gui.CheckBox(
            'Week', signal_changed=self._any_server_setting_changed,
            tip='Automatically increment the race time\'s week to the next available date from today.'))
        self.checkbox_package = self.grid2s.add(egg.gui.CheckBox(
            'Content', signal_changed=self._any_server_setting_changed,
            tip='Package up all the local files for upload.'))
        self.checkbox_upload  = self.grid2s.add(egg.gui.CheckBox(
            'Upload', signal_changed=self._any_server_setting_changed,
            tip='Upload to server and unpack.'))
        self.checkbox_clean = self.grid2s.add(egg.gui.CheckBox(
            'Clean', signal_changed=self._any_server_setting_changed,
            tip='During upload, remove all old content (cars and tracks) from the server.'))
        # self.checkbox_reset = self.grid2s.add(egg.gui.CheckBox(
        #     'Reset', signal_changed=self._any_server_setting_changed,
        #     tip='Stop the server, clear out previous live timings (laps), and restart it, using the specified script.'))
        self.checkbox_restart = self.grid2s.add(egg.gui.CheckBox(
            'Restart', signal_changed=self._any_server_setting_changed,
            tip='Stop the server before upload and restart after upload.'))
        self.checkbox_monitor = self.grid2s.add(egg.gui.CheckBox(
            'Restart Monitor', signal_changed=self._any_server_setting_changed,
            tip='Restart the monitor after upload and server restart.'))
        self.checkbox_url = self.grid2s.add(egg.gui.CheckBox(
            'URL(s)', signal_changed=self._any_server_setting_changed,
            tip='Open the specified URL in your browser.'))
        self.checkbox_announce = self.grid2s.add(egg.gui.CheckBox(
            'Announce', signal_changed=self._any_server_setting_changed,
            tip='Sends the discord announcement if there is a webhook specified.'))
        self.checkbox_post  = self.grid2s.add(egg.gui.CheckBox(
            'Post', signal_changed=self._any_server_setting_changed,
            tip='Run the post-command after everything is done.'))

        # upload button
        self.tab_uploader.new_autorow()
        self.grid_go = self.tab_uploader.add(egg.gui.GridLayout(False), alignment=0)

        self.button_upload = self.grid_go.add(egg.gui.Button(
            'Full Upload', tip='Packages the required server data, uploads, restarts \
            the server, cleans up the local files.',
            signal_clicked=self._button_upload_clicked), alignment=0).set_width(100)
        self.button_upload.set_style(self.style_fancybutton)

        self.button_skins = self.grid_go.add(egg.gui.Button(
            'Skins Only', tip='Skips Config, Clean Server, Restart Server, Restart Monitor, and only collects skins during Content.',
            signal_clicked=self._button_skins_clicked), alignment=0).set_width(100)
        self.button_skins.set_style(self.style_fancybutton)

        self.grid_spacer = self.grid_go.add(egg.gui.GridLayout())
        self.grid_go.set_column_stretch(2)

        self.button_send_to = self.grid_go.add(egg.gui.Button(
            'Send To:',
            tip='Send the track, layout, and car selection to the selected server profile and switch to that profile.',
            signal_clicked=self._button_send_to_clicked), alignment=0).set_width(80)
        self.button_send_to.set_style(self.style_fancybutton)
        self.combo_send_to = self.grid_go.add(egg.gui.ComboBox([], signal_changed=self._any_server_setting_changed)).set_width(120)

        # List of items to save associated with each "server" entry in the top combo
        self._server_keys = [
            'combo_mode',
            'text_login',
            'text_port',
            'text_pem',
            'text_password',
            'text_local',
            'text_remote',
            'text_start',
            'text_stop',
            'text_monitor',
            'text_remote_championship',
            'text_remote_live_timings',
            #'text_reset',
            'text_postcommand',
            'text_precommand',
            'text_url',
            'text_url2',
            'text_skins',
            'text_latest_skins',
            'text_webhook_errors',
            'text_webhook_announcement',
            'text_announcement_pre',
            'text_announcement_post',
            'number_max_dds_size',
            'text_tyres',
            'text_setup',
            'checkbox_setup',
            'number_slots',
            'checkbox_pre',
            'checkbox_modify',
            'checkbox_autoweek',
            'checkbox_package',
            'checkbox_upload',
            'checkbox_clean',
            #'checkbox_reset',
            'checkbox_restart',
            'checkbox_monitor',
            'checkbox_url',
            'checkbox_announce',
            'checkbox_post',
            'combo_send_to', 
            'number_tyre_wear',
            'text_filter_cars', # Do this as a last step!!!
        ]
        

        ###################
        # Load the servers list
        self.update_server_list()

        # Enables various events again.
        self._init = False

        # Now load whichever one was selected.
        self._button_load_server_clicked()

        # If we're automatically uploading skins, do so.
        if len(sys.argv) and sys.argv[-1].split('=')[0].strip() == 'skins':
            # print('\nAUTOMATED SKINS UPLOAD:')
            # Remember the original server setting
            og_server = self.combo_server.get_text()  
            
            # Loop over the servers to do skins with
            for server in sys.argv[-1].split('=')[1].split(';'):
                server = server.strip()

                # print('\n\n\n\n----------------------------------------------\nSELECTING '+server)
                self.combo_server.set_text(server)

                # print('UPLOADING SKINS')
                self.do_skins_only()
            
            # Set back to the original server
            self.combo_server.set_text(og_server)

        ######################
        # Show the window; no more commands below this.
        else: 
            if show: self.window.show(blocking)

    def _button_open_setup_folder_clicked(self, *a):
        """
        Opens the setup folder.
        """
        cars = self.get_selected_cars()
        if len(cars): path = os.path.join(os.path.expanduser('~'), 'Documents', 'Assetto Corsa', 'setups', cars[0])
        else:         path = os.path.join(os.path.expanduser('~'), 'Documents', 'Assetto Corsa', 'setups')
        os.startfile(path)

    def _button_test_clicked(self, *a):
        """
        Runs the test remote command.
        """
        test = self.text_test()  # For acsm
        self.log('\n'+test+'\n')

        if test.strip() != '':
            self.log('Testing...')
            if self.ssh_command(test):
                self.log('oop?')
                return
            self.log('Done.\n')

    def _text_filter_cars_changed(self, *a):
        """
        Someone changes the filter
        """
        # print('_text_filter_cars_changed')
        
        # Get the search string
        search = self.text_filter_cars().lower()
        
        # Loop over the car and carname lists
        for n in range(self.list_cars.count()):
            item1 = self.list_cars    .item(n)
            item2 = self.list_carnames.item(n)
            if item1: item1.setHidden(not search in item1.data(0).lower() and not item1.isSelected())
            if item2: item2.setHidden(not search in item2.data(0).lower() and not item2.isSelected())

        # Save the setting in case we ever decide to load on boot. 
        if not self._loading_server: self.button_save_server.click()

    def send_discord_message(self, message='', body='', color=15548997):
        """
        Sends a message (message, 2000 character limit) and an embed
        (body1, body2, footer, 4096 characters total). Returns the message id
        """
        webhook_url = self.text_webhook_errors.get_text().strip()
        if not len(webhook_url): return
        
        # Make the webhook
        try: webhook = discord.SyncWebhook.from_url(webhook_url)
        except Exception as e:
            self.log('ERROR: Could not create webhook.\n', e)
            return
        
        # Keep the total character limit below 4096, cutting body1 first, then body 2
        if len(body)    > 4090: body    = body[0:4090]    + ' ...'
        if len(message) > 2000: message = message[0:1995] + '\n...'

        # Make the discord embed for the body
        e = discord.Embed()
        e.color       = color
        e.description = body
        
        # Try to send it
        try: 
            if len(e.description): message_id = webhook.send(message, embeds=[e], wait=True).id
            else:                  message_id = webhook.send(message, embeds=[ ], wait=True).id
        except Exception as x:
            self.log('ERROR: Could not send discord message.', message_id, e, x)
            message_id = None

        # Return the id just in case.
        return message_id
    
    def _button_send_discord_announcement_clicked(self, *a):
        """
        Just sends the discord announcement message.
        """
        self.send_discord_announcement()

    def send_discord_announcement(self):
        """
        Sends a message (message, 2000 character limit) and an embed
        (body1, body2, footer, 4096 characters total). Returns the message id
        """
        if not self.checkbox_announce(): return

        self.log('Sending discord venue announcement.')

        # Get the webhook
        webhook_url = self.text_webhook_announcement.get_text().strip()
        if not len(webhook_url): return
        
        # Make the webhook
        try: webhook = discord.SyncWebhook.from_url(webhook_url)
        except Exception as x:
            self.log('ERROR: Could not create webhook.\n', x)
            return
        
        # Assemble the message
        message = self.text_announcement_pre() \
                + self.combo_carsets.get_text()+' at '+self.track['name'] \
                + self.text_announcement_post()

        # Unescape it
        message = codecs.decode(message, 'unicode_escape')

        # Keep the total character limit below 2000
        if len(message) > 2000: message = message[0:1995] + '\n...'

        # Try to send it
        try: 
            message_id = webhook.send(message, wait=True).id
        except Exception as x:
            self.log('ERROR: Could not send discord message.', message_id, x)
            message_id = None

        # Return the id just in case.
        return message_id

    def valid_dds_file(self, path):
        """
        Give the path to a dds and it will check it against self.number_dds_max_size
        """
        if path.split('.')[-1] != 'dds' or self.number_max_dds_size() <= 0: return True, None

        # Check the size
        try:
            img = Image.open(path)
            if img.width <= self.number_max_dds_size() or img.height <= self.number_max_dds_size():
                return True, None
            else: return False, 'Resolution is greater than %d.' % self.number_max_dds_size()
            
        # Couldn't open the file or something
        except Exception as e:
            self.log('  ERROR: Could not check size of', path.split('assettocorsa')[-1], e)
            return False, str(e)
            
    def unpack_skin(self, path):
        """
        Takes the supplied full zip path, validates it (sorta) and 
        puts it into the cars folder.
        """
        self.log('  ', os.path.split(path)[-1])
        skins   = self.text_skins().strip()
        local   = self.text_local().strip()
        cars = os.path.join(local, 'content', 'cars')
        
        # Sanity checks
        if not os.path.exists(path): return
        if skins == '' or not os.path.exists(skins): return
        if local == '' or not os.path.exists(cars) : return
        
        # Validity conditions
        skins_found = False # Whether we found a skins folder in the archive
        bad_files   = {}    # List of bad (dds) files: key = filename, value = error message
        path_out = None

        # Try navigating the zip file
        try: 
            # Get the zipfile object
            z = ZipFile(path, 'r')

            json_custom_skins = self.load_custom_skins_json()

            # Loop over every single file path in the zip.
            for x in z.infolist():

                # If this one is not a directory
                if x.is_dir(): continue

                # split the path to get components
                ls = x.filename.lower().split('/') # Lower case
                us = x.filename.split('/')         # Normal case

                # Look for the skins folder
                i_skins = -1
                if 'skins' in ls: 
                    i_skins = ls.index('skins')
                    skins_found = True

                # if the index is zero or lower, we don't know what car it is
                if i_skins <= 0: continue 

                # Remember the last valid car and skin folder
                car = us[i_skins-1]
                skin = us[i_skins+1]

                # Get the output path (everything after the skins folder)
                path_out = os.path.join(cars, *us[i_skins-1:])
                
                # Make sure it doesn't exist
                if os.path.exists(path_out): os.unlink(path_out)

                # Make the zipinfo filename just the file
                x.filename = os.path.basename(x.filename)

                # If this is a file we care about, and it comes from a path
                # at least 3 deep
                if x.filename not in ['desktop.ini'] and len(us)-i_skins == 3:

                    # Extract this file
                    dir_path_out = os.path.dirname(path_out)
                    z.extract(x, dir_path_out)
                    
                    # If this is a bad file
                    good, error = self.valid_dds_file(os.path.join(dir_path_out, x.filename))
                    if not good: bad_files[x.filename] = error   

            # End of loop over files in zip

            # Close the zip file and delete it, regardless of whether it worked
            z.close()
            os.unlink(path)

            # If it's valid, dump the updated list of skins.
            if skins_found and len(bad_files)==0: 
                # Add this to the json using the last valid car and skin folder names
                if car not in json_custom_skins: json_custom_skins[car] = []
                if skin not in json_custom_skins[car]: json_custom_skins[car].append(skin) 
                self.save_custom_skins_json(json_custom_skins)

                # Send a happy message
                zip_filename = os.path.split(path)[-1]
                message = 'SUCCESS! Livery file '+zip_filename+' passed checks and is uploading... :)'
                self.send_discord_message(message)

            # Otherwise something went wrong, so delete it and send a message about it.
            else: 

                # Delete the extracted folder
                if path_out and os.path.exists(path_out): os.unlink(path_out)

                # Assemble the error log for this car
                zip_filename = os.path.split(path)[-1]
                message = 'ERROR: ' + zip_filename + ' is invalid:'

                # Add custom issues.
                if not skins_found   : message = message + '\n* skins folder not found'
                for file in bad_files: message = message + '\n* '+file+': ' + bad_files[file]

                # Log
                self.log(message)
                self.send_discord_message('', message)
                
                

            # End of different cases for validity of zip file.

        # End of try

        # Just in case it's a bad file.
        except Exception as e: self.log('Ass.', e)
            
        
        


    def unpack_skins_queue(self):
        """
        Validates and unpacks the zip files in the queue
        """
        skins  = self.text_skins().strip()
        if skins == '': return

        # Get a list of (full) paths to the zip files
        paths = glob(os.path.join(skins, 'Queue', '*.zip'))

        # Now unpack each
        if len(paths): self.log('Unpacking queued skins:')
        for path in paths: self.unpack_skin(path)


    def load_custom_skins_json(self):
        """
        Loads custom_skins json or an empty dictionary.
        """
        # Open / create the json containing custom skins list
        j = load_json('custom_skins.json')
        if not j: j = dict()
        return j
    
    def save_custom_skins_json(self, j):
        """
        Just dumps the supplied dictionary to the file custom_skins.json.
        """
        dump_json(j, 'custom_skins.json')

    def import_and_package_skins(self):
        """
        Copies all the custom skins associated with the currently selected
        carset into the actual assetto content folder, and zips them up for
        distribution.
        """
        skins  = self.text_skins().strip()
        latest = self.text_latest_skins().strip()
        local  = self.text_local().strip()
        carset = self.combo_carsets.get_text()
        cars   = self.get_selected_cars()
        if skins == '' or local == '' or carset == _unsaved_carset or len(cars)==0: return

        self.log('Packaging carset skins...')

        # Tidy up the carset
        naughties = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        carset_safe = carset
        for naughty in naughties: carset_safe.replace(naughty,'')

        # Validate and unpack all skin zips in the queue
        self.unpack_skins_queue()

        # Get the root directory of the packs
        packs_path = os.path.join(skins,'Livery Packs')
        if not os.path.exists(packs_path): 
            try: os.mkdir(packs_path)
            except Exception as e: self.log(e)
        # print('Packs:', packs_path)

        # Get the path to the pack for this carset and delete it.
        zip_path = os.path.join(packs_path, carset_safe + '.zip')
        if os.path.exists(zip_path): os.remove(zip_path)

        # print('Zip:', zip_path)

        # Load the custom skins list to figure out which ones to pack
        j = self.load_custom_skins_json()
        
        # Temporarily switch working directory to the local cars folder.
        cwd = os.getcwd()
        os.chdir(os.path.join(local,'content','cars'))
    
        # Loop over the selected cars and copy them from a custom skins folder into the 
        # main local assetto folder. Also assemble the list of files to zip
        directories_to_zip = [] # list of sub-directories we will transfer to the archive
        if j: # we loaded the json
            for car in cars:
                self.log(' '+car)
                if car in j:
                    for skin in j[car]:
                        source = os.path.join(car, 'skins', skin)
                        if os.path.exists(source): directories_to_zip.append(source)
            
            # Zip the pack up in the archive
            if len(directories_to_zip):
                self.log('Zipping up skin pack...')
                for s in directories_to_zip:
                    self.log('  '+os.path.split(s)[-1])
                zip_directories(directories_to_zip, zip_path, zip_excludes, self.update_progress)
                self.progress_bar.setValue(100)

                # Get the latest.zip path
                if latest != '':
                    # zip_path is the path to the Livery Pack/carset.zip file. Should
                    # have been created above...
                    if os.path.exists(zip_path): 
                        self.log('Copying pack to ../'+latest)
                        copy(zip_path, os.path.join(skins,latest))
                    else: self.log('ERROR: Custom skins directory does not exist!')
            
            else: self.log('No custom skins defined for this carset.')

        else: self.log('No custom skins json.')

        # Back to the previous wd
        os.chdir(cwd)

        

    def _button_browse_skins_clicked(self, *a):
        """
        Opens a directory selection dialog for the skins path.
        """
        d = egg.dialogs.select_directory()
        if d: self.text_skins.set_text(d)

    def _button_send_to_clicked(self, *a):
        """
        Sends the venue to the selected server
        """
        # Get the track, cars and carset
        trackname  = self.combo_tracks.get_text()
        layoutname = self.combo_layouts.get_text()
        carset = self.combo_carsets.get_text()
        cars   = self.get_selected_cars() # This should always return the directories.
        tyres  = self.text_tyres()
        setup  = self.text_setup()
        setup_enabled = self.checkbox_setup()
        wear   = self.number_tyre_wear()

        try:
            # Now switch to the "send to" server
            self.combo_server.set_text(self.combo_send_to.get_text())

            # Track and layout
            self.combo_tracks.set_text(trackname)
            if len(self.combo_layouts.get_all_items()) > 0: self.combo_layouts.set_text(layoutname)

            # Some problem here if we overwrite a carset, sometimes
            # If we have an unsaved carset, use the list, otherwise just choose the carset
            if carset == _unsaved_carset: self.set_list_selection(cars, self.list_cars, self._list_cars_changed)
            self.combo_carsets.set_text(carset)

            # Tyres
            self.text_tyres.set_text(tyres)

            # Setup
            self.text_setup(setup)
            self.checkbox_setup(setup_enabled)

            # Wear
            self.number_tyre_wear(wear)

        except Exception as e: print('ERROR: _button_send_to_clicked', e)

    def _button_go_url_clicked(self, *a):
        """
        Opens the URL in browser.
        """
        if self.text_url() != '':
            self.log('Opening URL 1...')
            webbrowser_open(self.text_url())

    def _button_go_url2_clicked(self, *a):
        """
        Opens the URL in browser.
        """
        if self.text_url2() != '':
            self.log('Opening URL 2...')
            webbrowser_open(self.text_url2())

    # else: self.log('*Skipping URL')
    def _button_download_championship_clicked(self, *a):
        """
        Attempts to download the championship file into the server.json.
        """
        self.connect()
        
        # Load the championship from the server
        self.log('Downloading championship.json...')
        if self.sftp_download(self.text_remote_championship(), 'championship.json'):
            self.log('ERROR: Download failed.')
            return

        self.disconnect()

        # load it
        c = load_json('championship.json')
        if not c:
            self.log('ERROR: Could not load championship.json.')
            return

        # Dump it into the server file
        self.log('Saving contents...')
        self.server['championship'] = c
        self.button_save_server.click()
        self.log('Done!\n')



    def update_server_list(self):
        """
        Searches servers directory and updates combo box.
        """
        # print('update_server_list')
        
        # Clear existing
        self.combo_server.clear()

        # Add default entry that is always at the top
        self.combo_server.add_item(_create_new_profile)

        if not os.path.exists('servers'): os.makedirs('servers')
        paths = glob(os.path.join('servers','*.json'))
        paths.sort()
        for path in paths: self.combo_server.add_item(os.path.splitext(os.path.split(path)[-1])[0])

        # Now set it to the previous selection
        self.load_server_gui()


    def _any_server_setting_changed(self, *a):
        """
        Called whenever someone changes a server setting. Enables the save button.
        """
        if not self._loading_server: self.button_save_server.click()

        # Update available options based on what things have text in them.
        self.checkbox_url.set_hidden(self.text_url() == '' and self.text_url2() == '')
        self.checkbox_pre.set_hidden(self.text_precommand() == '')
        self.checkbox_post.set_hidden(self.text_postcommand() == '')
        #self.checkbox_reset.set_hidden(self.text_reset() == '')
        self.checkbox_restart.set_hidden(self.text_stop().strip() == '' or self.text_start().strip() == '')
        self.checkbox_monitor.set_hidden(self.text_monitor() == '')

    def _combo_server_changed(self, *a):
        """
        When the server combo changes, load it (and remember)
        """
        if self._init: return
        # print('_combo_server_changed')

        # If we're on "new server" prompt for a save.
        if self.combo_server() == 0: 
            self.button_save_server.click()
            return

        # Now whatever we've chosen, load it.
        self._button_load_server_clicked()
        self.save_server_gui()

        # remember the selection
        self.combo_server.save_gui_settings()

    def load_server_json(self):
        """
        Gets the selected server json from file.
        """
        # Special case: first element in combo box is new server
        if self.combo_server.get_index() == 0: return

        # Get the path associated with this
        path = os.path.join('servers', self.combo_server.get_text()+'.json')
        if not os.path.exists(path) or os.path.isdir(path): 
            self.log('Weird. Could not find', path, '\n  I need an adult!')
            return

        # Load it.
        f = open(path, 'r', encoding="utf8")
        self.server = load(f, strict=False)
        f.close()

        # If there is no championship, warn!
        if not 'championship' in self.server and self.server['settings']['combo_mode'] == SERVER_MODE_PREMIUM:
            self.log('\n-------\nWARNING: You must download the remote championship json at least once for this server.\n-------\n')

        return self.server

    def _button_clone_server_clicked(self, *a):
        """
        Pops up a dialog and adds a new server with the same settings.
        """
        if self.combo_server() == 0: return

        name, ok = egg.pyqtgraph.Qt.QtWidgets.QInputDialog.getText(egg.pyqtgraph.Qt.QtWidgets.QWidget(), 'New Server Profile', 'Name your new server profile:')
        name = name.strip()

        # If someone cancels out do nothing
        if not ok or name == '': return

        # Otherwise, copy the current selection
        old_path = os.path.join('servers', self.combo_server.get_text()+'.json')
        new_path = os.path.join('servers', name+'.json')
        copy(old_path, new_path)

        # Add it to the list and select it
        self.combo_server.add_item(name)
        self.combo_server.set_text(name)

    def _button_rename_server_clicked(self, *a):
        """
        Pops up a dialog and adds a new server with the same settings.
        """
        if self.combo_server() == 0: return

        name, ok = egg.pyqtgraph.Qt.QtWidgets.QInputDialog.getText(egg.pyqtgraph.Qt.QtWidgets.QWidget(), 'Rename Server Profile', 'Rename your server profile:')
        name = name.strip()

        # If someone cancels out do nothing
        if not ok or name == '': return

        # Otherwise, copy the current selection
        # print('Renaming')
        old_path = os.path.join('servers', self.combo_server.get_text()+'.json')
        new_path = os.path.join('servers', name+'.json')
        os.rename(old_path, new_path)

        # Add it to the list and select it
        self.combo_server.add_item(name)

        # Remove the currently selected one
        self.combo_server.remove_item(self.combo_server())

        # Now update the selected server to the new one.
        self.combo_server.set_text(name)

    def _button_load_server_clicked(self, *a): 
        """
        Load the selected server.
        """
        # print('_button_load_server_clicked')
        
        # If it's "new server" ask for one
        if self.combo_server() == 0: 
            self.button_save_server.click()
            return

        # Load the server GUI stuff
        self._load_server_settings()

        # Refresh the content based on the assetto path
        self._button_refresh_clicked()

    def _load_server_settings(self):
        """
        Loads the data for the settings tab only, based on the chosen server.
        """
        # print('_load_server_settings')
        self.server = self.load_server_json()
        if not 'settings' in self.server: return
        # print('  loaded json')

        self._loading_server = True

        # Populate the send to combo
        self.combo_send_to.clear()
        for item in self.combo_server.get_all_items():
            if item not in [self.combo_server.get_text(), _create_new_profile]:
                self.combo_send_to.add_item(item)

        dead_keys = []
        for key in self.server['settings']:
            try:    
                # Special case: we do this one manually at the end.
                if key in self._server_keys: 
                    exec('self.'+key+'.set_value(value)', dict(self=self, value=self.server['settings'][key]))
            except: 
                # print('  deleting', key)
                dead_keys.append(key)
        for key in dead_keys: self.server['settings'].pop(key)
            ## print(' ', key, '->', j['settings'][key])
        
        self._loading_server = False
        

        
        
    def validate_checkbox_setup(self):
        """
        Unchecks the checkbox_setup if the setup file does not exist.
        """
        # Check if the fixed setup exists. # JACK THIS SHOULD BE A FUNCTION THAT IS 
        # ALSO CHECKED WHEN CHANGING ANY CARS.
        # Loop over the selected cars and check if the setup exists for each
        if self.checkbox_setup():
            for car in self.get_selected_cars():
                setup_path = os.path.join(os.path.expanduser('~'), 'Documents', 'Assetto Corsa', 'setups', car, self.text_setup().strip())
                if not os.path.exists(setup_path):
                    self.log('WARNING: Fixed setup for %s does not exist. Disabling.' % setup_path)
                    self.checkbox_setup.set_value(False)

    def _load_server_uploader(self):
        """
        Loads the garbage into the uploader for the chosen server.
        """
        # print('_load_server_uploader')
        #self.server = self.load_server_json()
        if not 'uploader' in self.server: return
        self._loading_uploader = True

        # Now re-select the track
        # print('  track')
        try:  
            t = self.server['uploader']['combo_tracks']
            
            # Get the current text for comparison
            original = self.combo_tracks.get_text()
            
            # Set it if it's in there.
            if t in self.combo_tracks.get_all_items(): self.combo_tracks.set_text(t)

            # If it's the same as it was before, run the event to make sure  it updates the rest of the gui
            if self.combo_tracks.get_text() == original: self._combo_tracks_changed() 

        except Exception as e: print('ERROR: load_upload_gui combo_tracks', e)
        
        # Now re-select the layout
        # print('  layout')
        try:    
            t = self.server['uploader']['combo_layouts']
            if t in self.combo_layouts.get_all_items():
                self.combo_layouts.set_text(t)
        except Exception as e: print('ERROR: load_upload_gui combo_layouts', e)
        
        # Now re-select the carset
        # print('  carset')
        try:    
            t = self.server['uploader']['combo_carsets']
            if t in self.combo_carsets.get_all_items():
                self.combo_carsets.set_text(t)
        except Exception as e: print('ERROR: load_upload_gui combo_carsets', e)
        
        # Update the actual cars list based on the server data.
        self.set_list_selection(self.server['uploader']['list_cars'], self.list_cars, self._list_cars_changed)
        
        # Also send these to the carnames
        self.send_cars_to_carnames()

        self._loading_uploader = False
        
        # Now run the filter
        self._text_filter_cars_changed()

        # Do some clean-up
        self._after_cars_carnames_changed()

        #self.send_cars_to_tree()

        # print('_load_server_uploader complete')


    def _button_save_server_clicked(self, *a): 
        """
        Saves the current server configuration under the chosen name, or pops up a dialog
        if [New Server] is chosen.
        """
        if self._loading_uploader: return
        # print('_button_save_server_clicked')

        # Special case: first element in combo box is new carset
        if self.combo_server() == 0:
            name, ok = egg.pyqtgraph.Qt.QtWidgets.QInputDialog.getText(egg.pyqtgraph.Qt.QtWidgets.QWidget(), 'New Server', 'Name your new server:')
            name = name.strip()

            # If someone cancels out, don't take no for an answer.
            if not ok or name == '': 
                if len(self.combo_server.get_all_items()) == 0: 
                    self._button_save_server_clicked()
                    return
                else:
                    self.combo_server.set_index(1)
                    return
            
            # Add it to the combo and select it
            self.combo_server.add_item(name)

        # Otherwise use what's there.
        else: name = self.combo_server.get_text()

        # Set up the server dictionary / json
        self.server['settings'] = dict()
        for key in self._server_keys:  
            self.server['settings'][key] = eval('self.'+key+'()', dict(self=self))
    
        self.server['uploader'] = dict(
            combo_tracks  = self.combo_tracks.get_text(),
            combo_layouts = self.combo_layouts.get_text(),
            combo_carsets = self.combo_carsets.get_text(),
            list_cars     = self.get_selected_cars(),
        )
        # Include the shown car settings for the current carset, which may have changed
        if not 'carsets' in self.server: self.server['carsets'] = dict()
        #self.server['carsets'][self.combo_carsets.get_text()] = self.tree_cars.get_dictionary()[1]

        # Write the file
        if not os.path.exists('servers'): os.makedirs('servers')
        f = open(os.path.join('servers', name+'.json'), 'w', encoding="utf8")
        dump(self.server, f, indent=2)
        f.close()
        
        # Make sure it's selected.
        self.combo_server.set_text(name)
    
    def _button_delete_server_clicked(self, *a): 
        """
        Removes the selected server from the list and deletes the file.
        """
        if self.combo_server() == 0: return
        # print('_button_delete_server_clicked')

        # Get the name, kill the file
        name = self.combo_server.get_text()
        path = os.path.join('servers', name+'.json')
        if os.path.exists(path+'.backup'): os.unlink(path+'.backup')
        os.rename(path, path+'.backup')
        self.combo_server.remove_item(self.combo_server())
        return

    def start_server(self):
        """
        Starts the server
        """
        if self.text_start().strip() == '': return
        self.log('Starting server...')
        self.ssh_command(self.text_start().strip())
        return self

    def stop_server(self):
        """
        Stops the server
        """
        if self.text_stop().strip() == '': return
        self.log('Stopping server...')
        self.ssh_command(self.text_stop().strip())
        return self

    def _button_stop_server_clicked(self, *a):
        """
        Called when someone clicks the "Run Command" button.
        """
        self.stop_server()


    def _button_start_server_clicked(self, *a):
        """
        Called when someone clicks the "Run Command" button.
        """
        self.start_server()

    def _signal_new_exception(self, *a):
        """
        Called when a new exception comes in.
        """
        print('--------------------')
        print(a)
        print('--------------------')

    def save_server_gui(self):
        """
        Saves which server profile is selected, and the send_to selection.
        """
        if self._init: return
        
        gui = dict(
            combo_server=self.combo_server.get_text(),
            combo_send_to=self.combo_send_to.get_text()
        )
        # print('save_server_gui')
        dump(gui, open('server.json', 'w', encoding="utf8"), indent=2)

    def load_server_gui(self):
        """
        Loads the previously selected profile # and send to.
        """
        # print('load_server_gui')
        gui = load_json('server.json')
        if not gui: return

        try: self.combo_server.set_text(gui['combo_server'])
        except Exception as e: print('ERROR: load_server_gui combo_server', e)

        # try: self.combo_send_to.set_text(gui['combo_send_to'])
        # except Exception as e: print('load_server_gui combo_send_to', e)

    def _checkbox_clean_changed(self, e=None):
        """
        Warn the user about this.
        """
        if self.checkbox_clean():
            msg = egg.pyqtgraph.Qt.QtWidgets.QMessageBox()
            msg.setIcon(egg.pyqtgraph.Qt.QtWidgets.QMessageBox.Information)
            msg.setText("WARNING: After uploading, this step will remotely "+
                        "delete all content from the following folders:")
            msg.setInformativeText(
                self.text_remote.get_text()+'/content/cars/\n'+
                self.text_remote.get_text()+'/content/tracks/')
            msg.setWindowTitle("HAY!")
            msg.setStandardButtons(egg.pyqtgraph.Qt.QtWidgets.QMessageBox.Ok)
            msg.exec_()

    def _list_carnames_changed(self, e=None):
        """
        """
        if self._loading_uploader or self._updating_cars: return
        print('_list_carnames_changed')

        # If we changed something, unselect the carset since that's not valid any more
        self.combo_carsets(0)

        # Select the corresponding carnames
        self.send_carnames_to_cars()

        # Sends the car information to the tree, which is likely hidden, since ballast etc is kinda not worth setting per car
        #self.send_cars_to_tree()

        # Update the server json
        self.button_save_server.click()

        # Run common tasks after everything has been changed
        self._after_cars_carnames_changed()


    def _list_cars_changed(self, e=None):
        """
        Just set the carset combo when anything changes.
        """
        if self._loading_uploader or self._updating_cars: return
        # print('_list_cars_changed')

        # If we changed something, unselect the carset since that's not valid any more
        self.combo_carsets(0)

        # Select the corresponding carnames, should not trigger an event
        self.send_cars_to_carnames()

        # Sends the car information to the tree, which is likely hidden, since ballast etc is kinda not worth setting per car
        #self.send_cars_to_tree()

        # Update the server json
        self.button_save_server.click()

        # Run common tasks after everything has been changed
        self._after_cars_carnames_changed()

    def _after_cars_carnames_changed(self):
        """
        This is called after someone has selected cars or carnames and the other list
        has been correspondingly updated.
        """
        print('_after_cars_carnames_changed')

        cars = self.get_selected_cars()
        for car in cars:
            print(car)
            j = self.load_custom_skins_json()
            if car in j: skins = j[car]
            else:        skins = []
            for skin in skins: print(' ', skin)

        if len(cars) == 1: self.button_edit_skins_pack.enable()
        else:              self.button_edit_skins_pack.disable()

    def _button_edit_skins_pack_clicked(self, *a):
        """
        Brings up the skins pack dialog.
        """
        self.choose_custom_skins()


    def choose_custom_skins(self):
        """
        Opens a multi-select dialog and allows you to choose which skins are considered "custom" (for the packs)
        """
        cars = self.get_selected_cars()
        if len(cars) != 1: return

        # Assemble the skins path
        path_skins = os.path.join(self.text_local(), 'content', 'cars', cars[0], 'skins')
        
        # Get the custom skins for this
        j = self.load_custom_skins_json()
        if cars[0] in j: selected_skins = j[cars[0]]
        else:            selected_skins = []
        
        # Let the user choose
        paths = select_multiple_directories(path_skins, selected_skins)
        if paths is not None:
            
            self.log('\n'+cars[0]+' custom skins:')
            for path in paths: self.log(' ', path)
            
            # dump it.
            j[cars[0]] = paths
            self.save_custom_skins_json(j)
        
        else: self.log('\nLeaving '+cars[0]+' skins alone.')

    def send_cars_to_carnames(self):
        """
        Transfers the currently selected cars to carnames.
        """
        # Syncrhonize the selections from this list to the other one
        carnames = []
        for car in self.get_selected_cars(): carnames.append(self.cars[car])
        self.set_list_selection(carnames, self.list_carnames, self._list_carnames_changed)
        
    def send_carnames_to_cars(self):
        """
        Transfers the currently selected carnames to cars.
        """
        # Syncrhonize the selections from this list to the other one
        cars = []
        for car in self.get_selected_carnames(): cars.append(self.srac[car])
        self.set_list_selection(cars, self.list_cars, self._list_cars_changed)
        
    def _combo_mode_changed(self,*e):
        """
        Called when the server mode has changed. Just hides / shows the
        relevant settings.
        """
        # print('_combo_mode_changed')
        premium = self.combo_mode() == SERVER_MODE_PREMIUM


        # Things that show up only when in premium mode
        self.label_remote_championship   .hide(premium)
        self.text_remote_championship    .hide(premium)
        self.label_remote_live_timings   .hide(premium)
        self.text_remote_live_timings    .hide(premium)
        self.button_download_championship.hide(premium)
        #self.label_reset                 .hide(premium)
        #self.text_reset                  .hide(premium)
        self.checkbox_autoweek           .hide(premium)
        #self.checkbox_reset              .hide(premium)

        # Things that show up only in vanilla mode
        # self.label_stop         .show(premium)
        # self.label_start        .show(premium)
        self.label_monitor      .show(premium)
        #self.text_stop          .show(premium)
        #self.text_start         .show(premium)
        #self.button_start_server.show(premium)
        self.text_monitor       .show(premium)
        #self.checkbox_restart   .show(premium)

        # Run the stuff because something changed.
        self._any_server_setting_changed()


    def _button_skins_clicked(self,e):
        """
        Just calls the usual upload with skins_only=True.
        """
        if self.do_skins_only(): self.set_safe_mode(False)
        
    def disconnect(self):
        """
        Disconnects from SSH server.
        """
        if self.ssh:
            self.log('Disconnecting...')
            if self.sftp: self.sftp.close()
            if self.ssh:  self.ssh.close()
            self.ssh  = None
            self.sftp = None
        
        else:
            self.log('Weird? self.disconnect() was called with no connection.')
            

    def connect(self):
        """
        Logs into the SSH server. Will break the existing connection if it exists.
        """
        try:
            # Close any existing connection
            if self.ssh: self.disconnect()

            # Now connect
            self.ssh = paramiko.SSHClient()

            # Skips the "trust this server" stuff.
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Connect
            self.log('Connecting...')
            user, host = self.text_login().split('@')
            self.ssh.connect(host, username=user, password=self.text_password(), 
                            key_filename=os.path.abspath(self.text_pem()))
            self.sftp = self.ssh.open_sftp()

        except Exception as e:
            self.log('ERROR: Could not connect.', e)
            self.disconnect()
            return True

    def update_progress(self, transferred, total, other=None):
        """
        Updates the progress bar. This is called during downloads / uploads.
        """
        x = int(round(100*transferred/total))
        if x != self.transfer_percentage: 
            print('  ', x, '%', end='\r')
            self.transfer_percentage = x
        self.progress_bar.setValue(x)
        self.window.process_events()

    def ssh_command(self, command):
        """
        Runs the supplied command on the existing connection.
        """
        temporary_connection = False
        if not self.ssh: 
            self.connect()
            temporary_connection = True
        
        if not self.ssh:
            self.log('ERROR: Could not connect.')
            return True

        self.log(' >', command.strip())
        stdin, stdout, stderr = self.ssh.exec_command(command.strip())

        # Wait until completed
        exit_status = stdout.channel.recv_exit_status()

        if temporary_connection: self.disconnect()

    def sftp_download(self, source, destination):
        """
        Downloads the remote source file to the local destination.
        """
        if not self.sftp: 
            self.log('ERROR: Cannot download with no connection.')
            return True
        
        # Do the upload
        try:    
            self.sftp.get(source, destination, callback=self.update_progress)
            self.progress_bar.setValue(100)
            self.transfer_percentage = 100
        except Exception as e:
            self.log('ERROR: Could not download', source+'.', e)
            self.disconnect()
            return True

    def sftp_upload(self, source, destination):
        """
        Uploads the source file to the remote destination.
        """

        if not self.sftp: 
            self.log('ERROR: Cannot upload with no connection.')
            return True

        # Do the upload
        try:    
            self.sftp.put(source, destination, callback=self.update_progress)
            self.progress_bar.setValue(100)
            self.transfer_percentage = 100
        except Exception as e:
            self.log('ERROR: Could not upload', source+' to '+destination+'.\n', e)
            self.disconnect()
            return True

    def _button_upload_clicked(self,e,skins_only=False):
        """
        Uploads the current configuration to the server.
        """
        if self.do_upload(skins_only=skins_only): self.set_safe_mode(False)
    
    def set_safe_mode(self, safe_mode=True):
        """
        Disables dangerous controls.
        """
        self.tabs.disable(safe_mode)
        self.grid_top.disable(safe_mode)


    def do_upload(self, skins_only=False):
    
        # Make sure!
        qmb = egg.pyqtgraph.Qt.QtWidgets.QMessageBox
        ret = qmb.question(self.window._window, '******* WARNING *******', "This action can clear the server and overwrite\nthe existing event!", qmb.Ok | qmb.Cancel, qmb.Cancel)
        if ret == qmb.Cancel: return

        self.log('------- GO TIME! --------')
        self.set_safe_mode(True)

        # Remove the uploads directory if it's there.
        if os.path.exists('uploads'): rmtree('uploads')
        if os.path.exists('uploads.zip'): os.remove('uploads.zip')

        # Pre-command
        if self.checkbox_pre() and self.text_precommand().strip() != '':
            self.log('Running pre-command')
            if self.system([self.text_precommand()]): return

        # Generate the appropriate config files; This creates a setups folder if needed
        if self.checkbox_modify() and not skins_only: 
            if self.combo_mode() == SERVER_MODE_VANILLA: self.generate_acserver_cfg()
            elif self.generate_acsm_cfg(): return
        
        # Collect and package all the data
        if self.checkbox_package(): self.package_content(skins_only)
            
        ####################################
        # SERVER STUFF
        
        # Upload the main assetto content
        if self.checkbox_upload():
            if self.connect(): return True

            # Compresses and uploads the 7z, and clean remote files
            if self.upload_content(skins_only): return True

            # Stop server, but only if there is a command, we're not doing skins
            if self.checkbox_restart() and self.text_stop().strip() != '' and not skins_only:
                self.stop_server()

                # Pause to let server shut down, then delete live_timings.json
                if self.text_remote_live_timings().strip() != '':
                    self.log('Removing live_timings.json')
                    if self.ssh_command('rm -f '+self.text_remote_live_timings().strip()): return True
                
            # Remote unzip the upload
            if self.unpack_uploaded_content(skins_only): return True
            
            # If we made a championship.json
            if self.checkbox_modify() and self.combo_mode()==SERVER_MODE_PREMIUM \
            and os.path.exists('championship.json') and not skins_only:
                self.log('Uploading championship.json...')
                if self.sftp_upload('championship.json', self.text_remote_championship()): return True
                
            # Start server
            if self.checkbox_restart() and self.text_start().strip() != '' and not skins_only:
                self.start_server()

            # Restart monitor if enabled, there is a script, we're not just doing skins, and we're in vanilla mode
            if self.checkbox_monitor() and self.text_monitor().strip() != '' \
            and not skins_only and self.combo_mode()==SERVER_MODE_VANILLA:
                self.log('Restarting monitor...')
                if self.ssh_command(self.text_monitor()): return True

            self.disconnect()
        
        # END OF SERVER STUFF
        #########################################

        # Copy the nice cars list to the clipboard
        if self.combo_mode() == SERVER_MODE_VANILLA:
            pyperclip_copy(self.get_nice_selected_cars_string())
            self.log('List copied to clipboard')
            
        # Forward to the supplied URL
        if not skins_only and self.checkbox_url():
            self.button_go_url.click()
            self.button_go_url2.click()

        # Send the discord announcement
        if not skins_only: self.send_discord_announcement()

        # Post-command
        if self.checkbox_post() and self.text_postcommand().strip() != '':
            self.log('Running post-command')
            if self.system([self.text_postcommand()]): return True
        self.log('------- DONE! -------\n')
        self.set_safe_mode(False)

    def package_content(self, skins_only=False):
        """
        Packages all the content. Or just the skins.
        """
        # print('package_content()', skins_only)

        # If we're importing / packaging the skins as well (this function does nothing if no skins folder is supplied)
        self.import_and_package_skins()
        
        # get the tracks and cars folders
        track = self.skcart[self.combo_tracks.get_text()] # Track directory
        cars  = self.get_selected_cars()     # List of car directories

        # Make sure we have at least one car
        if len(cars) == 0:
            self.log('No cars selected?')
            return

        # # Add the missing directories to make skin uploading easier
        # if self.text_skins() != '':
        #     for car in cars:
        #         d = os.path.join(self.text_skins().strip(), 'Cars', car, 'skins')
        #         if not os.path.exists(d): 
        #             self.log('Creating skins folder for', car)
        #             os.makedirs(d, exist_ok=True)

        # Make sure we have a track
        if track == '' and not skins_only:
            self.log('No track selected?')
            return

        # COPY EVERYTHING TO TEMP DIRECTORY
        # Cars: we just need data dir and data.acd (if present)
        if skins_only: self.log('Collecting venue skins for upload:')
        else:          self.log('Collecting venue cars for upload:')
        for car in cars:
            self.log('  '+ self.cars[car])
            self.collect_assetto_files(os.path.join('cars',car), skins_only)

            # Fixed setup
            setup = ''
            if self.checkbox_setup():
                setup = self.text_setup().strip()
                if len(setup): 
                    # Get the "full" folder name
                    setup = car+'/'+setup
                
                    self.log('    Fixed setup:', setup)

                    # Setup path
                    source = os.path.join(os.path.expanduser('~'), 'Documents', 'Assetto Corsa', 'setups', setup)

                    # If the file exists copy it
                    if os.path.exists(source):

                        # Make the directory for the setup
                        destination = os.path.join(os.getcwd(), 'uploads','setups',setup)
                        os.makedirs(os.path.dirname(destination), exist_ok=True)
                        try: copy(source, destination, follow_symlinks=True)
                        except Exception as e: self.log(e)
                    
                    # Setup nonexistent
                    else:
                        self.log('SETUP DOES NOT EXIST:', source)




        # Copy over the carsets folder too.
        if not skins_only: copytree('carsets', os.path.join('uploads','carsets'))

        # Track
        if not skins_only: 
            self.log('Collecting track')
            self.log('  '+track)
            self.collect_assetto_files(os.path.join('tracks', track))

    def upload_content(self, skins_only=False):
        """
        Compresses uploads folder to uploads.zip and uploads it.
        """

        # Server info
        remote  = self.text_remote.get_text()
        
        # Make sure we don't bonk the system with rm -rf
        if not remote.lower().find('assetto') >= 0:
            self.log('Yeah, sorry, to avoid messing with something unintentionally, we enforce that your remote path have the word "assetto" in it.')
            return True

        # If we have uploads to compress
        if os.path.exists('uploads'):
            
            # Compress the files we gathered (MUCH faster upload)
            self.log('Compressing uploads.zip...')
            os.chdir('uploads')
            zip_directory('.', '../uploads.zip', zip_excludes, self.update_progress)
            os.chdir('..')
        
            self.log('Uploading uploads.zip...')
            if self.sftp_upload('uploads.zip', remote+'/uploads.zip'): return True
            # print()

            # If we're cleaning remote files... Note skins only prevents this
            # regardless of the checkbox state.
            if self.checkbox_clean() and not skins_only:
                self.log('Cleaning out old content...')
                if self.ssh_command('rm -rf '+remote+'/content/cars/* '+remote+'/content/tracks/*'): return True



    def unpack_uploaded_content(self, skins_only=False):
        """
        Just unzips the remote uploads.zip, and cleans up local files.
        """
        # Server info
        remote  = self.text_remote.get_text()
        
        # Remove the carsets folder
        if not skins_only:
            self.log('Removing remote carset lists...')
            if self.ssh_command('rm -f '+remote+'/carsets/*'): return True
        
        # Remote extract
        self.log('Extracting remote uploads.zip...')
        if self.ssh_command('7z x -aoa '+remote+'/uploads.zip -o'+remote): return True

        # If the local uploads directory exists.
        if os.path.exists('uploads'):
            self.log('Removing local uploads.')
            rmtree('uploads')
        if os.path.exists('uploads.zip'): os.remove('uploads.zip')

    # JACK! This is where to check for the DDS validity
    def collect_assetto_files(self, source_folder, skins_only=False):
        """
        Copies all the required files from the supplied content folder. 
        source_folder should be something like 'tracks/imola' or 'cars/ks_meow'
        """
        source_folder = os.path.join(self.text_local(),'content',source_folder)
        
        if skins_only:
            source_folder = os.path.join(source_folder, 'skins')

        # File extensions we should copy over. ACSM needs a few extra heavies.
        filetypes = ['ini', 'lut', 'rto', 'acd', 'json']
        if self.combo_mode() == SERVER_MODE_PREMIUM:
            filetypes = filetypes + ['ai', 'bin', 'jpg', 'png', 'JPG', 'PNG']

        # Walk through the directory picking up the key files
        # print('collecting', source_folder)
        for root, dirs, files in os.walk(source_folder):
            for file in files:
                
                # Get the file extension
                ext = os.path.splitext(file)[-1][1:]
                
                # Files we want to actually upload
                if ext in filetypes:
                    
                    # Source path full
                    source = os.path.join(root,file)

                    # Lower case extension
                    o,x = os.path.splitext(source)
                    if x in ['JPG','PNG']:
                        new_source = o+'.'+x.lower()
                        os.rename(source, new_source)
                        # print('-------------------------------------\n',source,'->',new_source)
                        source = new_source
                   
                    # Destination path for uploading
                    destination = os.path.join('uploads', source[len(self.text_local())+1:])
                    
                    # Copy it over, making dirs first
                    os.makedirs(os.path.dirname(destination), exist_ok=True)
                    try: copy(source, destination, follow_symlinks=True)
                    except Exception as e: print('ERROR:', e)

            

    def log(self, *a):
        """
        Logs it.
        """
        a = list(a)
        for n in range(len(a)): a[n] = str(a[n])
        text = ' '.join(a)
        self.text_log.append_text(text)
        print(text)
        self.window.process_events()

    def system(self, command):
        """
        Runs a system command and logs it.
        """
        # print()
        # print(command)
        self._c = command
        self._r = run(self._c, capture_output=True, shell=True)
        if self._r.returncode:
            self.log('--------------------') 
            self.log('ERROR:\n')
            self.log(' '.join(command)+'\n')
            self.log(self._r.stderr.decode('utf-8').strip())
            self.log('--------------------') 
            return 1
        return 0

    def get_nice_selected_cars_string(self):
        """
        Returns and copies a string to the clipboard a list
        for pasting into the google sheet data validation column.
        """

        # Get a string of nice car names for pasting into the data validation
        s = self.combo_carsets.get_text()
        for d in self.get_selected_cars():
            s = s+'\n'+self.cars[d]

        # copy this to the clipboard
        pyperclip_copy(s)
        return s

    def _combo_tracks_changed(self,*e):
        #if self._updating_tracks or self._loading_uploader: return

        if self._refilling_tracks: return
        # print('_combo_tracks_changed (populates layouts)')
        
        track = self.skcart[self.combo_tracks.get_text()]
        if track == '': return

        # Update the layouts selector
        self._refilling_layouts = True
        self.combo_layouts.clear()
        self.stuoyal = dict() # Reverse-lookup for layout directories
        self.layouts = dict() # looup for fancy names

        # Search for the default layout if it exists
        if os.path.exists(os.path.join(self.text_local(),'content','tracks',track,'models.ini')):
            self.combo_layouts.add_item(_default_layout)

        # Search for models_*.ini
        to_sort = [] # list of layouts to sort before adding
        root = os.path.join(self.text_local(), 'content', 'tracks', track, 'models_*.ini')
        paths = glob(root)
        for path in paths:
            layout = os.path.split(path)[-1].replace('models_','').replace('.ini','')

            # Get the layout name
            layoutname = layout
            ui_path = os.path.join(self.text_local(), 'content', 'tracks', track, 'ui', layout, 'ui_track.json')
            if os.path.exists(ui_path): layoutname = load_json(ui_path)['name']

            # Ensure there are no duplicates
            layoutname = layoutname + ' ('+layout+')'

            # Populate the lookup and reverse lookup
            self.layouts[layout] = layoutname
            self.stuoyal[layoutname] = layout

            # Add to list
            to_sort.append(layoutname)

        to_sort.sort()
        for layoutname in to_sort: self.combo_layouts.add_item(layoutname)
        
        # Ada
        self._refilling_layouts = False

        # No need to show nothing...
        if len(self.combo_layouts.get_all_items()) == 0: self.combo_layouts.hide()
        else:                                            self.combo_layouts.show()

        # Get the pitboxes
        self._combo_layouts_changed()
        
        self.button_save_server.click()

    def _combo_layouts_changed(self,*e):
        #if self._updating_tracks or self._loading_uploader: return
        if self._refilling_layouts: return
        # print('_combo_layouts_changed (extracts pitboxes)')
        
        # Paths
        local  = self.text_local()
        track  = self.skcart[self.combo_tracks.get_text()]
        layout = self.combo_layouts.get_text()

        #self.log('Layout:', layout)
        if layout == '': layout = _default_layout
        if layout not in [_default_layout,'']: layout = self.stuoyal[layout]

        # Path to ui.json
        if layout == _default_layout: p = os.path.join(local,'content','tracks',track,'ui',       'ui_track.json')
        else:                         p = os.path.join(local,'content','tracks',track,'ui',layout,'ui_track.json')
        
        if not os.path.exists(p): return

        # Load it and get the pit number
        # print('loading', p)
        self.track = load_json(p)
        if self.track: self.label_pitboxes('('+self.track['pitboxes']+' pit boxes)')
        
        self.button_save_server.click()

    def _combo_carsets_changed(self,e):
        if self._refilling_carsets or self._loading_uploader: return 

        # print('_combo_carsets_changed')
        self.button_load_carset.click()
        
        self._text_filter_cars_changed()

        self._after_cars_carnames_changed()
        #self.send_cars_to_tree()
        #self.button_save_server.click()

    def _button_delete_carset_clicked(self,e):
        """
        Deletes the selected carset.
        """
        # Special case: first element in combo box is new carset
        if self.combo_carsets.get_index() == 0: return

        # Assemble path
        path = os.path.join('carsets', self.combo_carsets.get_text())+'.json'
        if not os.path.exists(path) or os.path.isdir(path): return
        
        # Remove it
        os.remove(path)

        # Select the zeroth
        self.combo_carsets(0)

        # Rebuild
        self.update_carsets()

    def set_list_selection(self, selected, widget, itemSelectionChanged):
        """
        Selects the specified list of cars, without triggering events
        """
        # Disconnect the update signal until the end
        self._updating_cars = True
        #widget.itemSelectionChanged.disconnect()

        # Update the list selection
        widget.clearSelection()
        for s in selected:
            s = s.strip()
            if s != '':
                try:    widget.findItems(s, egg.pyqtgraph.QtCore.Qt.MatchExactly)[0].setSelected(True)
                except: self.log('WARNING: '+s+' not in list')
        
        # Reconnect and call it for good measure.
        self._updating_cars = False
        #widget.itemSelectionChanged.connect(itemSelectionChanged)
        
    def _button_load_carset_clicked(self,e):
        """
        Load the selected carset.
        """
        # print('_button_load_carset_clicked')

        # Special case: first element in combo box is new carset
        if self.combo_carsets.get_index() == 0: return

        # Get the path associated with this
        path = os.path.join('carsets', self.combo_carsets.get_text())+'.json'
        if not os.path.exists(path) or os.path.isdir(path): return
        
        # Load it.
        j = load_json(path)
        # f = open(path, 'r', encoding="utf8")
        # selected = f.read().splitlines()
        # f.close()

        # selected should be a list of car directories
        self.set_list_selection(j['cars'], self.list_cars, self._list_cars_changed)
        self.send_cars_to_carnames()
        #self.send_cars_to_tree()
        
        # Update the other things associated with this carset
        if 'tyres'         in j: self.text_tyres(j['tyres'])
        if 'setup'         in j: self.text_setup(j['setup'])
        if 'setup_enabled' in j: self.checkbox_setup(j['setup_enabled'])
        if 'wear'          in j: self.number_tyre_wear(j['wear'])

        self.button_save_server.click()
        
    def _button_save_carset_clicked(self,e):
        """
        Save the carset, and its options.
        """

        # Special case: first element in combo box is new carset
        if self.combo_carsets.get_index() == 0:
            # print('opening save dialog')
            name, ok = egg.pyqtgraph.Qt.QtWidgets.QInputDialog.getText(self.window._widget, 'New Carset', 'Name your carset:')
            # print('got', name)
            name = name.strip()
            if not ok or name == '': return
            
            # Add it to the combo and select it
            if not name in self.combo_carsets.get_all_items(): self.combo_carsets.add_item(name)

        # Otherwise use what's there. This should actually never get reached...
        else: name = self.combo_carsets.get_text()

        # Write the file
        if not os.path.exists('carsets'): os.makedirs('carsets')
        
        # Assemble the dictionary for the json file
        j = dict(
            cars  = self.get_selected_cars(), 
            tyres = self.text_tyres(),
            setup = self.text_setup(),
            setup_enabled = self.checkbox_setup(),
            wear = self.number_tyre_wear(),
        )
        dump_json(j, os.path.join('carsets', name)+'.json')
        # f = open(os.path.join('carsets', name), 'w', encoding="utf8")
        # for car in self.get_selected_cars(): f.write(car+'\n')
        # f.close()
        
        # Make sure it's selected; also updates the list I guess
        self.combo_carsets.set_text(name)


    def _button_browse_pem_clicked(self, e):
        """
        Pop up the directory selector.
        """
        path = egg.dialogs.load(text='Show me the key file, Johnny Practicehole', default_directory='assetto_pem')
        if(path): self.text_pem(path)

    def _button_browse_precommand_clicked(self, e):
        """
        Pop up the directory selector.
        """
        path = egg.dialogs.load(text='Select a file to run, apex-nerd.', default_directory='assetto_precommand')
        if path: self.text_precommand('"'+path+'"')

    def _button_browse_postcommand_clicked(self, e):
        """
        Pop up the directory selector.
        """
        path = egg.dialogs.load(text='Select a file to run, apex-nerd.', default_directory='assetto_postcommand')
        if(path): self.text_postcommand('"'+path+'"')

    def _button_browse_local_clicked(self, e):
        """
        Pop up the directory selector.
        """
        path = egg.dialogs.select_directory(text='Select the Assetto Corsa directory, apex-nerd.', default_directory='assetto_local')
        if(path):
            self.text_local(path)
            self.button_refresh.click()

    def _button_refresh_clicked(self, *e):
        """
        Refresh cars and tracks
        """
        # print('_button_refresh_clicked')
        self.log('\nScanning content...')

        # Load the carsets, tracks, and cars 
        self.update_cars()
        self.update_tracks()
        self.update_carsets()
        
        # # Load the combo boxes etc to the last state for this server
        self._load_server_uploader()

        self.log('w00t\n')
        

    def get_server_cfg_source(self):
        """
        Returns 'server_cfg.ini.private' if it exists, or 'server_cfg.ini'.
        """
        if os.path.exists('server_cfg.ini.private'): return 'server_cfg.ini.private'
        else: return 'server_cfg.ini'

    def get_entry_string(self, slot, model='', skin=''):
        """
        Assembles an entry string for entry_list.ini.
        """
        s =     '[CAR_'+str(slot)+']\n'
        s = s + 'MODEL='+str(model)+'\n'
        s = s + 'SKIN='+str(skin)+'\n'
        s = s + 'SPECTATOR_MODE=0\n'
        s = s + 'DRIVERNAME=\n'
        s = s + 'TEAM=\n'
        s = s + 'GUID=\n'
        s = s + 'BALLAST=0\n'
        s = s + 'RESTRICTOR=0'
        return s

    def generate_acsm_cfg(self):
        """
        Downloads the specified championship json, modifies it, but does not 
        re-upload.
        """
        self.log('Generating acsm config')
        
        # Make sure we have a championship.
        if not 'championship' in self.server:
            self.log('ERROR: Championship json has not been downloaded yet.')
            return True
        
        # Shortcut to all the data
        c = self.server['championship']

        # Make sure there is a remote championship to upload to
        remote_championship = self.text_remote_championship().strip()
        if remote_championship == '' and self.checkbox_upload(): 
            self.log('No remote championship file specified?')
            return True
        
        # Get basic information useful to both kinds of files.
        selected_cars = self.get_selected_cars()
        track  = self.skcart[self.combo_tracks.get_text()]
        layout = self.combo_layouts.get_text()
        if layout not in [_default_layout, '']: layout = self.stuoyal[layout]
        else:                                   layout = ''

        # Find the number of pitboxes
        N = self.number_slots()
        if 'pitboxes' not in self.track: self.track['pitboxes'] = 0
        N = min(N, int(self.track['pitboxes']))

        # If this has 'Events' then it is a championship json. If not, then assume it is a custom race
        if 'Events' in c:
            self.log('Championship detected...')

            # ID from file name
            c['ID'] = os.path.splitext(os.path.split(remote_championship)[-1])[0]

            # Name
            c['Name'] = self.combo_carsets.get_text()+' @ '+self.track['name']+' ('+self.combo_server.get_text()+')'
            
            # The championship should have one car class for simplicity. We edit it.
            c['Classes'][0]['Name'] = self.combo_carsets.get_text()
            
            # Update the cars list, noting if it's completely changed (no overlap)
            c['Classes'][0]['AvailableCars'] = selected_cars
            
            # One event for simplicity
            e = c['Events'][0]

            # Other race setup
            e['Name'] = self.combo_carsets.get_text()+' @ '+self.track['name']
            e['RaceSetup']['Cars']  = ';'.join(selected_cars)
            e['RaceSetup']['Track']       = track
            e['RaceSetup']['TrackLayout'] = layout
            e['RaceSetup']['LegalTyres']  = self.text_tyres() 
            e['RaceSetup']['TyreWearRate'] = int(self.number_tyre_wear())

            # Reset the signup form, classes and events entrants
            c['SignUpForm']['Responses'] = [] # Always start clean now. Simpler
            c['Classes'][0]['Entrants'] = dict()
            c['Events'][0]['EntryList'] = dict() 
        
            # Update the metadata
            c['Stats']['NumEntrants'] = N
            
            # Dictionary containing list of skins for each car
            skins = dict()

            # Now fill the pitboxes
            for n in range(N):
                
                # Cyclic cars
                entrant_car = selected_cars[n%len(selected_cars)]

                # If there is no list of skins yet or we've used them all get the list
                if not entrant_car in skins or len(skins[entrant_car]) == 0:
                    
                    # Get the list
                    x = os.path.join(self.text_local().strip(),'content','cars',entrant_car,'skins')
                    skins[entrant_car] = next(os.walk(x))[1] # Cool command!
                    
                    # Shuffle it
                    random.shuffle(skins[entrant_car])
                
                # Get the next (shuffled) skin
                skin = skins[entrant_car].pop(0)

                
                    # p = 
                    # The uploads.zip file base folder is content, so we can make a setups folder as well.
                    # Even if 'content' is not zipped I think.

                # In "Classes/Entrants", we have to specify "any_car_model" and "random_skin"
                # So that there aren't a fixed number of each to choose from for the race.
                c['Classes'][0]['Entrants']['CAR_'+str(n+1)] = {
                    "InternalUUID": "%08d-0000-0000-0000-000000000000" % (n+1),
                    "PitBox": n,
                    "Name": "",
                    "Team": "",
                    "GUID": "",

                    # We need to specify the full car if we do fixed setup
                    # This unfortunately places restrictions on the number 
                    # of each type of car. Not a problem with spec races, though.
                    "Model": entrant_car if self.checkbox_setup() else "any_car_model",
                    "Skin" : skin if self.checkbox_setup() else "random_skin",
                    
                    "ClassID": c['Classes'][0]['ID'], # Must match for championship
                    "Ballast":    0, # self.tree_cars[car+'/ballast']    if car+'/ballast'    in self.tree_cars.keys() else 0,
                    "Restrictor": 0, # self.tree_cars[car+'/restrictor'] if car+'/restrictor' in self.tree_cars.keys() else 0,
                    "SpectatorMode": 0,
                    "FixedSetup": entrant_car + '/' + self.text_setup().strip() if self.checkbox_setup() else '',
                    "ConnectAsSpectator": False,
                    "IsPlaceHolder": False}

                # Make the events entrylist match
                c['Events'][0]['EntryList']['CAR_'+str(n)] = dict(c['Classes'][0]['Entrants']['CAR_'+str(n+1)])
        
                # Manually cycle the cars in the event so there are good cars for practice 
                # (default server behavior is annoying)
                c['Events'][0]['EntryList']['CAR_'+str(n)].update({'Model' : entrant_car, })
        
            # Finally, update the schedule, but only if we're in ACSM mode (we must be for this
            # function to have been called!) and the key exists, and it's actually scheduled!
            if self.checkbox_autoweek() \
            and c['Events']             \
            and len(c['Events'])        \
            and 'Scheduled' in c['Events'][0].keys() \
            and parser.isoparse(c['Events'][0]['Scheduled']).year > 1:
                self.log('Auto-Week')
                t0 = parser.isoparse(c['Events'][0]['Scheduled'])
                self.log('  ', t0, '->')

                # Now find the one for next week
                tqf = auto_week(t0)
                self.log('  ', tqf)
                c['Events'][0]['Scheduled'] = tqf.isoformat()

        # Otherwise, we have a custom_race json, which is a bit simpler to modify.
        else:
            self.log('Custom Race Detected...')

            # Name
            c['Name'] = self.combo_carsets.get_text()+' at '+self.track['name']+' ('+self.combo_server.get_text()+')'
            
            # One event for simplicity
            rc = c['RaceConfig']
            
            # Update the cars list, noting if it's completely changed (no overlap)
            rc['MaxClients'] = N
            rc['Cars']  = ';'.join(selected_cars)
            rc['Track']       = track
            rc['TrackLayout'] = layout
            rc['LegalTyres']  = self.text_tyres() 
            
            # Reset the entry list. form, classes and events entrants
            c['EntryList'] = dict() 
        
            # Now fill the pitboxes
            for n in range(N):
                
                # Create an entry for this one.
                # Manually cycle the cars in the event so there are good cars for practice 
                c['EntryList']['CAR_'+str(n)] = {
                    "InternalUUID": "%08d-0000-0000-0000-000000000000" % (n+1),
                    "PitBox": n,
                    "Name": "",
                    "Team": "",
                    "GUID": "",
                    "Model": selected_cars[n%len(selected_cars)],
                    "Skin": "random_skin",
                    "ClassID": "00000000-0000-0000-0000-000000000000",
                    "Ballast":    0, # self.tree_cars[car+'/ballast']    if car+'/ballast'    in self.tree_cars.keys() else 0,
                    "Restrictor": 0, # self.tree_cars[car+'/restrictor'] if car+'/restrictor' in self.tree_cars.keys() else 0,
                    "SpectatorMode": 0,
                    "FixedSetup": selected_cars[n%len(selected_cars)] + '/' + self.text_setup().strip() if self.checkbox_setup() else '',
                    "ConnectAsSpectator": False,
                    "IsPlaceHolder": False}

        # Write the new file.
        self.log('Saving championship')

        # Save it also for uploading...
        f = open('championship.json','w', encoding="utf8")
        dump(c, f, indent=2)
        f.close()

        # And save it to the server config!
        self.button_save_server.click()
        return False

    def generate_acserver_cfg(self):
        """
        Writes the entry_list.ini and server_cfg.ini, and race.json for 
        the vanilla / steam acServer.
        """
        # print('generate_acserver_cfg')
        self.log('Generating acServer config')

        # Get the selected car directories
        cars = self.get_selected_cars()
        if len(cars)==0:
            self.log('OOPS: generate_acserver_cfg() with no cars selected!')
            return

        # Get the selected track directory
        track = self.skcart[self.combo_tracks.get_text()]
        if track == '':
            self.log('OOPS: generate_acserver_cfg() with no track selected!')

        #########################
        # entry_list.ini
        self.log('entry_list.ini')
        
        # now fill the slots
        entries = []
        m = 0 # car index
        N = self.number_slots()
        if 'pitboxes' not in self.track: self.track['pitboxes'] = 0
        N = min(N, int(self.track['pitboxes']))
        for n in range(0, N):

            # Get the next car dir
            car = cars[m]

            # Get the current random skin
            skin = self.skins[car][random.randrange(len(self.skins[car]))]

            # Append the entry
            entries.append(self.get_entry_string(n, car, skin))

            # Cyclic iterate
            m += 1
            if m >= len(cars): m = 0

        # Get the full string!
        s = '\n\n'.join(entries) + '\n'
        # print('\nENTRIES:\n\n'+s)

        # Save entries
        cfg = os.path.join('uploads', 'cfg')
        os.makedirs(cfg, exist_ok=True)

        self.log('entry_list.ini')
        f = open(os.path.join(cfg, 'entry_list.ini'), 'w', encoding="utf8")
        f.write(s)
        f.close()

        #######################
        # server_cfg.ini

        # We have to add the selected cars and track to server_cfg.ini before uploading
        f = open(self.get_server_cfg_source(), 'r', encoding="utf8"); ls = f.readlines(); f.close()
        for n in range(len(ls)):

            # Get the key for this line
            key = ls[n].split('=')[0].strip()

            # Add the list of cars
            if key == 'CARS': ls[n] = 'CARS='+';'.join(cars)+'\n'

            # Add the track
            elif key == 'TRACK': ls[n] = 'TRACK='+track+'\n'

            # Layout
            elif key == 'CONFIG_TRACK': ls[n] = 'CONFIG_TRACK=' \
                + self.stuoyal[self.combo_layouts.get_text()] if self.combo_layouts.get_text() != _default_layout else ''+'\n'

            # Slots
            elif key == 'MAX_CLIENTS': ls[n] = 'MAX_CLIENTS='+str(N)+'\n'

        self.log('server_cfg.ini ('+str(N)+' pit boxes)')
        f = open(os.path.join(cfg, 'server_cfg.ini'), 'w', encoding="utf8");
        f.writelines(ls);
        f.close()

        # Prep the race.json file, which is used to restart the server
        # on race night.
        self.log('Prepping race data:')
        self.race_json = dict()

        # CARSET NAME
        self.log ('  carset')
        if self.combo_carsets() > 0: self.race_json['carset'] = self.combo_carsets.get_text()
        else:                        self.race_json['carset'] = None

        # CARS DICTIONARY (Lookup by nice name)
        self.log('cars')
        self.race_json['cars'] = dict()
        for c in cars: self.race_json['cars'][self.cars[c]] = c
        
        # SKINS
        self.log('skins')
        self.race_json['skins'] = dict()
        for c in cars: self.race_json['skins'][c] = self.skins[c]
        
        # TRACK
        self.log('track')
        self.race_json['track'] = self.track
        self.race_json['track']['directory'] = track.strip()

        # Dump
        self.log('Dumping to race.json')
        dump(self.race_json, open(os.path.join('uploads', 'race.json'), 'w', encoding="utf8"), indent=2, sort_keys=True)



    def get_selected_cars(self):
        """
        Returns a list of selected cars.
        """
        a = []
        for x in self.list_cars.selectedItems(): a.append(x.text())
        a.sort()
        return a

    def get_selected_carnames(self):
        """
        Returns a list of selected carnames.
        """
        a = []
        for x in self.list_carnames.selectedItems(): a.append(x.text())
        a.sort()
        return a

    def update_carsets(self):
        """
        Searches carsets directory and updates combo box.
        """
        #self.log('Updating carsets...')
        # print('update_carsets')

        # Prevents signals
        self._refilling_carsets = True

        # Clear existing
        self.combo_carsets.clear()
        self.combo_carsets.add_item(_unsaved_carset)

        if not os.path.exists('carsets'): os.makedirs('carsets')
        paths = glob(os.path.join('carsets','*.json'))
        carsets = set()
        for path in paths: 
            carset = os.path.split(os.path.splitext(path)[0])[-1]
            carsets.add(carset)
            self.combo_carsets.add_item(carset)

        # Prune extra carsets.
        s = self.server
        if 'carsets' in s:
            
            # Find and loop over / prune extras
            extras = set(s['carsets'].keys()) - carsets
            for key in extras: 
                if key != _unsaved_carset and key in s['carsets']: 
                    # print('  pruning', key)
                    s['carsets'].pop(key)
        
            # Update the file. This screws up the rest of the load process.
            # Just rely on it happening next time there is a save...
            #self.button_save_server.click()
            
        # Enable signals again
        self._refilling_carsets = False

    def update_cars(self):
        """
        Searches through the current assetto directory for all cars, skins, etc.
        """
        # print('update_cars')
        
        # Disconnect the update signal until the end
        self._updating_cars = True
        self.list_cars    .itemSelectionChanged.disconnect()
        self.list_carnames.itemSelectionChanged.disconnect()

        # Clear out the list 
        self.list_cars.clear()
        self.list_carnames.clear()

        # Dictionary to hold all the model names
        self.cars  = dict()
        self.srac  = dict() # Reverse-lookup
        self.skins = dict()

        # Get all the car paths
        for path in glob(os.path.join(self.text_local(), 'content', 'cars', '*')):

            # Get the car's directory name
            dirname = os.path.split(path)[-1]

            # Make sure it exists.
            path_json = os.path.join(path, 'ui', 'ui_car.json')
            if not os.path.exists(path_json): continue

            # Get the fancy car name (the jsons are not always well formatted, so I have to manually search!)
            s = load_json(path_json)

            # Load will fail if there's an issue, returning None
            if s:

                # Remember the fancy name
                name = s['name'] if 'name' in s else dirname
                self.cars[dirname] = name
                self.srac[name]    = dirname

                # Store the list of skins and the index
                self.skins[dirname] = os.listdir(os.path.join(path, 'skins'))
            
            else: self.log('WARNING:', dirname, 'has no/invalid ui/ui_car.json')

        # Sort the car directories and add them to the list.
        self.cars_keys = list(self.cars.keys())
        self.srac_keys = list(self.srac.keys())
        self.cars_keys.sort()
        self.srac_keys.sort()
        for key in self.cars_keys: egg.pyqtgraph.Qt.QtWidgets.QListWidgetItem(key, self.list_cars)
        for key in self.srac_keys: egg.pyqtgraph.Qt.QtWidgets.QListWidgetItem(key, self.list_carnames)
        
        # Filter
        #self._text_filter_cars_changed()
        
        # Reconnect
        self.list_cars    .itemSelectionChanged.connect(self._list_cars_changed)
        self.list_carnames.itemSelectionChanged.connect(self._list_carnames_changed)
    
        self._updating_cars = False

        
    def do_skins_only(self):
        """
        Runs the pre-script (presumably copies latest skins into local assetto),
        even if unchecked, provided it exists, then packages and uploads just 
        the selected car skins, then runs post, even if unchecked, provided it exists.
        """
        # Pre-command
        self.log('------- UPDATING SKINS -------')
        self.set_safe_mode(True)

        # Remove the uploads directory if it's there.
        if os.path.exists('uploads'): rmtree('uploads')
        if os.path.exists('uploads.zip'): os.remove('uploads.zip')

        if self.text_precommand().strip() != '' and self.checkbox_pre():
            self.log('Running pre-command')
            if self.system([self.text_precommand().strip()]): return True

        if self.checkbox_package():
            if self.package_content(True) == 'no cars': return True

        ###################
        # SERVER STUFF

        if self.checkbox_upload():
            if self.connect():                     return True
            if self.upload_content(True):          return True
            if self.unpack_uploaded_content(True): return True
            self.disconnect()
        
        # Post-command
        if self.text_postcommand().strip() != '':
            self.log('Running post-command')
            if self.system([self.text_postcommand().strip()]): return True
        self.log('------- DONE! -------\n')
        self.set_safe_mode(False)


    def update_tracks(self):
        """
        Searches through the assetto directory for all the track folders
        """
        # print('update_tracks')
        # Clear existing
        self._refilling_tracks = True
        self.combo_tracks.clear()
        tracknames_to_sort = []

        # Get all the paths
        #self.log('Updating tracks...')
        paths = glob(os.path.join(self.text_local(), 'content', 'tracks', '*'))
        paths.sort()

        # Lookup table for track to trackname
        self.tracks = dict()
        self.skcart = dict()

        # Loop over all the paths
        for trackpath in paths: 

            
            # Track folder name
            track = os.path.split(trackpath)[-1]
            
            # Simplest case: one layout, with ui_track.json right there
            ui_default = os.path.join(trackpath, 'ui', 'ui_track.json')
            if os.path.exists(ui_default):
                x = load_json(ui_default)
                if x and 'name' in x: trackname = x['name']
                else: self.log('WARNING:', ui_default, 'did not load.')

            # Complicated case: many layouts, each having the same root name
            else:
                # Collect all possible tracknames from layout folders
                tracknames = []
                shortest   = None # shortest trackname
                N = 0 # Min string length for later
                ps = glob(os.path.join(trackpath, 'ui', '*'))
                ps.sort()
                for p in ps:
                    ui_path = os.path.join(p, 'ui_track.json')
                    if os.path.exists(ui_path):
                        tracknames.append(load_json(ui_path)['name'])
                        if N==0 or len(tracknames[-1]) < N: 
                            shortest = tracknames[-1]
                            N = len(shortest)
                #trackname = shortest.split('-')[0].strip()
                trackname = tracknames[0].split('-')[0].strip().split('(')[0].strip()
                
                # Get the shortest track name
                # if shortest: trackname = shortest
                # else:        trackname = track # default to folder name

                #print('  shortest', shortest, tracknames)

                # Let's find the longest matching substring they all contain
                # max_substr = ""
    
                # # Try all possible substrings of the shortest string
                # for i in range(len(shortest)):
                #     for j in range(i + len(max_substr) + 1, len(shortest) + 1):
                #         substring = shortest[i:j]
                #         # Check if this substring exists in all other strings
                #         if all(substring in s for s in tracknames):
                #             if len(substring) > len(max_substr):
                #                 max_substr = substring
                # trackname = max_substr
                # print('  trackname', trackname)

                # Find the index at which the strings diverge
                # for n in range(N):
                    
                #     # Get the next characters to compare
                #     to_compare = []
                #     for i in range(len(tracknames)): to_compare.append(tracknames[i][n])

                #     print(n, to_compare)
                #     # If they are not identical, quit
                #     if len(set(to_compare)) > 1: 
                #         trackname = shortest[0:n]
                #         break

                # Clear the '-' and spaces.
                # trackname = trackname.replace('-','').strip()

                # If it's nothing, use track
                if trackname == '': trackname = track

            # Store the lookup and reverse-lookup.
            self.tracks[track] = trackname
            self.skcart[trackname] = track
                
            # add to the list to sort
            tracknames_to_sort.append(trackname)

        # Sort them
        tracknames_to_sort.sort()

        # Add them
        for trackname in tracknames_to_sort: self.combo_tracks.add_item(trackname)

        # Ada
        self._refilling_tracks = False


# Start the show!
self = Uploader()