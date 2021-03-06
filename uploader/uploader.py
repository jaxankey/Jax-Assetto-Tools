#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import glob, codecs, os, sys, shutil, random, json, pyperclip, webbrowser, stat
import dateutil, subprocess, time, datetime, importlib

# Change to the directory of this script depending on whether this is a "compiled" version or run as script
if os.path.split(sys.executable)[-1] == 'uploader.exe': os.chdir(os.path.dirname(sys.executable)) # For executable version
else:                                                   os.chdir(os.path.dirname(os.path.abspath(__file__)))
print('WORKING DIRECTORY:')
print(os.getcwd())

import spinmob.egg as egg

_default_layout = '[default layout]'
_unsaved_carset = '[Unsaved Carset]'
_create_new_profile = '[Create New Profile]'

# Get the last argument, which can be used to automate stuff
if len(sys.argv): print('LAST ARGUMENT:', sys.argv[-1])

# Function for loading a json at the specified path
def load_json(path):
    """
    Load the supplied path with all the safety measures and encoding etc.
    """
    try:
        if os.path.exists(path):
            f = open(path, 'r', encoding='utf8', errors='replace')
            j = json.load(f, strict=False)
            f.close()
            return j
    except Exception as e:
        print('ERROR: Could not load', path)
        print(e)

def rmtree(top):
    """
    Implemented to take care of chmodding
    """
    for root, dirs, files in os.walk(top, topdown=False):
        for name in files:
            filename = os.path.join(root, name)
            os.chmod(filename, stat.S_IWUSR)
            os.remove(filename)
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    os.rmdir(top)

