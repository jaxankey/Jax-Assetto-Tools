#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import codecs
import glob
import json
import os
import shutil
import stat
import sys
import spinmob
import spinmob.egg as egg

from configparser import RawConfigParser as ConfigParser
from numpy import interp, linspace, isnan
from scipy.signal import savgol_filter

# Change to the directory of this script depending on whether this is a "compiled" version or run as script
if os.path.split(sys.executable)[-1] == 'uploader.exe': os.chdir(os.path.dirname(sys.executable)) # For executable version
else:                                                   os.chdir(os.path.dirname(os.path.abspath(__file__)))
print('WORKING DIRECTORY:')
print(os.getcwd())

exceptions = egg.gui.TimerExceptions()

# Function for loading a json at the specified path
def load_json(path):
    """
    Load the supplied path with all the safety measures and encoding etc.
    """
    try: 
        if os.path.exists(path):
            f = codecs.open(path, 'r', 'utf-8-sig', errors='replace')
            j = json.load(f, strict=False)
            f.close()
            return j
    except Exception as e:
        print('ERROR: Could not load', path)
        print(e)

def rmtree(top):
    """
    Implemented to take care of chmod
    """
    def rm_readonly(func, path):
        os.chmod(path, stat.S_IWRITE)
        func(path)
        
    shutil.rmtree(top, onerror=rm_readonly)


