#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import glob, codecs, os, shutil, pathlib, random, json, pyperclip, webbrowser
import spinmob.egg as egg
egg.gui.egg_settings_path = os.path.join(egg.settings.path_home, 'ac_server_uploader')

# GUI class for configuring the server
class server():

    def __init__(self):

        ######################
        # Set the working directory to that of the script
        a = os.path.abspath(__file__)
        d = os.path.dirname(a)
        os.chdir(d)

        # Make sure we have a carset folder
        if not os.path.exists('carsets'): os.mkdir('carsets')

        # Other variables
        self.track = dict()
        self.style_category = 'color:blue; font-size:14pt; font-weight:bold'
        self.style_fancybutton = 'background-color: blue; color: white; font-weight:bold'

        ######################
        # Build the GUI

        # Main window
        self.window = egg.gui.Window('Assetto Corsa Uploader', autosettings_path='window')

        # Tabs
        self.tabs = self.window.add(egg.gui.TabArea(autosettings_path='tabs'))
        self.tab_settings = self.tabs.add('Settings')
        self.tab_uploader = self.tabs.add('Uploader')

        # Log
        self.text_log = self.window.add(egg.gui.TextLog())
        self.text_log.append_text('Welcome to AC Uploader!\n')

        #######################
        # SETTINGS

        # Server stuff
        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Login:'))
        self.text_login = self.tab_settings.add(egg.gui.TextBox('username@ec2-whatever.compute.amazonaws.com', autosettings_path='text_login'), alignment=0)

        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('keyfile.pem:'))
        self.text_pem          = self.tab_settings.add(egg.gui.TextBox('C:\\path\\to\\whatever.pem', autosettings_path='text_pem'), alignment=0)
        self.button_browse_pem = self.tab_settings.add(egg.gui.Button('Browse', signal_clicked=self._button_browse_pem_clicked))

        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Remote Path:'))
        self.text_remote = self.tab_settings.add(egg.gui.TextBox('/home/username/path/to/assettocorsa', autosettings_path='text_remote'), alignment=0)

        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Restart Command:'))
        self.text_restart = self.tab_settings.add(egg.gui.TextBox('/home/username/restart-servers', autosettings_path='text_restart'), alignment=0)

        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Local Path:'))
        self.text_local          = self.tab_settings.add(egg.gui.TextBox('C:\\path\\to\\assettocorsa', autosettings_path='text_local'), alignment=0)
        self.button_browse_local = self.tab_settings.add(egg.gui.Button('Browse', signal_clicked=self._button_browse_local_clicked))

        self.tab_settings.set_row_stretch(20)

        self.tab_settings.new_autorow()
        self.tab_settings.add(egg.gui.Label('Post-Upload URL:'))
        self.text_url = self.tab_settings.add(egg.gui.TextBox('', autosettings_path='text_url'), alignment=0)

        #############################
        # UPLOADER
        self.tab_uploader.set_row_stretch(5)

        # Refresh button
        self.button_refresh = self.tab_uploader.add(egg.gui.Button('Refresh Tracks and Cars',signal_clicked=self._button_refresh_clicked), alignment=0)
        self.button_refresh.set_style(self.style_fancybutton)

        self.tab_uploader.new_autorow()
        self.tab_uploader.add(egg.gui.Label('\nTrack').set_style(self.style_category))

        self.tab_uploader.new_autorow()
        self.grid2a = self.tab_uploader.add(egg.gui.GridLayout(False))

        # Track combo
        self.combo_tracks  = self.grid2a.add(egg.gui.ComboBox([], signal_changed=self._combo_tracks_changed ), alignment=0).set_minimum_width(200)
        self.combo_layouts = self.grid2a.add(egg.gui.ComboBox([], signal_changed=self._combo_layouts_changed), alignment=0).set_minimum_width(200)
        self.label_pitboxes= self.grid2a.add(egg.gui.Label('(0 pit boxes)'))

        # Grid for car controls (save/load, etc)
        self.tab_uploader.new_autorow()
        self.tab_uploader.add(egg.gui.Label('\nCars').set_style(self.style_category))
        self.tab_uploader.new_autorow()
        self.grid2b = self.tab_uploader.add(egg.gui.GridLayout(False), alignment=0)

        # Save load buttons
        self.combo_carsets = self.grid2b.add(egg.gui.ComboBox(['[New Carset]']), alignment=0)
        self.grid2b.set_column_stretch(0)
        self.button_load = self.grid2b.add(egg.gui.Button('Load', signal_clicked=self._button_load_clicked))
        self.button_save = self.grid2b.add(egg.gui.Button('Save', signal_clicked=self._button_save_clicked))
        self.button_delete = self.grid2b.add(egg.gui.Button('Delete', signal_clicked=self._button_delete_clicked))

        # Grid for car list
        self.tab_uploader.new_autorow()
        self.grid2c = self.tab_uploader.add(egg.gui.GridLayout(False), alignment=0)

        # Car list
        self.list_cars = self.grid2c.add(egg.pyqtgraph.QtGui.QListWidget(), alignment=0, column_span=3)
        self.list_cars.setSelectionMode(egg.pyqtgraph.QtGui.QAbstractItemView.ExtendedSelection)
        #self.list_cars.itemSelectionChanged.connect(self._list_cars_changed)

        # Server stuff
        self.tab_uploader.new_autorow()
        self.tab_uploader.add(egg.gui.Label('\nServer').set_style(self.style_category))
        self.tab_uploader.new_autorow()

        self.grid2s = self.tab_uploader.add(egg.gui.GridLayout(margins=False), alignment=0).set_column_stretch(2)
        self.grid2s.add(egg.gui.Label('Max Pit Boxes:'))
        self.number_slots = self.grid2s.add(egg.gui.NumberBox(16, bounds=(1,100), int=True, autosettings_path='number_slots'))

        # upload button
        self.button_upload = self.grid2s.add(egg.gui.Button('Upload and Restart Server!', signal_clicked=self._button_upload_clicked), alignment=0)
        self.button_upload.set_style(self.style_fancybutton)
        self.grid2s.set_column_stretch(2)

        # Test mode
        self.checkbox_test = self.grid2s.add(egg.gui.CheckBox('Test Mode', autosettings_path='checkbox_test'))

        # Show it.
        self.window.show()

        ###################
        # Load tracks and cars
        self.button_refresh.click()
        self.update_carsets()

        # Do this after updating carsets to avoid issues
        self.combo_carsets.signal_changed.connect(self._combo_carsets_changed)

    def _button_upload_clicked(self,e):
        """
        Uploads the current configuration to the server.
        """
        self.log('\n------- UPLOADING TO SERVER --------')

        # Make sure it's clean
        if os.path.exists('uploads')   : shutil.rmtree('uploads')
        if os.path.exists('uploads.7z'): os.remove('uploads.7z')

        # get the tracks and cars
        track = self.combo_tracks.get_text() # Track directory
        cars  = self.get_selected_cars()     # List of car directories

        # Make sure we have at least one car
        if len(cars) == 0:
            self.log('No cars selected?')
            return

        # Make sure we have a track
        if track == '':
            self.log('No track selected?')
            return

        # Make base directory structure
        temp_content = os.path.join('uploads', 'content')
        temp_cars    = os.path.join('uploads', 'content', 'cars')
        temp_tracks  = os.path.join('uploads', 'content', 'tracks')
        os.makedirs(temp_content)
        os.makedirs(temp_cars)
        os.makedirs(temp_tracks)

        # Local assetto path
        local = os.path.abspath(self.text_local.get_text())

        #######################################################
        # Copy all the files we need to a temporary directory

        # Cars: we just need data dir and data.acd (if present)
        self.log('\nPrepping cars:')
        for car in cars:
            self.log('  '+ self.cars[car])
            d = os.path.join(local, 'content', 'cars', car, 'data')

            # Look for directory first
            if os.path.exists(d):
                c = os.path.abspath(os.path.join(temp_cars, car))
                os.makedirs(c, exist_ok=True)
                shutil.copytree(d, os.path.join(c,'data'))

            # Now do the acd
            if os.path.exists(d+'.acd'):
                c = os.path.abspath(os.path.join(temp_cars, car))
                os.makedirs(c, exist_ok=True)
                shutil.copy(d+'.acd', os.path.join(c,'data.acd'))

        # Copy the nice cars list to the clipboard
        pyperclip.copy(self.get_nice_selected_cars_string())
        self.log('List copied to clipboard.')
        if self.text_url() != '':
            self.log('Launching supplied URL...')
            webbrowser.open(self.text_url())

        # Tracks: all .ini just to be safe (and more like the server)
        self.log('\nPrepping track:')
        self.log('  '+track)
        d = os.path.join(local, 'content', 'tracks', track)
        for s in pathlib.Path(d).rglob('*.ini'):

            # Get the relative path
            r = os.path.join(*s.parts[s.parts.index(track)+1:])

            # Destination
            x = os.path.abspath(os.path.join(temp_tracks, track, r))

            # Copy it over
            os.makedirs(os.path.dirname(x), exist_ok=True)
            shutil.copy(s, x)

        # Writes the server_cfg.ini files based on selection.
        self.generate_cfg()

        ####################################
        # Info json file
        self.log('\nPrepping race data:')
        self.race_json = dict()

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
        self.log('Dumping to race.json...')
        json.dump(self.race_json, open(os.path.join('uploads', 'race.json'), 'w'), indent=2, sort_keys=True)

        ####################################
        # SERVER STUFF
        self.log('\nServer stuff:')

        # Server info
        login  = self.text_login.get_text()
        pem    = os.path.abspath(self.text_pem.get_text())
        remote = self.text_remote.get_text()
        restart = self.text_restart.get_text()

        # Make sure we don't bonk the system with rm -rf
        if not remote.lower().find('assetto') >= 0:
            self.log('  Yeah, no, for safety reasons, we enforce that your remote path have the word "assetto" in it.')
            return

        self.log('  Compressing to uploads.7z...')
        os.chdir('uploads')
        c = '7z a ../uploads.7z *'
        if(os.system(c)): self.log('  UH OH!')
        os.chdir('..')

        # Upload the archive
        self.log('  Uploading uploads.7z...')
        c = 'scp -i "' + pem + '" uploads.7z '+login+':"'+remote+'"'
        print(c)
        if self.checkbox_test(): self.log('    (skipped in test mode)')
        else:                    self.system(c)

        # Remote extract
        self.log('  Extracting remote uploads.7z...')
        c = 'ssh -i "'+pem+'" '+login+' 7z x -aoa steam/assetto/uploads.7z -o./steam/assetto/'
        print(c)
        if self.checkbox_test(): self.log('    (skipped in test mode)')
        else:                    self.system(c)

        # Restart server
        self.log('  Restarting server...')
        print(c)
        c = 'ssh -i "'+pem+'" '+login+' '+restart
        if self.checkbox_test(): self.log('    (skipped in test mode)')
        else:                    self.system(c)

        # # Clean up the mess
        if self.checkbox_test(): self.log('  No cleanup in test mode.')
        else:
            self.log('  Cleaning up...')
            if os.path.exists('uploads')   : shutil.rmtree('uploads')
            if os.path.exists('uploads.7z'): os.remove('uploads.7z')

        self.log('\nDone! Hopefully!')

    def log(self, *a):
        """
        Logs it.
        """
        a = list(a)
        for n in range(len(a)): a[n] = str(a[n])
        self.text_log.append_text(' '.join(a))
        self.window.process_events()

    def system(self, command):
        """
        Runs a system command and logs it.
        """
        r = os.system(command)
        if r!=0: self.log('  UH OH! See console!')

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

    def _combo_tracks_changed(self,e):
        track = self.combo_tracks.get_text()
        if track == '': return

        # Update the layouts selector
        self.combo_layouts.clear()

        # Search for models_*.ini
        paths = glob.glob(os.path.join(self.text_local(), 'content', 'tracks', track, 'models_*.ini'))
        for path in paths:
            layout = os.path.split(path)[-1].replace('models_','').replace('.ini','')
            self.combo_layouts.add_item(layout)

    def _combo_layouts_changed(self,e):
        # Paths
        local  = self.text_local()
        track  = self.combo_tracks.get_text()
        layout = self.combo_layouts.get_text()

        # Path to ui.json
        if layout == '': p = os.path.join(local,'content','tracks',track,'ui',       'ui_track.json')
        else:            p = os.path.join(local,'content','tracks',track,'ui',layout,'ui_track.json')
        if not os.path.exists(p): return

        # Load it and get the pit number
        self.track = json.load(open(p, 'r'))
        self.label_pitboxes('('+self.track['pitboxes']+' pit boxes)')

    def _combo_carsets_changed(self,e): self.button_load.click()

    def upload_file(self, path):
        """
        Just uplaods a file relative to this script's working directory.
        """
        # Server info
        login  = self.text_login.get_text()
        pem    = os.path.abspath(self.text_pem.get_text())
        remote = self.text_remote.get_text()

        # Upload path
        c = 'scp -i "' + pem + '" "'+path+'" '+login+':"'+remote+'"'
        print(c)
        self.system(c)

    def _button_delete_clicked(self,e):
        """
        Deletes the selected carset.
        """
        # Special case: first element in combo box is new carset
        if self.combo_carsets.get_index() == 0: return

        # remove it
        os.remove(os.path.join('carsets', self.combo_carsets.get_text()))

        # Rebuild
        self.update_carsets()

    def _button_load_clicked(self,e):
        """
        Load the selected carset.
        """

        # Special case: first element in combo box is new carset
        if self.combo_carsets.get_index() == 0: return

        # Load it.
        f = open(os.path.join('carsets', self.combo_carsets.get_text()), 'r')
        selected = eval(f.read())
        f.close()

        # Update the list selection
        self.list_cars.clearSelection()
        for s in selected:
            self.list_cars.findItems(s, egg.pyqtgraph.QtCore.Qt.MatchExactly)[0].setSelected(True)

    def _button_save_clicked(self,e):
        """
        Save the carset.
        """

        # Special case: first element in combo box is new carset
        if self.combo_carsets.get_index() == 0:
            name, ok = egg.pyqtgraph.QtGui.QInputDialog.getText(egg.pyqtgraph.QtGui.QWidget(), 'New Carset', 'Name your carset:')
            if not ok or name.strip() == '': return

        # Otherwise use what's there.
        else: name = self.combo_carsets.get_text()

        # Get rid of white space
        name = name.strip()

        # Write the file
        f = open(os.path.join('carsets', name), 'w')
        f.write(str(self.get_selected_cars()))
        f.close()

        # Add it to the combo and select it
        self.combo_carsets.add_item(name)
        self.combo_carsets.set_text(name)

    def _button_browse_pem_clicked(self, e):
        """
        Pop up the directory selector.
        """
        path = egg.dialogs.load('Show me the *.pem file, Johnny Practicehole', default_directory='assetto_pem')
        if(path): self.text_pem(path)

    # def _button_browse_zip_clicked(self, e):
    #     """
    #     Pop up the directory selector.
    #     """
    #     path = egg.dialogs.load('Find the 7-zip executable, Prof. Tryhard', default_directory='7zip')
    #     if(path): self.text_zip(path)

    def _button_browse_local_clicked(self, e):
        """
        Pop up the directory selector.
        """
        path = egg.dialogs.select_directory('Select the Assetto Corsa directory, apex-nerd.', default_directory='assetto_local')
        if(path):
            self.text_local(path)
            self.button_refresh.click()

    def _button_refresh_clicked(self, e):
        """
        Refresh cars and tracks
        """
        self.update_tracks()
        self.update_cars()

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

    def generate_cfg(self):
        """
        Writes the entry_list.ini based on self.get_selected_cars().
        """

        # Get the selected car directories
        cars = self.get_selected_cars()
        if len(cars)==0:
            self.log('OOPS: generate_cfg() with no cars selected!')
            return

        # Get the selected track directory
        track = self.combo_tracks.get_text()
        if track == '':
            self.log('OOPS: generate_cfg() with no track selected!')

        #########################
        # entry_list.ini
        self.log('\nGenerating config files...')
        # now fill the slots
        entries = []
        m = 0 # car index
        N = self.number_slots()
        if self.track['pitboxes']: N = min(N, int(self.track['pitboxes']))
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
        f = open(os.path.join(cfg, 'entry_list.ini'), 'w')
        f.write(s)
        f.close()

        #######################
        # server_cfg.ini

        # We have to add the selected cars and track to server_cfg.ini before uploading
        f = open(self.get_server_cfg_source(), 'r'); ls = f.readlines(); f.close()
        for n in range(len(ls)):

            # Get the key for this line
            key = ls[n].split('=')[0].strip()

            # Add the list of cars
            if key == 'CARS': ls[n] = 'CARS='+';'.join(cars)+'\n'

            # Add the track
            elif key == 'TRACK': ls[n] = 'TRACK='+track+'\n'

            # Layout
            elif key == 'CONFIG_TRACK': ls[n] = 'CONFIG_TRACK='+self.combo_layouts.get_text()+'\n'

            # Slots
            elif key == 'MAX_CLIENTS': ls[n] = 'MAX_CLIENTS='+str(N)+'\n'

        self.log('  server_cfg.ini ('+str(N)+' pit boxes)')
        f = open(os.path.join(cfg, 'server_cfg.ini'), 'w');
        f.writelines(ls);
        f.close()


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
        self.log('Updating carsets...')
        # Clear existing
        self.combo_carsets.clear()
        self.combo_carsets.add_item('[New Carset]')

        paths = glob.glob(os.path.join('carsets','*'))
        for path in paths: self.combo_carsets.add_item(os.path.split(path)[-1])

    def update_cars(self):
        """
        Searches through the current assetto directory for all cars, skins, etc.
        """
        # Clear out the list
        self.list_cars.clear()

        # Dictionary to hold all the model names
        self.cars = dict()
        self.skins = dict()

        # Get all the car paths
        paths = glob.glob(os.path.join(self.text_local(), 'content', 'cars', '*'))
        self.log('Updating cars...')
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

    def update_tracks(self):
        """
        Searches through the assetto directory for all the track folders
        """
        # Clear existing
        self.combo_tracks.clear()

        # Get all the paths
        self.log('Updating tracks...')
        paths = glob.glob(os.path.join(self.text_local(), 'content', 'tracks', '*'))
        paths.sort()
        for path in paths:
            self.combo_tracks.add_item(os.path.split(path)[-1])




# Start the show!
self = server()