# GUI class for configuring the server
class Uploader:
    """
    GUI class for uploading content and restarting the assetto server.
    """

    def __init__(self, show=True, blocking=True):

        # If we're in executable mode, close the splash screen
        if '_PYIBoot_SPLASH' in os.environ and importlib.util.find_spec("pyi_splash"):
            import pyi_splash # Warning is ok; we don't get here outside of executable mode.
            pyi_splash.update_text('UI Loaded ...')
            pyi_splash.close()

        # For troubleshooting; may not work
        # self.timer_exceptions = egg.gui.TimerExceptions()
        # self.timer_exceptions.signal_new_exception.connect(self._signal_new_exception)
        # self.timer_exceptions.start()

        # Flag for whether we're in the init phases
        self._init = True
        self._loading_server    = False
        self._loading_uploader  = False
        self._refilling_layouts = False
        self._refilling_tracks  = False
        self._refilling_carsets = False

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
            signal_changed=self._combo_server_changed)).set_width(150)
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
        self.text_log = self.window.add(egg.gui.TextLog(), alignment=0).set_minimum_width(150).set_maximum_width(350)
        self.text_log.append_text('Welcome to AC Uploader!')



        #######################
        # SETTINGS

        # Server stuff
        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Mode:'))
        self.combo_mode = self.tab_settings.add(egg.gui.ComboBox(['Steam acServer', 'Server Manager'],
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
        self.text_stop = self.tab_settings.add(egg.gui.TextBox('/home/username/stop-server',
            tip='Remote path to a script that stops the server prior to modifying / uploading.',
            signal_changed=self._any_server_setting_changed), alignment=0)

        self.tab_settings.new_autorow()
        self.label_start = self.tab_settings.add(egg.gui.Label('Start Server Command:'))
        self.text_start = self.tab_settings.add(egg.gui.TextBox('/home/username/start-servers',
            tip='Remote path to a script that starts the server.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        self.button_start_server = self.tab_settings.add(egg.gui.Button('Run Command',
            signal_clicked=self._button_start_server_clicked,
            tip='Run the command using the SSH parameters above.'))

        self.tab_settings.new_autorow()
        self.label_monitor = self.tab_settings.add(egg.gui.Label('Restart Monitor Command:'))
        self.text_monitor = self.tab_settings.add(egg.gui.TextBox('/home/username/restart-monitor',
            tip='Remote path to a script that restarts the monitor.',
            signal_changed=self._any_server_setting_changed), alignment=0)

        self.tab_settings.new_autorow()
        self.label_remote_championship = self.tab_settings.add(egg.gui.Label('Remote Championship JSON:'))
        self.text_remote_championship = self.tab_settings.add(egg.gui.TextBox('/home/username/server-manager/json/championships/blah-blah-blah.json',
            tip='Remote path to the championship json we wish to update. Requires json mode in\nserver-manager\'s config.yml.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        self.button_download_championship = self.tab_settings.add(egg.gui.Button('Download',
            tip='Download the specified championship into the server.json file.',
            signal_clicked = self._button_download_championship_clicked))

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
            tip='Optional command to run before everything begins.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        self.button_browse_precommand = self.tab_settings.add(egg.gui.Button('Browse',
            tip='Opens a dialog to let you select a script file or something.',
            signal_clicked=self._button_browse_precommand_clicked))



        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Post-Command:'))
        self.text_postcommand = self.tab_settings.add(egg.gui.TextBox('',
            tip='Optional command to run after everything is done.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        self.button_browse_postcommand = self.tab_settings.add(egg.gui.Button('Browse',
            tip='Opens a dialog to let you select a script file or something.',
            signal_clicked=self._button_browse_postcommand_clicked))


        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Post-Command:'))
        self.text_postcommand = self.tab_settings.add(egg.gui.TextBox('',
            tip='Optional command to run after everything is done.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        self.button_browse_postcommand = self.tab_settings.add(egg.gui.Button('Browse',
            tip='Opens a dialog to let you select a script file or something.',
            signal_clicked=self._button_browse_postcommand_clicked))


        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Custom Skins:'))
        self.text_skins = self.tab_settings.add(egg.gui.TextBox('',
            tip='Optional path to a custom skins folder (containing a content folder).\n' +\
                'Setting this will package the selected carset skins in content folder.',
            signal_changed=self._any_server_setting_changed), alignment=0)
        self.button_browse_skins = self.tab_settings.add(egg.gui.Button('Browse',
            tip='Opens a dialog to let you select the custom skins directory.',
            signal_clicked=self._button_browse_skins_clicked))




        #############################
        # UPLOADER
        self.tab_uploader.set_row_stretch(5)

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
        self.tab_uploader.add(egg.gui.Label('\nCars').set_style(self.style_category))
        self.tab_uploader.new_autorow()
        self.grid2b = self.tab_uploader.add(egg.gui.GridLayout(False), alignment=0)

        # Save load buttons
        self.combo_carsets = self.grid2b.add(egg.gui.ComboBox([_unsaved_carset],
            signal_changed=self._combo_carsets_changed,
            tip='Select a carset (if you have one saved)!'), alignment=0)
        self.grid2b.set_column_stretch(0)
        self.button_load = self.grid2b.add(egg.gui.Button('Load',
            tip='Load the selected carset.', signal_clicked=self._button_load_clicked))
        self.button_save = self.grid2b.add(egg.gui.Button('Save',
            tip='Save / overwrite the selected carset with the selection below.\nIf [Unsaved Carset] is selected, this pops up a dialog to name the carset.',
            signal_clicked=self._button_save_clicked))
        self.button_delete = self.grid2b.add(egg.gui.Button('Delete',
            tip='Delete the selected carset.',
            signal_clicked=self._button_delete_clicked))

        # Grid for car list
        self.tab_uploader.new_autorow()
        self.grid2c = self.tab_uploader.add(egg.gui.GridLayout(False), alignment=0)

        # Car list
        self.list_cars = self.grid2c.add(egg.pyqtgraph.QtGui.QListWidget(), alignment=0, column_span=3)
        self.list_cars.setSelectionMode(egg.pyqtgraph.QtGui.QAbstractItemView.ExtendedSelection)
        self.list_cars.itemSelectionChanged.connect(self._list_cars_changed)

        self.tab_uploader.new_autorow()
        self.grid_tyres = self.tab_uploader.add(egg.gui.GridLayout(False))
        self.grid_tyres.add(egg.gui.Label('Allowed Tyres:'))
        self.text_tyres = self.grid_tyres.add(egg.gui.TextBox('V;H;M;S;ST;SM;SV',
            tip='Allowed tyres list, usually one or two capital characters, separated by semicolons.',
            signal_changed=self._any_server_setting_changed))

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
        self.checkbox_restart = self.grid2s.add(egg.gui.CheckBox(
            'Restart Server', signal_changed=self._any_server_setting_changed,
            tip='Stop the server before upload and restart after upload.'))
        self.checkbox_monitor = self.grid2s.add(egg.gui.CheckBox(
            'Restart Monitor', signal_changed=self._any_server_setting_changed,
            tip='Restart the monitor after upload and server restart.'))
        self.checkbox_url = self.grid2s.add(egg.gui.CheckBox(
            'URL(s)', signal_changed=self._any_server_setting_changed,
            tip='Open the specified URL in your browser.'))
        self.checkbox_post  = self.grid2s.add(egg.gui.CheckBox(
            'Post', signal_changed=self._any_server_setting_changed,
            tip='Run the post-command after everything is done.'))

        # upload button
        self.tab_uploader.new_autorow()
        self.grid_go = self.tab_uploader.add(egg.gui.GridLayout(False), alignment=0)

        self.button_upload = self.grid_go.add(egg.gui.Button(
            'Full Upload', tip='Packages the required server data, uploads, restarts the server, cleans up the local files.',
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
        self.combo_send_to = self.grid_go.add(egg.gui.ComboBox([])).set_width(120)

        # List of items to save associated with each "server" entry in the top combo
        self._server_keys = [
            'combo_mode',
            'text_login',
            'text_port',
            'text_pem',
            'text_local',
            'text_remote',
            'text_start',
            'text_stop',
            'text_monitor',
            'text_remote_championship',
            'text_postcommand',
            'text_precommand',
            'text_url',
            'text_url2',
            'text_skins',
            'text_tyres',
            'number_slots',
            'checkbox_pre',
            'checkbox_modify',
            'checkbox_autoweek',
            'checkbox_package',
            'checkbox_upload',
            'checkbox_clean',
            'checkbox_restart',
            'checkbox_monitor',
            'checkbox_url',
            'checkbox_post',
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
            print('\nAUTOMATED SKINS UPLOAD:')
            for server in sys.argv[-1].split('=')[1].split(';'):
                server = server.strip()

                print('\n\n\n\n----------------------------------------------\nSELECTING '+server)
                self.combo_server.set_text(server)

                print('UPLOADING SKINS')
                self.update_skins(True)

        ######################
        # Show the window; no more commands below this.
        elif show: self.window.show(blocking)

    def import_and_package_skins(self, wait_for_zip=False):
        """
        Copies all the custom skins associated with the currently selected
        carset into the actual assetto content folder, and zips them up for
        distribution.
        """
        skins  = self.text_skins()
        local  = self.text_local()
        carset = self.combo_carsets.get_text()
        cars   = self.get_selected_cars()
        if skins == '' or local == '' or carset == _unsaved_carset or len(cars)==0: return

        self.log('Packaging carset skins')

        # Tidy up the carset
        naughties = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        carset_safe = carset
        for naughty in naughties: carset_safe.replace(naughty,'')

        # Get the path to the zip and delete it if it exists
        packs_path = os.path.join(skins,'Livery Packs')
        if not os.path.exists(packs_path): os.mkdir(packs_path)
        zip_path = os.path.join(packs_path, carset_safe + '.7z')
        if os.path.exists(zip_path): os.remove(zip_path)

        # Permissions hack
        # _orig_copystat = shutil.copystat
        # shutil.copystat = lambda x, y: x

        # Loop over the selected cars and copy them into the main folder
        # Also assemble the zip command
        command = ['7z', '-mx4', '-xr!*desktop.ini', 'a', '"'+zip_path+'"']
        if not wait_for_zip: command = ['start', '"Compressing Skins"']+command
        for car in cars:
            source   = os.path.join(skins,'content','cars',car)
            destination = os.path.join(local,'content','cars',car)
            if os.path.exists(source):
                print('Copying', source,'\n  ->',destination)
                try: shutil.copytree(source, destination, dirs_exist_ok=True, copy_function=shutil.copy, ignore=shutil.ignore_patterns('desktop.ini'))
                except Exception as e:
                    self.log('ERROR COPYING', car)
                    try:
                        for x in e.args[0]: self.log(x[-1])
                    except Exception as f:
                        print('I need an adult!', f)

            # Add this to the zip command.
            command.append('"' + source + '"')

        # Undo hack
        #shutil.copystat = _orig_copystat

        # Now in a separate thread, start the zip process
        command_string = ' '.join(command)
        print(command_string)
        os.system(command_string)

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
        track  = self.combo_tracks.get_text()
        layout = self.combo_layouts.get_text()
        carset = self.combo_carsets.get_text()
        cars   = self.get_selected_cars()

        try:
            # Now switch to the "send to" server
            self.combo_server.set_text(self.combo_send_to.get_text())

            # Track and layout
            self.combo_tracks.set_text(track)
            if len(self.combo_layouts.get_all_items()) > 0: self.combo_layouts.set_text(layout)

            # +++JACK: Some problem here if we overwrite a carset
            # If we have an unsaved carset, use the list, otherwise just choose the carset
            if carset == _unsaved_carset: self.set_list_cars_selection(cars)
            self.combo_carsets.set_text(carset)

        except Exception as e: print('_button_send_to_clicked', e)

    def _button_go_url_clicked(self, *a):
        """
        Opens the URL in browser.
        """
        if self.text_url() != '':
            self.log('Opening URL 1...')
            webbrowser.open(self.text_url())

    def _button_go_url2_clicked(self, *a):
        """
        Opens the URL in browser.
        """
        if self.text_url2() != '':
            self.log('Opening URL 2...')
            webbrowser.open(self.text_url2())

    # else: self.log('*Skipping URL')
    def _button_download_championship_clicked(self, *a):
        """
        Attempts to download the championship file into the server.json.
        """
        # Server info
        login   = self.text_login.get_text()
        port    = self.text_port .get_text()
        pem     = os.path.abspath(self.text_pem.get_text())

        # Load the championship from the server
        self.log('Downloading championship.json...')
        #c = 'scp -P '+port+' -i "' + pem +'" '+ login+':"'+self.text_remote_championship()+'" championship.json'
        if self.system(['scp', '-T', '-P', port, '-i', pem, login+':"'+self.text_remote_championship()+'"', 'championship.json']):
            self.log('ERROR: Download failed.')
            return

        # load it
        c = load_json('championship.json')
        if not c:
            self.log('ERROR: Could not load championship.json.')
            return

        # Dump it into the server file
        self.log('  Saving contents...')
        self.server['championship'] = c
        self.button_save_server.click()
        self.log('  Done!')



    def update_server_list(self):
        """
        Searches servers directory and updates combo box.
        """
        print('update_server_list')
        
        # Clear existing
        self.combo_server.clear()
        self.combo_server.add_item(_create_new_profile)

        if not os.path.exists('servers'): os.makedirs('servers')
        paths = glob.glob(os.path.join('servers','*.json'))
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
        self.checkbox_restart.set_hidden(self.text_stop() == '' or self.text_start() == '')
        self.checkbox_monitor.set_hidden(self.text_monitor() == '')

    def _combo_server_changed(self, *a):
        """
        When the server combo changes, load it (and remember)
        """
        if self._init: return
        print('_combo_server_changed')

        # If we're on "new server" prompt for a save.
        if self.combo_server() == 0: 
            self.button_save_server.click()
            return

        # Now whatever we've chosen, load it.
        self._button_load_server_clicked()
        self.save_server_gui()

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
        self.server = json.load(f, strict=False)
        f.close()

        # If there is no championship, warn!
        if not 'championship' in self.server and self.server['settings']['combo_mode'] == 1:
            self.log('\n-------\nWARNING: You must download the remote championship json at least once for this server.\n-------\n')

        return self.server

    def _button_clone_server_clicked(self, *a):
        """
        Pops up a dialog and adds a new server with the same settings.
        """
        if self.combo_server() == 0: return

        name, ok = egg.pyqtgraph.QtGui.QInputDialog.getText(egg.pyqtgraph.QtGui.QWidget(), 'New Server Profile', 'Name your new server profile:')
        name = name.strip()

        # If someone cancels out do nothing
        if not ok or name == '': return

        # Otherwise, copy the current selection
        old_path = os.path.join('servers', self.combo_server.get_text()+'.json')
        new_path = os.path.join('servers', name+'.json')
        shutil.copy(old_path, new_path)

        # Add it to the list and select it
        self.combo_server.add_item(name)
        self.combo_server.set_text(name)

    def _button_rename_server_clicked(self, *a):
        """
        Pops up a dialog and adds a new server with the same settings.
        """
        if self.combo_server() == 0: return

        name, ok = egg.pyqtgraph.QtGui.QInputDialog.getText(egg.pyqtgraph.QtGui.QWidget(), 'Rename Server Profile', 'Rename your server profile:')
        name = name.strip()

        # If someone cancels out do nothing
        if not ok or name == '': return

        # Otherwise, copy the current selection
        print('Renaming')
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
        print('_button_load_server_clicked')
        
        # If it's "new server" ask for one
        if self.combo_server() == 0: 
            self.button_save_server.click()
            return

        # Load the server GUI stuff
        self._load_server_settings()

        # Refresh the content based on the assetto path
        self._button_refresh_clicked()

        # Populate the send to combo
        self.combo_send_to.clear()
        for item in self.combo_server.get_all_items():
            if item not in [self.combo_server.get_text(), _create_new_profile]:
                self.combo_send_to.add_item(item)


    def _load_server_settings(self):
        """
        Loads the data for the settings tab only, based on the chosen server.
        """
        print('_load_server_settings')
        self.server = self.load_server_json()
        if not 'settings' in self.server: return
        print('  loaded json')

        self._loading_server = True
        for key in self.server['settings']:
            exec('self.'+key+'.set_value(value)', dict(self=self, value=self.server['settings'][key]))
            #print(' ', key, '->', j['settings'][key])
        self._loading_server = False

    def _load_server_uploader(self):
        """
        Loads the garbage into the uploader for the chosen server.
        """
        print('_load_server_uploader')
        #self.server = self.load_server_json()
        if not 'uploader' in self.server: return
        print('  found uploader key')

        self._loading_uploader = True

        # Now populate everything :)
        try:    
            self.combo_tracks.set_text(self.server['uploader']['combo_tracks'])
            self._combo_tracks_changed() # JACK: redundant, but catches if it's already selected.
        except Exception as e: print('load_upload_gui combo_tracks', e)
        try:    self.combo_layouts.set_text(self.server['uploader']['combo_layouts'], block_signals=True)
        except Exception as e: print('load_upload_gui combo_layouts', e)
        try:    self.combo_carsets.set_text(self.server['uploader']['combo_carsets'])
        except Exception as e: print('load_upload_gui combo_carsets', e)
        
        # List items
        self.set_list_cars_selection(self.server['uploader']['list_cars'])

        self._loading_uploader = False


    def _button_save_server_clicked(self, *a): 
        """
        Saves the current server configuration under the chosen name, or pops up a dialog
        if [New Server] is chosen.
        """
        if self._loading_uploader: return
        print('_button_save_server_clicked')

        # Special case: first element in combo box is new carset
        if self.combo_server() == 0:
            name, ok = egg.pyqtgraph.QtGui.QInputDialog.getText(egg.pyqtgraph.QtGui.QWidget(), 'New Server', 'Name your new server:')
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
            value = eval('self.'+key+'()', dict(self=self))
            self.server['settings'][key] = value

        self.server['uploader'] = dict(
            combo_tracks  = self.combo_tracks.get_text(),
            combo_layouts = self.combo_layouts.get_text(),
            combo_carsets = self.combo_carsets.get_text(),
            list_cars     = self.get_selected_cars(),
        )

        # Write the file
        if not os.path.exists('servers'): os.makedirs('servers')
        f = open(os.path.join('servers', name+'.json'), 'w', encoding="utf8")
        json.dump(self.server, f, indent=2)
        f.close()
        
        # Make sure it's selected.
        self.combo_server.set_text(name)
    
    def _button_delete_server_clicked(self, *a): 
        """
        Removes the selected server from the list and deletes the file.
        """
        if self.combo_server() == 0: return
        print('_button_delete_server_clicked')

        # Get the name, kill the file
        name = self.combo_server.get_text()
        path = os.path.join('servers', name+'.json')
        if os.path.exists(path+'.backup'): os.unlink(path+'.backup')
        os.rename(path, path+'.backup')
        self.combo_server.remove_item(self.combo_server())
        return

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
        print('save_server_gui')
        json.dump(gui, open('server.json', 'w'), indent=2)

    def load_server_gui(self):
        """
        Loads the previously selected profile and send to.
        """
        print('load_server_gui')
        gui = load_json('server.json')
        if not gui: return

        try: self.combo_server.set_text(gui['combo_server'])
        except Exception as e: print('load_server_gui combo_server', e)

        try: self.combo_send_to.set_text(gui['combo_send_to'])
        except Exception as e: print('load_server_gui combo_send_to', e)

    def _checkbox_clean_changed(self, e=None):
        """
        Warn the user about this.
        """
        if self.checkbox_clean():
            msg = egg.pyqtgraph.QtGui.QMessageBox()
            msg.setIcon(egg.pyqtgraph.QtGui.QMessageBox.Information)
            msg.setText("WARNING: After uploading, this step will remotely "+
                        "delete all content from the following folders:")
            msg.setInformativeText(
                self.text_remote.get_text()+'/content/cars/\n'+
                self.text_remote.get_text()+'/content/tracks/')
            msg.setWindowTitle("HAY!")
            msg.setStandardButtons(egg.pyqtgraph.QtGui.QMessageBox.Ok)
            msg.exec_()
        
    def _list_cars_changed(self, e=None):
        """
        Just set the carset combo when anything changes.
        """
        if self._loading_uploader: return
        print('_list_cars_changed')
        self.combo_carsets(0)
        self.button_save_server.click()

    def _combo_mode_changed(self,*e):
        """
        Called when the server mode has changed. Just hides / shows the
        relevant settings.
        """
        print('_combo_mode_changed')
        premium = self.combo_mode.get_index() == 1

        # Settings tab
        self.label_remote_championship   .hide(premium)
        self.text_remote_championship    .hide(premium)
        self.button_download_championship.hide(premium)
        self.label_stop         .show(premium)
        self.label_start        .show(premium)
        self.label_monitor      .show(premium)
        self.text_stop          .show(premium)
        self.text_start         .show(premium)
        self.button_start_server.show(premium)
        self.text_monitor       .show(premium)

        # Uploader tab
        self.checkbox_restart .show(premium)
        self.checkbox_autoweek.hide(premium)

        self._any_server_setting_changed()


    def _button_skins_clicked(self,e):
        """
        Just calls the usual upload with skins_only=True.
        """
        self.update_skins()

    def start_server(self):
        """
        Runs the start server command over ssh.
        """
        login   = self.text_login.get_text()
        port    = self.text_port .get_text()
        pem     = os.path.abspath(self.text_pem.get_text())
        start   = self.text_start.get_text()   # For acsm
        
        if start.strip() != '':
            self.log('Starting server...')
            #c = 'ssh -p '+port+' -i "'+pem+'" '+login+' "'+start+'"' 
            if self.system(['ssh', '-T', '-p', port, '-i', pem, login, start]): return

    def _button_upload_clicked(self,e,skins_only=False):
        """
        Uploads the current configuration to the server.
        """
        # Make sure! +++
        qmb = egg.pyqtgraph.QtGui.QMessageBox
        ret = qmb.question(self.window._window, '******* WARNING *******', "This action can clear the server and overwrite\nthe existing championship!", qmb.Ok | qmb.Cancel, qmb.Cancel)
        if ret == qmb.Cancel: return

        self.log('\n------- GO TIME! --------')

        # Pre-command
        if self.checkbox_pre() and self.text_precommand().strip() != '':
            self.log('Running pre-command')
            if self.system([self.text_precommand()]): return



        # Generate the appropriate config files
        if self.checkbox_modify() and not skins_only: 
            if self.combo_mode() == 0: self.generate_acserver_cfg()
            elif self.generate_acsm_cfg(): return
        #else: self.log('*Skipping server config')
        
        # Collect and package all the data
        if self.checkbox_package():
            
            # Package the content
            self.package_content(skins_only)
            
        # Package not checked
        #else: self.log('*Skipping package')

        
        ####################################
        # SERVER STUFF
        
        # Server info
        login   = self.text_login.get_text()
        port    = self.text_port .get_text()
        pem     = os.path.abspath(self.text_pem.get_text())
        stop    = self.text_stop.get_text()    # For acsm
        start   = self.text_start.get_text()   # For acsm
        monitor = self.text_monitor.get_text() 

        # Upload the main assetto content
        if self.checkbox_upload():
            
            # Upload the 7z, and clean remote files
            if self.upload_content(skins_only): return True
    
            # Stop server, but only if there is a command, we're not doing skins, and we're in vanilla mode
            if self.checkbox_restart() and stop != '' and not skins_only and self.combo_mode()==0:
                self.log('Stopping server...')
                #c = 'ssh -p '+port+' -i "'+pem+'" '+login+' "'+stop+'"' 
                if self.system(['ssh', '-T', '-p', port, '-i', pem, login, stop]): return True
            #else: self.log('*Skipping server stop')
                
            # Remote unzip the upload
            if self.unpack_uploaded_content(skins_only): return True
            
            # If we made a championship.json
            if self.checkbox_modify() and self.combo_mode()==1 \
            and os.path.exists('championship.json') and not skins_only:
                # Upload it
                self.log('Uploading championship.json...')
                #c = 'scp -P '+port+' -i "' + pem +'" championship.json '+ login+':"'+self.text_remote_championship()+'"'
                if self.system(['scp', '-T', '-P', port, '-i', pem, 'championship.json', login+':"'+self.text_remote_championship()+'"']): return True
                
            # Start server
            if self.checkbox_restart() and start != '' and not skins_only and self.combo_mode()==0:
                self.start_server()
            #else: self.log('*Skipping server start')

            # Restart monitor if enabled, there is a script, we're not just doing skins, and we're in vanilla mode
            if self.checkbox_monitor() and monitor != '' and not skins_only and self.combo_mode()==0:
                self.log('Restarting monitor...')
                #c = 'ssh -p '+port+' -i "'+pem+'" '+login+' "'+monitor+'"' 
                if self.system(['ssh', '-T', '-p', port, '-i', pem, login, monitor]): return True
            #else: self.log('*Skipping monitor restart')

        # No upload
        #else: self.log('*Skipping upload')

        # Copy the nice cars list to the clipboard
        if self.combo_mode() == 0:
            pyperclip.copy(self.get_nice_selected_cars_string())
            self.log('List copied to clipboard')
            
        # Forward to the supplied URL
        if self.checkbox_url():
            self.button_go_url.click()
            self.button_go_url2.click()

        # Post-command
        if self.checkbox_post() and self.text_postcommand().strip() != '':
            self.log('Running post-command')
            if self.system([self.text_postcommand()]): return True
        self.log('------- DONE! -------\n')


    def package_content(self, skins_only=False, wait_for_zip=False):
        """
        Packages all the content. Or just the skins.
        """
        print('package_content()', skins_only, wait_for_zip)

        # If we're importing / packaging the skins as well (this function does nothing if no skins folder is supplied)
        self.import_and_package_skins(wait_for_zip)

        # Make sure it's clean
        if os.path.exists('uploads'): rmtree('uploads')
        if os.path.exists('uploads.7z'): os.remove('uploads.7z')
        
        # get the tracks and cars
        track = self.combo_tracks.get_text() # Track directory
        cars  = self.get_selected_cars()     # List of car directories

        # Make sure we have at least one car
        if len(cars) == 0:
            self.log('No cars selected?')
            return

        # Make sure we have a track
        if track == '' and not skins_only:
            self.log('No track selected?')
            return

        # COPY EVERYTHING TO TEMP DIRECTORY
        # Cars: we just need data dir and data.acd (if present)
        if skins_only: self.log('Collecting skins')
        else:          self.log('Collecting cars')
        for car in cars:
            self.log('  '+ self.cars[car])
            self.collect_assetto_files(os.path.join('cars',car), skins_only)

        # Copy over the carsets folder too.
        if not skins_only: shutil.copytree('carsets', os.path.join('uploads','carsets'))

        # Track
        if not skins_only: 
            self.log('Collecting track')
            self.log('  '+track)
            self.collect_assetto_files(os.path.join('tracks', track))

    def upload_content(self, skins_only=False):
        """
        Uploads uploads.7z and unpacks it remotely (if checked).
        """

        # Server info
        login   = self.text_login.get_text()
        port    = self.text_port .get_text()
        pem     = os.path.abspath(self.text_pem.get_text())
        remote  = self.text_remote.get_text()
        
        # Make sure we don't bonk the system with rm -rf
        if not remote.lower().find('assetto') >= 0:
            self.log('Yeah, sorry, to avoid messing with something unintentionally, we enforce that your remote path have the word "assetto" in it.')
            return True

        # If we have uploads to compress
        if os.path.exists('uploads'):
            
            # Compress the files we gathered (MUCH faster upload)
            self.log('Compressing uploads.7z')
            os.chdir('uploads')
            #c = '7z a ../uploads.7z *'
            if self.system(['7z', 'a', '../uploads.7z', '*']): 
                os.chdir('..')
                return True
            os.chdir('..')
        
            self.log('Uploading uploads.7z...')
            #c = 'scp -P '+port+' -i "' + pem + '" uploads.7z '+login+':"'+remote+'"'
            if self.system(['scp', '-T', '-P', port, '-i', pem, 'uploads.7z', login+':"'+remote+'"']): return True

            # If we're cleaning remote files... Note skins only prevents this
            # regardless of the checkbox state.
            if self.checkbox_clean() and not skins_only:
                self.log('Cleaning out old content...')
                #c = 'ssh -p '+port+' -i "'+pem+'" '+login+' rm -rf ' + remote + '/content/cars/* ' + remote + '/content/tracks/*'
                if self.system(['ssh', '-T', '-p', port, '-i', pem, login, 'rm -rf '+remote+'/content/cars/* '+remote+'/content/tracks/*']): return True

    def unpack_uploaded_content(self, skins_only=False):
        """
        Just unzips the remote uploads.7z, and cleans up local files.
        """
        # Server info
        login   = self.text_login.get_text()
        port    = self.text_port .get_text()
        pem     = os.path.abspath(self.text_pem.get_text())
        remote  = self.text_remote.get_text()
        
        # Back to the upload process
        if os.path.exists('uploads'):

            # Remove the carsets folder
            if not skins_only:
                self.log('Removing remote carset lists...')
                if self.system(['ssh', '-T', '-p', port,'-i',pem,login, 'rm -rf '+remote+'/carsets']): return True
            
            # Remote extract
            self.log('Extracting remote uploads.7z...')
            #c = 'ssh -p '+port+' -i "'+pem+'" '+login+' 7z x -aoa ' + remote + '/uploads.7z' + ' -o' + remote
            if self.system(['ssh', '-T', '-p', port,'-i',pem,login,'7z x -aoa '+remote+'/uploads.7z -o'+remote]): return True

            self.log('Removing local uploads.')
            rmtree('uploads')
            if os.path.exists('uploads.7z'): os.remove('uploads.7z')

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
        if self.combo_mode.get_index() == 1:
            filetypes = filetypes + ['ai', 'bin', 'jpg', 'png', 'JPG', 'PNG']

        # Walk through the directory picking up the key files
        print('collecting', source_folder)
        for root, dirs, files in os.walk(source_folder):
            for file in files:
                
                if os.path.splitext(file)[-1][1:] in filetypes:
                    
                    # Source path full
                    source = os.path.join(root,file)
                    
                    # Lower case extension
                    o,x = os.path.splitext(source)
                    if x in ['JPG','PNG']:
                        new_source = o+'.'+x.lower()
                        os.rename(source, new_source)
                        print('-------------------------------------\n',source,'->',new_source)
                        source = new_source
                   
                    # Destination path for uploading
                    destination = os.path.join('uploads', source[len(self.text_local())+1:])
                    
                    # Copy it over, making dirs first
                    os.makedirs(os.path.dirname(destination), exist_ok=True)
                    try: shutil.copy(source, destination, follow_symlinks=True)
                    except Exception as e: print(e)

            

    def log(self, *a):
        """
        Logs it.
        """
        a = list(a)
        for n in range(len(a)): a[n] = str(a[n])
        text = ' '.join(a)
        self.text_log.append_text(text)
        print('LOG:',text)
        self.window.process_events()

    def system(self, command):
        """
        Runs a system command and logs it.
        """
        print()
        print(command)
        #r = os.system(command)
        self._c = command
        self._r = subprocess.run(self._c, capture_output=False, shell=True)
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
        pyperclip.copy(s)
        return s

    def _combo_tracks_changed(self,*e):
        #if self._updating_tracks or self._loading_uploader: return

        if self._refilling_tracks: return
        print('_combo_tracks_changed (populates layouts)')
        
        track = self.combo_tracks.get_text()
        if track == '': return

        # Update the layouts selector
        self._refilling_layouts = True
        self.combo_layouts.clear()

        # Search for the default layout if it exists
        if os.path.exists(os.path.join(self.text_local(),'content','tracks',track,'models.ini')):
            self.combo_layouts.add_item(_default_layout)

        # Search for models_*.ini
        root = os.path.join(self.text_local(), 'content', 'tracks', track, 'models_*.ini')
        print(root)
        paths = glob.glob(root)
        for path in paths:
            layout = os.path.split(path)[-1].replace('models_','').replace('.ini','')
            self.combo_layouts.add_item(layout)
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
        print('_combo_layouts_changed (extracts pitboxes)')
        
        # Paths
        local  = self.text_local()
        track  = self.combo_tracks.get_text()
        layout = self.combo_layouts.get_text()

        # Path to ui.json
        if layout == _default_layout: p = os.path.join(local,'content','tracks',track,'ui',       'ui_track.json')
        else:                         p = os.path.join(local,'content','tracks',track,'ui',layout,'ui_track.json')
        if not os.path.exists(p): return

        # Load it and get the pit number
        print('loading', p)
        self.track = load_json(p)
        self.label_pitboxes('('+self.track['pitboxes']+' pit boxes)')
        
        self.button_save_server.click()

    def _combo_carsets_changed(self,e):
        if self._refilling_carsets or self._loading_uploader: return 

        print('_combo_carsets_changed')
        self.button_load.click()
        self.button_save_server.click()

    def _button_delete_clicked(self,e):
        """
        Deletes the selected carset.
        """
        # Special case: first element in combo box is new carset
        if self.combo_carsets.get_index() == 0: return

        # remove it
        os.remove(os.path.join('carsets', self.combo_carsets.get_text()))

        # Select the zeroth
        self.combo_carsets(0)

        # Rebuild
        self.update_carsets()

    def set_list_cars_selection(self, selected):
        """
        Selects the specified list of cars.
        """
        # Disconnect the update signal until the end
        self.list_cars.itemSelectionChanged.disconnect()

        # Update the list selection
        self.list_cars.clearSelection()
        for s in selected:
            s = s.strip()
            if s != '':
                try:    self.list_cars.findItems(s, egg.pyqtgraph.QtCore.Qt.MatchExactly)[0].setSelected(True)
                except: self.log('WARNING: '+s+' not in list')
        
        # Reconnect
        self.list_cars.itemSelectionChanged.connect(self._list_cars_changed)
                

    def _button_load_clicked(self,e):
        """
        Load the selected carset.
        """
        print('Load carset button clicked')

        # Special case: first element in combo box is new carset
        if self.combo_carsets.get_index() == 0: return

        # Get the path associated with this
        path = os.path.join('carsets', self.combo_carsets.get_text())
        if not os.path.exists(path) or os.path.isdir(path): return
        
        # Load it.
        f = open(path, 'r', encoding="utf8")
        selected = f.read().splitlines()
        f.close()

        self.set_list_cars_selection(selected)
        
        self.button_save_server.click()
        
    def _button_save_clicked(self,e):
        """
        Save the carset.
        """

        # Special case: first element in combo box is new carset
        if self.combo_carsets.get_index() == 0:
            name, ok = egg.pyqtgraph.QtGui.QInputDialog.getText(egg.pyqtgraph.QtGui.QWidget(), 'New Carset', 'Name your carset:')
            name = name.strip()
            if not ok or name == '': return
            
            # Add it to the combo and select it
            if not name in self.combo_carsets.get_all_items(): self.combo_carsets.add_item(name)

        # Otherwise use what's there. This should actually never get reached...
        else: name = self.combo_carsets.get_text()

        # Write the file
        if not os.path.exists('carsets'): os.makedirs('carsets')
        f = open(os.path.join('carsets', name), 'w', encoding="utf8")
        for car in self.get_selected_cars(): f.write(car+'\n')
        f.close()
        
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
        print('_button_refresh_clicked')
        self.log('\nScanning content...')

        # Load the carsets, tracks, and cars 
        self.update_cars()
        self.update_tracks()
        self.update_carsets()
        
        # # Load the combo boxes etc to the last state for this server
        self._load_server_uploader()

        self.log('  w00t')
        

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
        
        # Server info
        # login   = self.text_login.get_text()
        # port    = self.text_port .get_text()
        # pem     = os.path.abspath(self.text_pem.get_text())

        # Load the championship from the server    
        # JACK: Downloading causes the problem where there are all kinds of results that won't go away and you can't restart it.    
        # self.log('Downloading championship.json')
        # #c = 'scp -P '+port+' -i "' + pem +'" '+ login+':"'+self.text_remote_championship()+'" championship.json'
        # if self.system(['scp', '-T', '-P', port, '-i', pem, login+':"'+self.text_remote_championship()+'"', 'championship.json']): return True
        #c = load_json('championship.json')
        if not 'championship' in self.server:
            self.log('ERROR: Championship json has not been downloaded yet.')
        c = self.server['championship']

        # Make sure there is a remote championship to upload to
        remote_championship = self.text_remote_championship().strip()
        if remote_championship == '': 
            self.log('No remote championship file specified?')
            return
        
        # ID from file name
        c['ID'] = os.path.splitext(os.path.split(remote_championship)[-1])[0]

        # Whether the venue has changed
        new_venue = False

        # Name
        new_name = self.combo_carsets.get_text()+' at '+self.track['name']+' ('+self.combo_server.get_text()+')'
        # if c['Name'] != new_name: 
        #     print('Venue:', c['Name'], '->', new_name)
        #     new_venue = True
        c['Name'] = new_name
        
        # One car class for simplicity
        x = c['Classes'][0]
        carset = self.combo_carsets.get_text()
        if x['Name'] != carset: 
            print('VENUE Carset:', x['Name'], '->', carset)
            new_venue = True
        x['Name'] = carset
        
        # Update the cars list, noting if it's completely changed (no overlap)
        selected_cars = self.get_selected_cars()
        if len(set(x['AvailableCars']).intersection(set(selected_cars))) == 0: 
            print('VENUE Cars:', x['AvailableCars'], '->', selected_cars)
            new_venue = True
        x['AvailableCars'] = selected_cars
        
        # One event for simplicity
        e = c['Events'][0]
        
        # Other race setup
        e['RaceSetup']['Cars']  = ';'.join(self.get_selected_cars())
        track  = self.combo_tracks.get_text()
        layout = self.combo_layouts.get_text()
        if layout == _default_layout: layout = ''

        # For this new_venue stuff to work, we'd have to download the entrants
        # From the championship, but we cannot ALWAYS download the championship because
        # it becomes irreparably mutilated after an event.
        # if e['RaceSetup']['Track']       != track \
        # or e['RaceSetup']['TrackLayout'] != layout:
        #     print('VENUE Track or Layout change.')
        #     new_venue = True
        e['RaceSetup']['Track'] = track
        e['RaceSetup']['TrackLayout'] = layout
        e['RaceSetup']['LegalTyres'] = self.text_tyres() # JACK: UNPACK AND SCRAPE DATA.ACD? GROSS!!
        
        # Reset the signup form, but only if the venue has changed.
        # if new_venue:
        #     self.log('New venue detected, clearing signup.')
        # JACK:
        c['SignUpForm']['Responses'] = []
        
        # Now that we know if there are still responses, 
        # We can fill up the Entrants and EntryList
        x['Entrants'] = dict()
        c['Events'][0]['EntryList'] = dict()
    
        # Find the number of pitboxes
        N = self.number_slots()
        if 'pitboxes' not in self.track: self.track['pitboxes'] = 0
        N = min(N, int(self.track['pitboxes']))

        # Update the metadata
        c['Stats']['NumEntrants'] = N
        
        # Now fill the pitboxes
        # JACK: Classes,Entrants must have an entry for everyone in
        #       the SignupForm Responses
        #R = c['SignUpForm']['Responses']
        for n in range(N):
            x['Entrants']['CAR_'+str(n+1)] = {
                "InternalUUID": "%08d-0000-0000-0000-000000000000" % (n+1),
                "PitBox": n,
                "Name": "",
                "Team": "",
                "GUID": "",
                "Model": "any_car_model",
                "Skin": "random_skin",
                "ClassID": "00000000-0000-0000-0000-000000000000",
                "Ballast": 0,
                "SpectatorMode": 0,
                "Restrictor": 0,
                "FixedSetup": "",
                "ConnectAsSpectator": False,
                "IsPlaceHolder": False}
            c['Events'][0]['EntryList']['CAR_'+str(n)] = dict(x['Entrants']['CAR_'+str(n+1)])
     
            # Manually cycle the cars (default server behavior is annoying)
            c['Events'][0]['EntryList']['CAR_'+str(n)].update({
                'Model' : selected_cars[n%len(selected_cars)], })
     
            # If we have a response in the sign-up form, modify the entrants
            # if n < len(R):
            #     x['Entrants']['CAR_'+str(n+1)].update({
            #         'Name' : R[n]['Name'],
            #         'GUID' : R[n]['GUID'],
            #         'Team' : R[n]['Team'],
            #         'Model': R[n]['Car'],
            #         'Skin' : R[n]['Skin'], })

        # Finally, update the schedule, but only if we're in ACSM mode (we must be for this
        # function to have been called!) and the key exists
        if self.checkbox_autoweek() and c['Events'][0]['Scheduled']:
            self.log('  Auto-Week')
            self.log('  ',c['Events'][0]['Scheduled'], '->')

            # Parse the scheduled timestamp and add the qualifying time.
            tq = dateutil.parser.isoparse(c['Events'][0]['Scheduled'])

            # Go backwards to before our time, then forward to the first week after now.
            week = datetime.timedelta(days=7)
            while tq.timestamp() > time.time(): tq -= week
            while tq.timestamp() < time.time(): tq += week

            self.log('  ', tq.isoformat())
            c['Events'][0]['Scheduled'] = tq.isoformat()

        # Write the new file.
        self.log('Saving championship')

        # Save it also for uploading...
        f = open('championship.json','w', encoding="utf8")
        json.dump(c, f, indent=2)
        f.close()

        # And save it to the server config!
        self.button_save_server.click()
        return False

    def generate_acserver_cfg(self):
        """
        Writes the entry_list.ini and server_cfg.ini, and race.json for 
        the vanilla / steam acServer.
        """
        print('generate_acserver_cfg')
        self.log('Generating acServer config')

        # Get the selected car directories
        cars = self.get_selected_cars()
        if len(cars)==0:
            self.log('OOPS: generate_acserver_cfg() with no cars selected!')
            return

        # Get the selected track directory
        track = self.combo_tracks.get_text()
        if track == '':
            self.log('OOPS: generate_acserver_cfg() with no track selected!')

        #########################
        # entry_list.ini
        self.log('  entry_list.ini')
        
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
        print('\nENTRIES:\n\n'+s)

        # Save entries
        cfg = os.path.join('uploads', 'cfg')
        os.makedirs(cfg, exist_ok=True)

        self.log('  entry_list.ini')
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
                +self.combo_layouts.get_text() if self.combo_layouts.get_text() != _default_layout else ''+'\n'

            # Slots
            elif key == 'MAX_CLIENTS': ls[n] = 'MAX_CLIENTS='+str(N)+'\n'

        self.log('  server_cfg.ini ('+str(N)+' pit boxes)')
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
        self.log('  cars')
        self.race_json['cars'] = dict()
        for c in cars: self.race_json['cars'][self.cars[c]] = c
        #json.dump(cars_dictionary, open(os.path.join('uploads', 'cars.txt'), 'w'))

        # SKINS
        self.log('  skins')
        self.race_json['skins'] = dict()
        for c in cars: self.race_json['skins'][c] = self.skins[c]
        #json.dump(skins, open(os.path.join('uploads', 'skins.txt'), 'w'))

        # TRACK
        self.log('  track')
        self.race_json['track'] = self.track
        self.race_json['track']['directory'] = track.strip()

        # Dump
        self.log('Dumping to race.json')
        json.dump(self.race_json, open(os.path.join('uploads', 'race.json'), 'w', encoding="utf8"), indent=2, sort_keys=True)



    def get_selected_cars(self):
        """
        Returns a list of selected cars.
        """
        a = []
        for x in self.list_cars.selectedItems(): a.append(x.text())
        a.sort()
        return a

    def update_carsets(self):
        """
        Searches carsets directory and updates combo box.
        """
        #self.log('Updating carsets...')
        print('update_carsets')

        # Prevents signals
        self._refilling_carsets = True

        # Clear existing
        self.combo_carsets.clear()
        self.combo_carsets.add_item(_unsaved_carset)

        if not os.path.exists('carsets'): os.makedirs('carsets')
        paths = glob.glob(os.path.join('carsets','*'))
        for path in paths: self.combo_carsets.add_item(os.path.split(path)[-1])

        # Enable signals again
        self._refilling_carsets = False

    def update_cars(self):
        """
        Searches through the current assetto directory for all cars, skins, etc.
        """
        print('update_cars')
        
        # Disconnect the update signal until the end
        self.list_cars.itemSelectionChanged.disconnect()

        # Clear out the list 
        self.list_cars.clear()

        # Dictionary to hold all the model names
        self.cars = dict()
        self.skins = dict()

        # Get all the car paths
        paths = glob.glob(os.path.join(self.text_local(), 'content', 'cars', '*'))
        #self.log('Updating cars...')
        for path in paths:

            # Get the car's directory name
            dirname = os.path.split(path)[-1]

            # Make sure it exists.
            path_json = os.path.join(path, 'ui', 'ui_car.json')
            if not os.path.exists(path_json): continue

            # Get the fancy car name (the jsons are not always well formatted, so I have to manually search!)
            f = codecs.open(path_json, 'r', encoding='utf-8')
            s = f.read()
            f.close()

            # Find the index of "name" as the starting point
            i1 = s.find('"name"')
            if i1 >= 0:
                i2 = s.find('"', i1+6)
                if i2 >= 0:
                    i3 = s.find('"', i2+1)
                    if i3 >= 0:
                        try: s[i2+1:i3] + ': ' + dirname
                        except: print(' *[CANNOT PRINT / UNICODE ISSUE]: '+dirname)
                        self.cars[dirname] = s[i2+1:i3]

            # Store the list of skins and the index
            self.skins[dirname] = os.listdir(os.path.join(path, 'skins'))

        # Sort the car directories and add them to the list.
        self.car_directories = list(self.cars.keys())
        self.car_directories.sort()
        for n in self.car_directories: egg.pyqtgraph.QtGui.QListWidgetItem(n, self.list_cars)

        # Reconnect
        self.list_cars.itemSelectionChanged.connect(self._list_cars_changed)
    
    def update_skins(self, wait_for_zip=False):
        """
        Runs the pre-script (presumably copies latest skins into local assetto),
        even if unchecked, provided it exists, then packages and uploads just 
        the selected car skins, then runs post, even if unchecked, provided it exists.
        """
        # Pre-command
        if self.text_precommand().strip() != '' and self.checkbox_pre():
            self.log('Running pre-command')
            if self.system([self.text_precommand()]): return True

        self.log('\n------- UPDATING SKINS -------')
        if self.checkbox_package():
            if self.package_content(True, wait_for_zip) == 'no cars': return True

        if self.checkbox_upload():
            if self.upload_content(True): return True
            if self.unpack_uploaded_content(True): return True
        
        # Post-command
        if self.text_postcommand().strip() != '':
            self.log('Running post-command')
            if self.system([self.text_postcommand()]): return True
        self.log('Done! Hopefully!')

    def update_tracks(self):
        """
        Searches through the assetto directory for all the track folders
        """
        print('update_tracks')
        # Clear existing
        self._refilling_tracks = True
        self.combo_tracks.clear()

        # Get all the paths
        #self.log('Updating tracks...')
        paths = glob.glob(os.path.join(self.text_local(), 'content', 'tracks', '*'))
        paths.sort()
        for path in paths: self.combo_tracks.add_item(os.path.split(path)[-1])
        self._refilling_tracks = False


# Start the show!
u = Uploader()