# noinspection PyProtectedMember
class Modder:
    """
    GUI class for searching and modding content.
    """

    def __init__(self, blocking=False):

        # When updating cars, we want to suppress some signals.
        self._init_running = True
        self._updating_cars = False
        self._loading_car_data = False
        self._expanding_tree = False
        self._tree_changing = False

        # Other variables
        self.source_power_lut = None # Used to hold the source power.lut data.
        self.cars = dict()  # Car folder keys, car name values
        self.srac = dict()  # Reverse-lookup
        self.skins = dict()
        self.cars_keys = None
        self.srac_keys = None

        # Lookup table for which files to mod, with extra sections possible
        self.ini = {
            'CAR.INI'           : {'RULES': ['MIN_HEIGHT']},
            'DRIVETRAIN.INI'    : {},
            'SUSPENSIONS.INI'   : {},
        }

        # This will hold all the configs with the files above as keys.
        self.ini_files = dict()


        ######################
        # Build the GUI

        # Main window
        self.window = egg.gui.Window('Assetto Corsa Minimodder', size=(1200,700), autosettings_path='window')

        # Top grid controls
        self.grid_top = self.window.add(egg.gui.GridLayout(False), alignment=0)

        self.grid_top.add(egg.gui.Label('Local Assetto Path:'))
        self.text_local = self.grid_top.add(egg.gui.TextBox(
            'C:\\path\\to\\assettocorsa',
            tip='Local path to assettocorsa folder.',
            autosettings_path='text_local'), alignment=0)
        self.button_browse_local = self.grid_top.add(egg.gui.Button('Browse',
            tip='Opens a dialog to let you find the local assettocorsa folder.',
            signal_clicked=self._button_browse_local_clicked))
        self.button_scan = self.grid_top.add(egg.gui.Button('Scan',
            tip='Scans this Assetto directory for content.',
            signal_clicked=self._button_scan_clicked))

        # Combo row
        self.window.new_autorow()
        self.grid_middle = self.window.add(egg.gui.GridLayout(False), alignment=1)
        self.combo_car = self.grid_middle.add(egg.gui.ComboBox([],
            autosettings_path='combo_car',
            signal_changed=self._combo_car_changed,).set_width(180))
        self.combo_car.load_gui_settings(True)
        last_car_index = self.combo_car._lazy_load['self']
        self.button_load_car = self.grid_middle.add(egg.gui.Button(
            'Load Car Data', signal_clicked=self._button_load_car_clicked)).hide()

        self.button_open_car_folder = self.grid_middle.add(egg.gui.Button(
            'Open Car Folder', signal_clicked=self._button_open_car_folder_clicked))

        self.button_create_mod = self.grid_middle.add(egg.gui.Button(
            'Create Mod', signal_clicked=self._button_create_mod_clicked))
        
        self.button_reset_inis = self.grid_middle.add(egg.gui.Button(
            'Reset INI\'s', 
            tip='Undoes all changes to the files below.',
            signal_clicked=self._button_reset_inis_clicked))

        self.button_hide_unchanged = self.grid_middle.add(egg.gui.Button('Hide Unchanged', 
            True, tip='Hides everything that will not be changed.',
            autosettings_path='button_hide'))
        self.button_hide_unchanged.signal_toggled.connect(self._button_hide_unchanged_toggled)


        # Settings and plot row
        self.window.new_autorow()
        self.grid_middle2 = self.window.add(egg.gui.GridLayout(False), alignment=0)
        self.tree = self.grid_middle2.add(egg.gui.TreeDictionary(
            new_parameter_signal_changed=self._tree_changed), row_span=2)
        self.tree.set_minimum_width(400)

        # Settings
        self.tree.add('Mod Tag', 'R')

        self.tree.add('POWER.LUT', False)
        self.set_tree_item_style_header('POWER.LUT')
        
        self.tree.add('POWER.LUT/Restrictor', False)
        self.tree.add('POWER.LUT/Restrictor/Exponent', 0.3, step=0.05)
        self.tree.add('POWER.LUT/Restrictor/RPM Range', 1.0, step=0.05, bounds=(0,None))
        self.tree.add('POWER.LUT/Smooth', False)
        self.tree.add('POWER.LUT/Smooth/Points', 100)
        self.tree.add('POWER.LUT/Smooth/Window', 5)
        self.tree.add('POWER.LUT/Smooth/Order', 3)
        
        
        # Populate those specified outside the file itself        
        for file in self.ini:
            self.tree.add(file, False)
            self.set_tree_item_style_header(file)
            
            for section in self.ini[file]:
                self.tree.add(file+'/'+section, False)
                for key in self.ini[file][section]:
                    self.tree.add(file+'/'+section+'/'+key, '')

        #self.tree.load_gui_settings()
        
        # Make the plotter
        self.plot = self.grid_middle2.add(egg.gui.DataboxPlot(autosettings_path='plot'), alignment=0)

        # Log area
        self.window.new_autorow()
        self.text_log = self.grid_middle2.add(egg.gui.TextLog(), 1,1, alignment=0)

        self.log('Welcome to my silly-ass minimodder!')

        # Scan for content
        self.button_scan.click()
        self.combo_car.set_index(last_car_index)

        self._init_running = False

        # Last pretty steps.
        self.hide_unchanged()
        self.highlight_changed()

        # Show it.
        self.window.show(blocking)

    def _button_hide_unchanged_toggled(self, *a):
        """
        Updates the hidden state.
        """
        self.hide_unchanged()

    def set_tree_item_style_header(self, tree_key):
        """
        Sets the style of the tree key.
        """
        w = self.tree.get_widget(tree_key)
        
        
        f = w.font(0)
        f.setBold(True)
        
        w.setFont(0, f)
        w.setFont(1, f)
        
        color = egg.pyqtgraph.QtGui.QColor(200,200,255)
        w.setBackground(0, color)
        w.setBackground(1, color)
        
    def _button_reset_inis_clicked(self, *a):
        """
        Clears out the jax-minimodder file and reloads the car.
        """
        self.log('Resetting car data:')
        
        car = self.combo_car.get_text()
        path = os.path.join(self.text_local(), 'content', 'cars', car, 'ui', 'jax-minimodder.txt')

        # delete the config file
        if os.path.exists(path):
            self.log('  Deleting ui/jax-minimodder.txt')
            os.unlink(path)
        else: self.log('  Could not find', path)

        # Uncheck them all
        self._tree_changing = True
        for file in self.ini_files: 
            self.tree[file] = False
            for section in self.ini_files[file]: self.tree[file+'/'+section] = False
            for section in self.ini[file]:       self.tree[file+'/'+section] = False
            
        self._tree_changing = False

        # Reload the car
        self.load_car_data()

    def _button_create_mod_clicked(self, *a):
        """
        Duplicates the currently selected car and creates a modded version.
        """

        # Get the mod name and new folder name
        car      = self.combo_car.get_text()
        car_name = self.cars[car]
        car_path = os.path.realpath(os.path.join(self.text_local(), 'content', 'cars', car))
        
        mod_name = car_name + '-'+self.tree['Mod Tag']
        mod_car  = car+'_'+self.tree['Mod Tag'].lower().replace(' ', '_')
        mod_car_path = os.path.realpath(os.path.join(self.text_local(), 'content', 'cars', mod_car))

        # Create a warning dialog and quit if cancelled
        qmb = egg.pyqtgraph.QtGui.QMessageBox
        ret = qmb.question(self.window._window, '******* WARNING *******',
          "This will create the mod '"+mod_name+"' and create / overwrite the folder "+mod_car_path,
          qmb.Ok | qmb.Cancel, qmb.Cancel)
        if ret == qmb.Cancel: return

        self.log('Creating '+mod_name)

        # If the other directory is already there, kill it.
        if os.path.exists(mod_car_path):
            self.log('  Deleting '+mod_car_path)
            rmtree(mod_car_path)

        # Copy the existing mod as is
        self.log('  Copying '+car+' -> '+mod_car)
        shutil.copytree(car_path, mod_car_path)

        # Now update power.lut
        d = self.plot
        if self.tree['POWER.LUT']:
            self.log('  Updating power.lut')
            mod_power_path = os.path.join(mod_car_path,'data','power.lut')
            f = open(mod_power_path, 'w')
            for n in range(len(d[0])):
                if not isnan(d[2][n]):
                    line = '%.1f|%.1f\n' % (d[0][n], d[2][n])
                    f.write(line)
            f.close()

        # Now update the ui.json
        self.log('  Updating ui_car.json')
        mod_ui = os.path.realpath(os.path.join(mod_car_path, 'ui', 'ui_car.json'))
        x = load_json(mod_ui)
        x['name'] = mod_name
        x['torqueCurve'] = []
        x['powerCurve']  = []
        hp = d[0]*d[2]*0.00014
        for n in range(len(d[0])):
            if not isnan(d[2][n]):
                x['torqueCurve'].append(['%.1f' % d[0][n], '%.1f' % d[2][n]])
                x['powerCurve'] .append(['%.1f' % d[0][n], '%.1f' % hp[n]  ])
        x['specs']['bhp']      = '%.0f bhp' % max(hp)
        x['specs']['torque']   = '%.0f Nm'  % max(d[2])
        x['specs']['weight']   = '%s kg'  % self.tree['CAR.INI/BASIC/TOTALMASS']
        x['specs']['pwratio']  = '%.2f kg/bhp' % (float(self.tree['CAR.INI/BASIC/TOTALMASS'])/max(hp))
        x['specs']['topspeed'] = 'buh?'
        x['minimodder'] = self.tree.get_dictionary()[1]
        json.dump(x, open(mod_ui, 'w'), indent=2)

        ##################
        # INI FILES
        ##################
        
        # Update the config parser for each file
        for k in self.tree.keys():
            s = k.split('/')
            file = s[0]
            
            # If it's a file we modify and we have it checked
            if file in self.ini and self.tree[file]:
                    
                # Get the config parser for this file
                c = self.ini_files[file]
                
                # If there is a section
                if len(s) > 1:
                    section = s[1]
                    
                    # If there is not already a section in the config parser, add it
                    if not section in c: c.add_section(section)
                    
                    # If we're supposed to modify the section and there is a key
                    if self.tree[file + '/' + section] and len(s) > 2:
                        
                        # Update the key to the tree value
                        c[section][s[2]] = self.tree[k]
                
        # Write the files
        for file in self.ini_files:
            c = self.ini_files[file]
            self.log('  Writing ', file.lower())
            with open(os.path.join(mod_car_path, 'data', file.lower()),'w') as f: 
                c.write(f, space_around_delimiters=False)

        # Now delete the data.acd
        mod_data_acd = os.path.join(mod_car_path, 'data.acd')
        if os.path.exists(mod_data_acd):
            self.log('  Deleting mod data.acd (don\'t forget to pack!)')
            os.unlink(mod_data_acd)

        # Update sfx
        mod_guids = os.path.join(mod_car_path, 'sfx', 'GUIDs.txt')
        if os.path.exists(mod_guids):
            self.log('  Updating '+mod_guids)
            with open(mod_guids, 'r') as f: s = f.read()
            with open(mod_guids, 'w') as f: f.write(s.replace(car, mod_car))

        # Renaming bank
        self.log('  Renaming '+car+'.bank -> '+mod_car+'.bank')
        os.rename(os.path.join(mod_car_path, 'sfx', car     + '.bank'),
                  os.path.join(mod_car_path, 'sfx', mod_car + '.bank'))

        # Remember our selection and scan
        self.button_scan.click()
        self.combo_car.set_index(self.combo_car.get_index(car))

        # Open the mod car path
        os.startfile(mod_car_path)


    def _button_open_car_folder_clicked(self, *a):
        """
        Opens the car directory.
        """
        car  = self.combo_car.get_text()
        path = os.path.realpath(os.path.join(self.text_local(), 'content', 'cars', car))
        self.log('Opening', path)
        os.startfile(path)

    def _combo_car_changed(self, *a):
        """
        Someone changed the car combo.
        """
        if self._updating_cars: return
        self.log('New car selected.')
        self.load_car_data()

    def _button_load_car_clicked(self, *a):
        """
        Someone clicked the "Load Car Data" button.
        """
        self.load_car_data()

    def reload_ini_files(self):
        """
        Resets self.ini_files to the defaults.
        """
        # Get the path to the car
        car  = self.combo_car.get_text()
        data = os.path.realpath(os.path.join(self.text_local(), 'content', 'cars', car, 'data'))
        
        # Load default settings from the ini files themselves
        for file in self.ini:
            self.log('  Loading', file)
            
            # Load the existing data as dictionary
            c = ConfigParser()
            c.optionxform = str
            c.read(os.path.join(data, file.lower()))
            self.ini_files[file] = c

    def load_car_data(self):
        """
        Loads the car data.
        """
        # Prevent tree events etc
        self._loading_car_data = True

        # Get the path to the car
        car  = self.combo_car.get_text()
        data = os.path.realpath(os.path.join(self.text_local(), 'content', 'cars', car, 'data'))

        self.log('Loading '+car+' data:')
        if not os.path.exists(data):
            self.log('  ERROR: '+ data + ' does not exist. Make sure you have unpacked data.acd.')
            self.button_create_mod.disable()
            self.plot.clear()
            self.plot.plot()
            self.grid_middle2.disable()
            return

        self.log('  Found ' + data)
        self.button_create_mod.enable()
        self.grid_middle2.enable()

        # load power.lut, stick it in an "original" databox, copy to plot, and run the plot
        power_lut = os.path.join(data, 'power.lut')
        self.source_power_lut = spinmob.data.load(power_lut, delimiter='|')

        # Load default settings from the ini files themselves
        for file in self.ini:
            self.log('  Loading', file)
            
            # Load the existing data as dictionary
            c = ConfigParser()
            c.optionxform = str
            c.read(os.path.join(data, file.lower()))
            self.ini_files[file] = c

            # loop over the keys
            for section in c:

                # Add section
                s = file + '/' + section
                if s not in self.tree.keys(): self.tree.add(s, False)
                    
                # Add keys
                for key in c[section]:
                    k = s+'/'+key
                    if k not in self.tree.keys():
                        self.tree.add(k, self.get_ini_value(file, section, key))
                    self.tree[k] = self.get_ini_value(file, section, key)

        # If we have already saved a tree for this car, load that data
        saved_tree_path = os.path.join(self.text_local(), 'content', 'cars', car, 'ui', 'jax-minimodder.txt')
        if os.path.exists(saved_tree_path):
            self.log('  Loading ', saved_tree_path)
            saved_tree = spinmob.data.load(saved_tree_path, header_only=True, delimiter='\t')
            self.tree.update(saved_tree) # No event fired because we're loading car data.

        # Re-enable tree events
        self._loading_car_data = False

        # Expand
        self.expand_tree()
        self.update_curves()

    def get_ini_value(self, file, section, key):
        """
        Returns the value string from self.ini_files.
        """
        if file    in self.ini_files and \
           section in self.ini_files[file] and \
           key     in self.ini_files[file][section]:
               return str(self.ini_files[file][section][key].split(';')[0].strip())
        return None

    def set_tree_item_highlighted(self, key, highlighted=False):
        """
        Sets whether the item is highlighted.
        """
        # Get the widget
        w = self.tree.get_widget(key)
        
        if highlighted: color = egg.pyqtgraph.QtGui.QColor(255,200,200)
        else:           color = w.background(0)
        
        w.setBackground(1, color)

            
    def get_changed_tree_keys(self):
        """
        Loops over the tree keys and returns a list of those changed from the
        car values.
        """
        
        # Reload car data to original values
        self.reload_ini_files()
        
        # Loop over all keys
        changed_keys = []
        for tk in self.tree.keys():
            s = tk.split('/')
            
            # If we're length 3, that means we have file/section/key
            if len(s) < 3: continue
            file, section, key = s
            
            # If the file is not in the config parser set, skip
            if file not in self.ini_files: continue
            
            # Get the config parser for this file
            c = self.ini_files[file]
            
            # If the section isn't in there, we highlight
            if section not in c or self.tree[tk] != self.get_ini_value(file, section, key):  
                changed_keys.append(tk)
                
        return changed_keys
            

    def highlight_changed(self):
        """
        Highlights the changed items.
        """        
        self.log('Highlighting changed items...')
        changed = self.get_changed_tree_keys()
        for tk in self.tree.keys():
            if len(tk.split('/')) == 3:
                self.set_tree_item_highlighted(tk, tk in changed)
            
        

    def hide_unchanged(self):
        """
        Loops through the ini list and hides everything that has not been changed.
        """
        unhide = not self.button_hide_unchanged()
        
        # Reload car data to original values
        self.reload_ini_files()
        
        # Load default settings from the ini files themselves
        for file in self.ini_files:
            c = self.ini_files[file]
            
            # loop over the keys
            for section in c:
                ts = file + '/' + section
                
                # Hide the section if it's unchecked
                self.tree.hide_parameter(ts, self.tree[ts] or unhide)
                
                # Hide keys that aren't different.
                if self.tree[ts]:
                    for key in c[section]:
                        tk = file + '/' + section + '/' + key
                        self.tree.hide_parameter(tk, self.tree[tk] != self.get_ini_value(file, section, key) or unhide)

            # loop over the extras
            for section in self.ini[file]:
                ts = file + '/' + section
                self.tree.hide_parameter(ts, self.tree[ts] or unhide)
                


    def update_curves(self):
        """
        Calculates and updates the plot.
        """
        if not len(self.source_power_lut): return

        # Start clean
        self.plot.clear()
        self.plot.copy_all_from(self.source_power_lut)

        # Update the plot
        x = self.plot[0]
        y = self.plot[1]
        self.plot['Modded'] = y
        self.plot['Scale']  = 0 * x + 1

        if self.tree['POWER.LUT']:

            # If we're smoothing
            if self.tree['POWER.LUT/Smooth']:

                # Sav-Gol filter
                x2 = linspace(min(x),max(x),self.tree['POWER.LUT/Smooth/Points'])
                y2 = interp(x2, x, y)
                x = self.plot[0] = x2
                y = self.plot[1] = savgol_filter(y2, self.tree['POWER.LUT/Smooth/Window'], self.tree['POWER.LUT/Smooth/Order'])

            x0 = max(self.plot[0])*self.tree['POWER.LUT/Restrictor/RPM Range']
            p  = self.tree['POWER.LUT/Restrictor/Exponent']

            if self.tree['POWER.LUT/Restrictor']:
                self.plot['Modded'] = y*((x0-x)/x0)**p
                self.plot['Scale']  = ((x0-x)/x0)**p

            else:
                self.plot['Modded'] = y
                self.plot['Scale'] = 0 * x + 1

        self.plot.plot()

    def expand_tree(self):
        """
        Expands / collapses based on check boxes
        """
        print('expand_tree')

        self._expanding_tree = True
        
        self.tree.set_expanded('POWER.LUT', self.tree['POWER.LUT'])
        for file in self.ini:

            # Expand top level
            if file in self.tree.keys():
                self.tree.set_expanded(file, self.tree[file])

            # Expand sections
            for section in self.ini_files[file]:
                s = file+'/'+section
                self.tree.set_expanded(s, self.tree[s])
            
            # Expand added sections
            for section in self.ini[file]:
                s = file+'/'+section
                self.tree.set_expanded(s, self.tree[s])

        self.window.process_events()
        self._expanding_tree = False


    def _tree_changed(self, *a):
        """
        Setting in the tree changed.
        """
        if self._loading_car_data \
        or self._expanding_tree   \
        or self._tree_changing    \
        or self._init_running: return
        print('_tree_changed')

        # Update the plot curves
        self.update_curves()

        # Automatically expand based on checkboxes
        self.expand_tree()

        # Change colors
        self.highlight_changed()

        # Save the tree
        car = self.combo_car.get_text()
        saved_tree_path = os.path.join(self.text_local(), 'content', 'cars', car, 'ui', 'jax-minimodder.txt')
        self.tree.save(saved_tree_path)

    def _button_scan_clicked(self, *a):
        """
        Scans the content directory for things to mod.
        """
        self.update_cars()

    def _button_browse_local_clicked(self, *a):
        """
        Pop up the directory selector.
        """
        path = egg.dialogs.select_directory(text='Select the Assetto Corsa directory, apex-nerd.', default_directory='assetto_local')
        if path:
            self.text_local(path)
            self.button_scan.click()

    def log(self, *a):
        """
        Logs it.
        """
        a = list(a)
        for n in range(len(a)): a[n] = str(a[n])
        text = ' '.join(a)
        self.text_log.append_text(text)
        print('LOG:', text)
        self.window.process_events()

    def update_cars(self):
        """
        Searches through the current assetto directory for all cars, skins, etc.
        """
        self.log('Updating cars...')
        self._updating_cars = True

        # Dictionary to hold all the model names
        self.cars  = dict()
        self.srac  = dict() # Reverse-lookup
        self.skins = dict()

        # Get all the car paths
        for path in glob.glob(os.path.join(self.text_local(), 'content', 'cars', '*')):

            # Get the car's directory name
            dirname = os.path.split(path)[-1]

            # Make sure it exists.
            path_json = os.path.join(path, 'ui', 'ui_car.json')
            if not os.path.exists(path_json): continue

            # Get the fancy car name (the jsons are not always well formatted, so I have to manually search!)
            s = load_json(path_json)

            # Remember the fancy name
            name = s['name'] if 'name' in s else dirname
            self.cars[dirname] = name
            self.srac[name]    = dirname

            # Store the list of skins and the index
            self.skins[dirname] = os.listdir(os.path.join(path, 'skins'))

        # Sort the car directories and add them to the list.
        self.cars_keys = list(self.cars.keys())
        self.srac_keys = list(self.srac.keys())
        self.cars_keys.sort()
        self.srac_keys.sort()

        # Populate the combo
        self.combo_car.clear()
        for key in self.cars_keys: self.combo_car.add_item(key)

        self._updating_cars = False


# Start the show!
self = Modder()
