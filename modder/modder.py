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

from numpy import interp, linspace, isnan, unravel_index
from scipy.signal import savgol_filter

# Change to the directory of this script depending on whether this is a "compiled" version or run as script
if os.path.split(sys.executable)[-1] == 'uploader.exe': os.chdir(os.path.dirname(sys.executable)) # For executable version
else:                                                   os.chdir(os.path.dirname(os.path.abspath(__file__)))
print('WORKING DIRECTORY:')
print(os.getcwd())

exceptions = egg.gui.TimerExceptions()
exceptions.start()

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
    def rm_readonly(func, path, *a):
        #if len(a): print('rm_readonly:', a)
        os.chmod(path, stat.S_IWRITE)
        func(path)
        
    shutil.rmtree(top, onerror=rm_readonly)

def nearest_fraction(x, nmin=7, nmax=40):
    """
    Given x, find the closest fraction
    """
    
    # Generate all fractions
    num, den = spinmob.fun.generate_xy_grid(nmin, nmax, nmax-nmin+1, nmin, nmax, nmax-nmin+1)
    
    # Find the closest
    n,m = unravel_index(((x-num/den)**2).argmin(), num.shape)
    
    return num[n,m], den[n,m]


# noinspection PyProtectedMember
class Modder:
    """
    GUI class for searching and modding content.
    """

    def __init__(self, blocking=False):

        # JACK: WHEN DOES _BUTTON_SCAN HAPPEN AND WHEN IS THE COMBO BOX VALUE SET?
        print('\nINIT')
        # When updating cars, we want to suppress some signals.
        self._init_running = True
        self._updating_cars = False
        self._loading_car_data = False
        self._expanding_tree = False
        self._tree_changing = False
        self._creating_mod = False

        # Other variables
        self.source_power_lut = None # Used to hold the source power.lut data.
        self.cars = dict()  # Car folder keys, car name values
        self.srac = dict()  # Reverse-lookup
        self.skins = dict()
        self.cars_keys = None
        self.srac_keys = None

        # Lookup table for which files to mod, with extra sections possible
        self.ini_seed = {
            'AERO.INI'          : {},
            'CAR.INI'           : {'RULES': {'MIN_HEIGHT': '0.000'}},
            'DRIVETRAIN.INI'    : {},
            'ENGINE.INI'        : {},
            'SETUP.INI'         : {
                'FINAL_GEAR_RATIO': {
                    'RATIOS' : 'final.rto',
                    'NAME'   : 'Final Gear Ratio',
                    'POS_X'  : '1',
                    'POS_Y'  : '8',
                    'HELP'   : 'HELP_REAR_GEAR'
                }
            },
            'SUSPENSIONS.INI'   : {},
            'TYRES.INI'         : {},
        }

        # This will hold all the data from the ini files.
        self.ini_source = dict()
        

        ######################
        # Build the GUI

        print('\nBUILDING GUI')

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
        
        # JACK: Not sure why I had to put this here. Legacy?
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

        self.button_hide_unchanged = self.grid_middle.add(egg.gui.CheckBox('Hide Unchanged', 
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
        print('\nPOPULATING TREE:')
        
        self.tree.add('Mod Tag', 'R')

        self.tree.add('POWER.LUT', ['leave', 'modify'])
        self.set_tree_item_style_header('POWER.LUT')
        
        self.tree.add('POWER.LUT/Restrictor', False)
        self.tree.add('POWER.LUT/Restrictor/Exponent', 0.3, step=0.05)
        self.tree.add('POWER.LUT/Restrictor/RPM Range', 1.0, step=0.05, bounds=(0,None))
        self.tree.add('POWER.LUT/Smooth', False)
        self.tree.add('POWER.LUT/Smooth/Points', 100)
        self.tree.add('POWER.LUT/Smooth/Window', 5)
        self.tree.add('POWER.LUT/Smooth/Order', 3)
        
        self.tree.add('RATIOS.RTO', ['leave', 'modify'])
        self.set_tree_item_style_header('RATIOS.RTO')

        self.tree.add('RATIOS.RTO/Start', 2.64, bounds=(0,None))
        self.tree.add('RATIOS.RTO/Stop',  0.88, bounds=(0,None))
        self.tree.add('RATIOS.RTO/Steps', 24)
        self.tree.add('RATIOS.RTO/Min',   7)
        self.tree.add('RATIOS.RTO/Max',  37)
        self.tree.add_button('RATIOS.RTO/Preview', tip='Generate and send the output to the log', signal_clicked=self._button_test_ratios_clicked)
        
        self.tree.add('FINAL.RTO', ['leave', 'modify'])
        self.set_tree_item_style_header('FINAL.RTO')

        self.tree.add('FINAL.RTO/Start', 4, bounds=(0,None))
        self.tree.add('FINAL.RTO/Stop',  2, bounds=(0,None))
        self.tree.add('FINAL.RTO/Steps', 24)
        self.tree.add('FINAL.RTO/Min',   7)
        self.tree.add('FINAL.RTO/Max',   42)
        self.tree.add_button('FINAL.RTO/Preview', tip='Generate and send the output to the log', signal_clicked=self._button_test_final_clicked)
        
        
        # Populate those specified outside the file itself        
        for file in self.ini_seed:
            self.tree.add(file, ['leave', 'modify'])
            self.set_tree_item_style_header(file)
            
            for section in self.ini_seed[file]:
                self.tree.add(file+'/'+section, ['leave', 'modify', 'remove'])
                for key in self.ini_seed[file][section]:
                    self.tree.add(file+'/'+section+'/'+key, self.ini_seed[file][section][key], tip='(manually created)')

        print('\nMAKING PLOTTER')
        # Make the plotter
        self.plot = self.grid_middle2.add(egg.gui.DataboxPlot(autosettings_path='plot'), alignment=0)

        # Log area
        self.window.new_autorow()
        self.text_log = self.grid_middle2.add(egg.gui.TextLog(), 1,1, alignment=0)

        self.log('Welcome to my silly-ass minimodder!')

        # Scan for content
        print('\nSCANNING')
        self.button_scan.click()

        print('\nSETTING LAST CAR INDEX')
        self._init_running = False

        # Now set the last index and let it update
        self.combo_car.set_index(last_car_index)

        # Last pretty steps.
        print('\nHIDING / HIGHLIGHTING')
        self.hide_unchanged()
        self.highlight_changed()

        # Show it.
        print('\nSHOWING')
        self.window.show(blocking)

    def _button_test_ratios_clicked(self, *a):
        """
        Generates ratio file contents for the log.
        """
        self.generate_rto('RATIOS.RTO', test=True)

    def _button_test_final_clicked(self, *a):
        """
        Generates final.rto for log.
        """
        self.generate_rto('FINAL.RTO', test=True)

    def generate_rto(self, file='RATIOS.RTO', test=False):
        """
        Generates the ratio selection.
        """
    
        if not self.tree[file]: return
        
        # Get the range of targeted ratio floats
        #rs = spinmob.fun.erange(self.tree[file+'/Start'], self.tree[file+'/Stop'], self.tree[file+'/Steps'])
        rs = linspace(self.tree[file+'/Start'], self.tree[file+'/Stop'], self.tree[file+'/Steps'])

        # Get the nearest fraction for each
        s = ''
        for r in rs:
            n,d = nearest_fraction(r, self.tree[file+'/Min'], self.tree[file+'/Max'])
            s = s+'%i//%i|%0.3f\n' % (d, n, n/d)

        # Write the file or show it.
        if not test:
            with open(self.get_mod_path('data',file.lower()), 'w') as f:
                self.log('  Creating new '+file)
                f.write(s)
        else:  self.log('\n'+file+'\n', s)
                
                

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
        for file in self.ini_source: 
            self.tree[file] = False
            for section in self.ini_source[file]: self.tree[file+'/'+section] = False
            for section in self.ini_seed[file]:   self.tree[file+'/'+section] = False
            
        self._tree_changing = False

        # Reload the car
        self.load_car_data()

    def get_mod_path(self, *args):
        """
        Returns the path to the mod car.
        
        args can be additional paths, e.g. 'data'.
        """
        mod_car  = self.combo_car.get_text()+'_'+self.tree['Mod Tag'].lower().replace(' ', '_')
        return os.path.realpath(os.path.join(self.text_local(), 'content', 'cars', mod_car, *args))
    

    def _button_create_mod_clicked(self, *a): self.create_mod()
    def create_mod(self):
        """
        Duplicates the currently selected car and creates a modded version.
        """
        self._creating_mod = True

        # Source car 
        car      = self.combo_car.get_text()
        car_name = self.cars[car]
        car_path = os.path.realpath(os.path.join(self.text_local(), 'content', 'cars', car))
        
        # Mod name, folder, and path
        mod_name = car_name + '-'+self.tree['Mod Tag']
        mod_car  = car+'_'+self.tree['Mod Tag'].lower().replace(' ', '_')
        mod_car_path = os.path.realpath(os.path.join(self.text_local(), 'content', 'cars', mod_car))

        # Create a warning dialog and quit if cancelled
        qmb = egg.pyqtgraph.QtWidgets.QMessageBox
        ret = qmb.question(self.window._window, '******* WARNING *******',
          "This will create the mod '"+mod_name+"' and create / overwrite the folder "+mod_car_path,
          qmb.Ok | qmb.Cancel, qmb.Cancel)
        if ret == qmb.Cancel: return

        self.log('Creating '+mod_name)

        # If the other directory is already there, kill it.
        if os.path.exists(mod_car_path):
            self.log('  Deleting '+mod_car_path)
            try: rmtree(mod_car_path)
            except Exception as e:
                self.log('  Error:', e)
                return 

        # Copy the existing mod as is
        self.log('  Copying '+car+' -> '+mod_car)
        shutil.copytree(car_path, mod_car_path)

        # POWER.LUT
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

        # UI.JSON
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

        # RATIOS AND FINAL RTO
        self.generate_rto('RATIOS.RTO')
        self.generate_rto('FINAL.RTO')

        ##################
        # INI FILES
        ##################
        
        ini_modded = dict(self.ini_source)

        # Loop over all the tree keys, e.g. SETUP.INI/SPRING_RATE_LF/NAME
        for k in self.tree.keys():

            # k is something like SETUP.INI/SPRING_RATE_LF/NAME
            s = k.split('/') # ['SETUP.INI', 'SPRING_RATE_LF', 'NAME']
            file = s[0]      # 'SETUP.INI'
            
            # If it's an ini file (not another category) 
            # and we have it set to be changed, modify it
            if file in self.ini_seed and self.tree[file] == 'modify':
                                    
                # Only proceed if there is a section
                if len(s) <= 1: continue
                
                # Section
                section = s[1] # e.g. 'SPRING_RATE_LF'

                # We will populated this with the modded values from the tree
                c = ini_modded[file]

                # If we're supposed to modify the section and there is a key
                if self.tree[file + '/' + section] == 'modify' and len(s) > 2:

                    # If there is not already a section in the tree, add it
                    if not section in c: c[section] = dict()
                                    
                    # Update the key to the tree value
                    c[section][s[2]] = self.tree[k]
                
                # If we're supposed to remove it, pop it from the dictionary
                # so it's not written
                elif self.tree[file + '/' + section] == 'remove' and len(s) == 2: 
                    print('  popping', file, section)
                    c.pop(section)
            
        # Write the files
        for file in ini_modded:
            if self.tree[file] == 'modify':
                self.write_ini_file(ini_modded[file], mod_car_path, 'data', file.lower())

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

        # All done
        self._creating_mod = False
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
        if self._updating_cars \
        or self._init_running  \
        or self._creating_mod: return
        self.log('New car selected.')
        self.load_car_data()

    def _button_load_car_clicked(self, *a):
        """
        Someone clicked the "Load Car Data" button.
        """
        self.load_car_data()

    def read_ini_file(self, *paths):
        """
        My own parser because dammit the other one is annoying af and doesn't like to play nice.
        """
        path = os.path.join(*paths)
        with open(path, 'r') as f:

            # Get the lines
            lines = f.readlines()

            # Organization: section, key, value
            c = dict()
            section = ''

            # Loop over lines
            for line in lines:

                # Strip the comment
                line = line.split(';')[0].strip()

                # If it's empty or just a comment
                if line == '': continue

                # If it's a new section
                if line[0] == '[':
                    section = line[1:len(line)-1]
                    continue
            
                # If it's a key-value pair
                s = line.split('=')
                if len(s) < 2: continue

                # Create the section in the output dictionary
                if not section in c: c[section] = dict()

                # Store the key and value (string)
                c[section][s[0].strip()] = s[1].strip()
            
        return c

    def write_ini_file(self, c, *paths):
        """
        Writes the dictionary 'c' to the ini file format specified by paths
        """
        path = os.path.join(*paths)
        self.log('  Overwriting', paths[-1])
        with open(path,'w') as f: 
            for section in c:

                # Write the section header
                f.write('\n['+section+']\n')

                # Loop over sub-keys
                for key in c[section]: f.write(key+'='+c[section][key]+'\n')


    # def reload_ini_files(self):
    #     """
    #     Resets self.ini_source to the defaults.
    #     """
    #     # Get the path to the car
    #     car  = self.combo_car.get_text()
    #     data = os.path.realpath(os.path.join(self.text_local(), 'content', 'cars', car, 'data'))
        
    #     if not os.path.exists(data):
    #         self.log('ERROR: Data folder not present. Make sure you unpack data.acd.')
    #         return
        
    #     # Load default settings from the ini files themselves
    #     for file in self.ini_seed:
    #         print('  Reloading', file)
    #         self.ini_source[file] = self.read_ini_file(data, file.lower())

    def load_car_data(self):
        """
        Loads the car data.
        """
        # Prevent tree events etc
        self._loading_car_data = True

        # Get the path to the car
        car  = self.combo_car.get_text()
        data = os.path.realpath(os.path.join(self.text_local(), 'content', 'cars', car, 'data'))

        # Make sure we have the file
        self.log('Loading '+car+' data:')
        if not os.path.exists(data):
            self.log('  ERROR: '+ data + ' does not exist. Make sure you have unpacked data.acd.')
            self.button_create_mod.disable()
            self.plot.clear()
            self.plot.plot()
            self.grid_middle2.disable()
            return

        # We have it, so we can do everything. Enable stuff.
        self.button_create_mod.enable()
        self.grid_middle2.enable()

        # load power.lut, stick it in an "original" databox, copy to plot, and run the plot
        power_lut = os.path.join(data, 'power.lut')
        self.source_power_lut = spinmob.data.load(power_lut, delimiter='|')

        # Load DEFAULT settings from the ini files themselves
        for file in self.ini_seed:
            self.log('  Loading', file)
            
            # Start clean
            c = self.read_ini_file(data, file.lower())
            self.ini_source[file] = dict(c) # make a copy we will not change
            
            # loop over the keys
            for section in c:

                # Add section
                s = file + '/' + section
                if s not in self.tree.keys(): self.tree.add(s, ['leave', 'modify', 'remove'])
                    
                # Add keys
                for key in c[section]:
                    k = s+'/'+key
                    
                    # Create or update the item
                    if k not in self.tree.keys():
                        x = self.get_ini_source_value(file, section, key)
                        self.tree.add(k, x, tip='Original: '+str(x))
                    else: 
                        self.tree[k] = self.get_ini_source_value(file, section, key)

        # Load USER settings from the saved json
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
        
        return True

    def get_ini_source_value(self, file, section, key):
        """
        Returns the value string from self.ini_source if it's there, or self.ini_source if not.
        """
        if file  in self.ini_source         and \
           section in self.ini_source[file] and \
           key     in self.ini_source[file][section]:
               return str(self.ini_source[file][section][key].split(';')[0].strip())
        
        return None

    def set_tree_item_highlighted(self, key, highlighted=False):
        """
        Sets whether the item is highlighted.
        """
        if len(key.split('/')) < 3: print(key, highlighted)

        # Get the widget
        w = self.tree.get_widget(key) 
        
        # Set whether highlighted
        if highlighted: color = egg.pyqtgraph.QtGui.QColor(255,200,200)
        else:           color = w.background(0)
        w.setBackground(1, color)

            
    def get_changed_tree_keys(self):
        """
        Loops over the tree keys and returns a list of those changed from the
        car values.
        """
        print('get_changed_tree_keys')
        
        # Loop over all keys in the tree
        changed_keys = [] # Just a list to return at the end
        for tk in self.tree.keys():
            s = tk.split('/') # [file, section, key]
            
            # If we're length 1, it's a file
            if len(s) == 1: 
                if self.tree[tk] in ['modify']: changed_keys.append(tk)
            
            # If we're length 2 it s file/section
            elif len(s) == 2:
                if self.tree[tk] in ['modify', 'remove']: changed_keys.append(tk)
            
            # If we're length 3, that means we have file/section/key
            else:
                file, section, key = s
                
                # We don't highlight things that aren't regular ini files
                if file not in self.ini_source: continue

                # If the section is not in the source data 
                # or the value is different from the source data, append
                if section not in self.ini_source[file] \
                or self.tree[tk] != self.get_ini_source_value(file, section, key):  
                    changed_keys.append(tk)
                
        return changed_keys
            

    def highlight_changed(self):
        """
        Highlights the changed items.
        """        
        print('\nHighlighting changed items...')
        self.window.block_signals()

        changed = self.get_changed_tree_keys()
        for tk in self.tree.keys():
            tks = tk.split('/')
            self.set_tree_item_highlighted(tk, tk in changed)
        
        self.window.unblock_signals()
                    
        

    def hide_unchanged(self):
        """
        Loops through the ini list and hides everything that has not been changed.
        """
        print('hide_unchanged')
        
        # Toggle
        unhide = not self.button_hide_unchanged()
        
        # Reload car data to original values
        #self.reload_ini_files()
        
        # Try to freeze the system so it doesn't generate signals
        self.window.block_signals()

        # Loop over all the tree keys
        for tk in self.tree.keys():
            s = tk.split('/')

            # If we have one element, it's a file
            if len(s) == 1:
                if tk == 'Mod Tag': continue 
                
                # If the file is not to be modified, hide
                if self.tree[tk] == 'leave': self.tree.hide_parameter(tk, unhide)
            
            # If we have two, it's a file/section situation
            elif len(s) == 2:
                if self.tree[tk] == 'leave': self.tree.hide_parameter(tk, unhide)
            
            # If it's 3, we have file/section/parameter and need to see if it's different
            elif len(s) == 3:
                if self.tree[tk] == self.get_ini_source_value(*s): self.tree.hide_parameter(tk, unhide)

        self.window.unblock_signals()

        # # Load default settings from the ini files themselves
        # for file in self.ini_source:
        #     c = self.ini_source[file]
            
        #     # loop over the keys
        #     for section in c:
        #         ts = file + '/' + section
                
        #         # Hide the section if it's unchecked
        #         if ts in self.tree.keys(): 
        #             self.tree.hide_parameter(ts, self.tree[ts] or unhide)
                
        #             # Hide keys that have the same values.
        #             for key in c[section]:
        #                 tk = file + '/' + section + '/' + key
        #                 self.tree.hide_parameter(tk, self.tree[tk] != self.get_ini_source_value(file, section, key) or unhide)

        #     # loop over the extras
        #     for section in self.ini_seed[file]:
        #         ts = file + '/' + section
        #         self.tree.hide_parameter(ts, self.tree[ts] or unhide)
                


    def update_curves(self):
        """
        Calculates and updates the plot.
        """
        if not self.source_power_lut or not len(self.source_power_lut): return

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
        
        self.tree.set_expanded('POWER.LUT',  self.tree['POWER.LUT']=='modify')
        self.tree.set_expanded('RATIOS.RTO', self.tree['RATIOS.RTO']=='modify')
        self.tree.set_expanded('FINAL.RTO',  self.tree['FINAL.RTO']=='modify')
        
        for file in self.ini_seed:

            # Expand top level
            if file in self.tree.keys():
                self.tree.set_expanded(file, self.tree[file]=='modify')

            # Expand sections
            for section in self.ini_source[file]:
                s = file+'/'+section
                if s in self.tree.keys(): self.tree.set_expanded(s, self.tree[s]=='modify')
            
            # Expand added sections
            for section in self.ini_seed[file]:
                s = file+'/'+section
                if s in self.tree.keys(): self.tree.set_expanded(s, self.tree[s]=='modify')

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

        # Get the current car name
        og_name = self.combo_car.get_text()

        # Get all the car paths
        for path in glob.glob(os.path.join(self.text_local(), 'content', 'cars', '*')):

            # Get the car's directory name
            dirname = os.path.split(path)[-1]

            # Make sure it exists.
            path_json = os.path.join(path, 'ui', 'ui_car.json')
            path_data = os.path.join(path, 'data')
            if not os.path.exists(path_json) or not os.path.exists(path_data): continue

            # Get the fancy car name (the jsons are not always well formatted, so I have to manually search!)
            s = load_json(path_json)

            # Remember the fancy name
            name = s['name'] if 'name' in s else dirname
            print('  ', name)
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

        # Set it to what it was.
        if og_name in self.cars_keys: self.combo_car.set_text(og_name)

        self._updating_cars = False

        self._combo_car_changed()


# Start the show!
self = Modder()
