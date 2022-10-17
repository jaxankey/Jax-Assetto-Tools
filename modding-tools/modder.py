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

from numpy import interp, linspace, isnan
from scipy.signal import savgol_filter

# Change to the directory of this script depending on whether this is a "compiled" version or run as script
if os.path.split(sys.executable)[-1] == 'uploader.exe': os.chdir(os.path.dirname(sys.executable)) # For executable version
else:                                                   os.chdir(os.path.dirname(os.path.abspath(__file__)))
print('WORKING DIRECTORY:')
print(os.getcwd())



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

def rm_readonly(func, path):
    os.chmod(path, stat.S_IWRITE)
    func(path)

def rmtree(top):
    """
    Implemented to take care of chmod
    """
    shutil.rmtree(top, onerror=rm_readonly)


# noinspection PyProtectedMember
class Modder:
    """
    GUI class for searching and modding content.
    """

    def __init__(self, blocking=True):

        # When updating cars, we want to suppress some signals.
        self._updating_cars = False
        self._loading_car_data = False
        self._tree_changing = False

        # Other variables
        self.source_power_lut = None # Used to hold the source power.lut data.
        self.cars = dict()  # Car folder keys, car name values
        self.srac = dict()  # Reverse-lookup
        self.skins = dict()
        self.cars_keys = None
        self.srac_keys = None

        # Lookup table to convert from user-friendly settings to keys in ini files.
        self.ini = {
            'CAR.INI'           : {
                'Mass'              : 'BASIC/TOTALMASS',
            },
            'DRIVETRAIN.INI'        : {
                'Power'             : 'DIFFERENTIAL/POWER',
                'Coast'             : 'DIFFERENTIAL/COAST',
                'Preload'           : 'DIFFERENTIAL/PRELOAD',
            },
            'SUSPENSIONS.INI'   : {
                'Front/Height'      : 'FRONT/ROD_LENGTH',
                'Front/Travel'      : 'FRONT/PACKER_RANGE',
                'Front/Bump'        : 'FRONT/DAMP_BUMP',
                'Front/Rebound'     : 'FRONT/DAMP_REBOUND',
                'Front/Fast Bump'   : 'FRONT/DAMP_FAST_BUMP',
                'Front/Fast Rebound': 'FRONT/DAMP_FAST_REBOUND',

                'Rear/Height'       : 'REAR/ROD_LENGTH',
                'Rear/Travel'       : 'REAR/PACKER_RANGE',
                'Rear/Bump'         :  'REAR/DAMP_BUMP',
                'Rear/Rebound'      : 'REAR/DAMP_REBOUND',
                'Rear/Fast Bump'    : 'REAR/DAMP_FAST_BUMP',
                'Rear/Fast Rebound' : 'REAR/DAMP_FAST_REBOUND',
            },
        }
        

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
        
        # Settings and plot row
        self.window.new_autorow()
        self.grid_middle2 = self.window.add(egg.gui.GridLayout(False), alignment=0)
        self.tree = self.grid_middle2.add(egg.gui.TreeDictionary(
            autosettings_path='tree', new_parameter_signal_changed=self._tree_changed),
            row_span=2)
        self.tree.set_minimum_width(210)

        # Settings
        self.tree.add('Mod Tag', 'R')
        
        self.tree.add('POWER.LUT', False)
        self.tree.add('POWER.LUT/Restrictor', False)
        self.tree.add('POWER.LUT/Restrictor/Exponent', 0.3, step=0.05)
        self.tree.add('POWER.LUT/Restrictor/RPM Range', 1.0, step=0.05, limits=(0,None))
        self.tree.add('POWER.LUT/Smooth', False)
        self.tree.add('POWER.LUT/Smooth/Points', 100)
        self.tree.add('POWER.LUT/Smooth/Window', 5)
        self.tree.add('POWER.LUT/Smooth/Order', 3)

        self.button_reset_inis = self.tree.add_button('Reset INI\'s')
        self.button_reset_inis.signal_clicked.connect(self._button_reset_inis_clicked)

        for key in self.ini:
            self.tree.add(key, False)
            for k in self.ini[key]:
                self.tree.add(key+'/'+k, 0.0, format='{value:.6g}')
                self.tree.add(key+'/'+k+'/->', 0.0, format='{value:.6g}')
                
        self.tree.load_gui_settings()
        
        # Make the plotter
        self.plot = self.grid_middle2.add(egg.gui.DataboxPlot(autosettings_path='plot'), alignment=0)        
        
        # Log area
        self.window.new_autorow()
        self.text_log = self.grid_middle2.add(egg.gui.TextLog(), 1,1, alignment=0)
        
        self.log('Welcome to my silly-ass minimodder!')
        
        # Scan for content
        self.button_scan.click()
        self.combo_car.set_index(last_car_index)
        
        # Show it.
        self.window.show(blocking)

    def _button_reset_inis_clicked(self, *a):
        """
        Clears out the jax-minimodder file and reloads the car.
        """
        path = os.path.join(self.text_local(), 'content', 'cars', self.srac[self.combo_car.get_text()], 'ui', 'jax-minimodder.txt')

        # delete the config file
        if os.path.exists(path):
            self.log('Deleting ui/jax-minimodder.txt')
            os.unlink(path)

        # Uncheck them all
        self._tree_changing = True
        for file in self.ini: self.tree[file] = False
        self._tree_changing = False

        # Reload the car
        self.load_car_data()

    def _button_create_mod_clicked(self, *a):
        """
        Duplicates the currently selected car and creates a modded version.
        """
        
        # Get the mod name and new folder name
        car_name = self.combo_car.get_text()
        car = self.srac[car_name]
        car_path = os.path.realpath(os.path.join(self.text_local(), 'content', 'cars', car))
        mod_name = self.combo_car.get_text() + '-'+self.tree['Mod Tag']
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
            mod_power_path = os.path.realpath(os.path.join(mod_car_path,'data','power.lut'))
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
        x['specs']['weight']   = '%.0f kg'  % self.tree['CAR.INI/Mass/->']
        x['specs']['pwratio']  = '%.2f kg/bhp' % (self.tree['CAR.INI/Mass/->']/max(hp))
        x['specs']['topspeed'] = 'buh?'
        x['minimodder'] = self.tree.get_dictionary()[1]
        json.dump(x, open(mod_ui, 'w'), indent=2)

        # JACK: CAR.INI NAMES

        ##################
        # INI FILES
        ##################
        for file in self.ini:
        
            # if we're supposed to mess with this file    
            if not self.tree[file]: continue
            self.log('  Updating '+file)
            
            # Read the existing ini file
            mod_ini_path = os.path.join(mod_car_path,'data',file.lower())
            with open(mod_ini_path) as f: ls = f.readlines()
            
            # Loop over lines, keeping track of the section
            section = ''
            for n in range(len(ls)):
     
                # Check if this is a section header
                if ls[n][0] == '[': 
                    section = ls[n][1:].split(']')[0].strip()

                # Otherwise, do the key-value thing
                else:
                    b = ls[n].split('=')[0].strip()
                    ab = section+'/'+b
                    for k in self.ini[file]:
                        if ab == self.ini[file][k]:
                            ls[n] = b+'='+str(self.tree[file+'/'+k+'/->'])+'\n'
                            self.log('     '+b+'='+str(self.tree[file+'/'+k+'/->']))

            # Overwrite the ini file
            with open(mod_ini_path, 'w') as f: f.writelines(ls)
        
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
        self.log('Renaming '+car+'.bank -> '+mod_car+'.bank')
        os.rename(os.path.join(mod_car_path, 'sfx', car     + '.bank'),
                  os.path.join(mod_car_path, 'sfx', mod_car + '.bank'))
        
        # Remember our selection and scan
        self.button_scan.click()
        self.combo_car.set_index(self.combo_car.get_index(car_name))
        
        # Open the mod car path
        os.startfile(mod_car_path)
    
    def load_ini(self, *path_args):
        """
        Returns dictionary for the specified file.
        """
        path = os.path.join(*path_args)
        self.log('  Loading '+path)

        # ConfigParser is a bug-ass piece of shit.
        # Assemble a dictionary.
        c = dict()
        with open(path) as f: ls = f.readlines()
        section = None
        for l in ls:
            if l[0] == '[':
                section = l[1:].split(']')[0].strip()
                c[section] = dict()
            elif section:
                s = l.split('=')
                if len(s) > 1:
                    key   = s[0].strip()
                    value = s[1].split(';')[0].strip()
                    c[section][key] = value
        return c

    def _button_open_car_folder_clicked(self, *a):
        """
        Opens the car directory.
        """
        car  = self.srac[self.combo_car.get_text()]
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
    
    def load_car_data(self):
        """
        Loads the car data.
        """
        # Prevent tree events etc
        self._loading_car_data = True

        # Get the path to the car
        car  = self.srac[self.combo_car.get_text()]
        data = os.path.realpath(os.path.join(self.text_local(), 'content', 'cars', car, 'data'))

        self.log('Loading '+self.combo_car.get_text()+' data:')
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

        # If we have already saved a tree for this car, load it
        saved_tree = None
        saved_tree_path = os.path.join(self.text_local(), 'content', 'cars', car, 'ui', 'jax-minimodder.txt')
        if os.path.exists(saved_tree_path):
            self.log('  Loading ', saved_tree_path)
            saved_tree = spinmob.data.load(saved_tree_path, header_only=True, delimiter='\t')
            self.tree.update(saved_tree) # No event fired because we're loading car data.

        # Load other ini settings into the tree
        for file in self.ini:

            # Load the existing data
            c = self.load_ini(data, file.lower())

            # loop over the "user friendly" keys of interest
            for nice_key in self.ini[file]:

                # Get the ini file section and key
                section,key = self.ini[file][nice_key].split('/')
                value = c[section][key]

                # update the tree 'start' value
                tree_key = file+'/'+nice_key
                self.tree[tree_key] = value

                # If we didn't already load the saved_tree, set a default for the 'to'
                if saved_tree is None: self.tree[tree_key + '/->'] = value

        # Re-enable tree events
        self._loading_car_data = False

        # Expand
        self.expand_tree()
        self.update_curves()

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
        self._tree_changing = True
        self.tree.set_expanded('POWER.LUT', self.tree['POWER.LUT'])
        for file in self.ini:
            if file in self.tree.keys(): self.tree.set_expanded(file, self.tree[file])
        self._tree_changing = False

    def _tree_changed(self, *a):
        """
        Setting in the tree changed.
        """
        if self._loading_car_data or self._tree_changing: return

        print('_tree_changed')
        self.update_curves()

        self.expand_tree()

        # Save the tree
        car = self.srac[self.combo_car.get_text()]
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
        for key in self.srac_keys: self.combo_car.add_item(key)

        self._updating_cars = False


# Start the show!
self = Modder()
