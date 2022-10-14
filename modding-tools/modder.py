#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import glob, codecs, os, sys, shutil, random, json, pyperclip, webbrowser, stat
import dateutil, subprocess, time, datetime, importlib, codecs
import configparser, spinmob
from scipy.signal import savgol_filter
from numpy import interp, linspace


# Change to the directory of this script depending on whether this is a "compiled" version or run as script
if os.path.split(sys.executable)[-1] == 'uploader.exe': os.chdir(os.path.dirname(sys.executable)) # For executable version
else:                                                   os.chdir(os.path.dirname(os.path.abspath(__file__)))
print('WORKING DIRECTORY:')
print(os.getcwd())

import spinmob.egg as egg

# Function for loading a json at the specified path
def load_json(path):
    """
    Load the supplied path with all the safety measures and encoding etc.
    """
    try:
        if os.path.exists(path):
            f = codecs.open(path, 'r', 'utf-8-sig', errors='replace')
            #f = open(path, 'r', encoding='utf8', errors='replace')
            j = json.load(f, strict=False)
            f.close()
            return j
    except Exception as e:
        print('ERROR: Could not load', path)
        print(e)

def rm_readonly(func, path, excinfo):
    os.chmod(path, stat.S_IWRITE)
    func(path)

def rmtree(top):
    """
    Implemented to take care of chmodding
    """
    shutil.rmtree(top, onerror=rm_readonly)

class Modder:
    """
    GUI class for searching and modding content.
    """

    def __init__(self, show=True, blocking=True):

        # When updating cars, we want to suppress some signals.
        self._updating_cars = False
        

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
            autosettings_path='tree', new_parameter_signal_changed=self._tree_changed))
        self.tree.set_minimum_width(210)

        # Settings
        self.tree.add('Mod Tag', 'R')
        self.tree.add('Restrictor Curve/Exponent', 0.3, step=0.05)
        self.tree.add('Restrictor Curve/RPM Range', 1.0, step=0.05, limits=(0,None))
        self.tree.add('Ballast', 0.0, step=10)
        self.tree.add('Smooth', False)
        self.tree.add('Smooth/Points', 100)
        self.tree.add('Smooth/Window', 5)
        self.tree.add('Smooth/Order', 3)
        
        self.tree.load_gui_settings()
        
        self.plot = self.grid_middle2.add(egg.gui.DataboxPlot(autosettings_path='plot'), alignment=0)        
        
        
        self.window.new_autorow()
        self.grid_bottom = self.window.add(egg.gui.GridLayout(False), alignment=0)  
        self.text_log = self.grid_bottom.add(egg.gui.TextLog(), alignment=0)
        
        self.log('Welcome to my silly-ass minimodder! I just use this to balance carsets, so don\'t @ me!')
        
        # Scan for content
        self.button_scan.click()
        self.combo_car.set_index(last_car_index)
        
        # Show it.
        self.window.show(blocking)

    def _button_create_mod_clicked(self, *a):
        """
        Duplicates the currently selected car and creates a modded version.
        """
        
        # Get the mod name and new folder name
        car_name = self.combo_car.get_text()
        car = self.srac[car_name]
        car_path = os.path.realpath(os.path.join(self.text_local(), 'content', 'cars', car))
        mod_name = self.combo_car.get_text() + ' ('+self.tree['Mod Tag']+')'
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
        mod_power_path = os.path.realpath(os.path.join(mod_car_path,'data','power.lut'))
        self.log('  Writing '+mod_power_path)
        f = open(mod_power_path, 'w')
        for n in range(len(d[0])): 
            line = '%.1f|%.1f\n' % (d[0][n], d[2][n])
            f.write(line)
        f.close()
        
        # Now update ballast etc
        self.log('  Updating car.ini to include ballast')
        c = configparser.ConfigParser()
        mod_car_ini = os.path.join(mod_car_path, 'data', 'car.ini')
        c.read(mod_car_ini)
        mod_mass = float(c['BASIC']['TOTALMASS']) + self.tree['Ballast']
        c['BASIC']['TOTALMASS'] = '%.0f' % mod_mass
        c.write(open(mod_car_ini, 'w'))
        
        
        # Now update the ui.json
        self.log('  Updating ui_car.json')
        ui     = os.path.realpath(os.path.join(car_path,     'ui', 'ui_car.json'))
        mod_ui = os.path.realpath(os.path.join(mod_car_path, 'ui', 'ui_car.json'))
        x = load_json(ui)
        
        # Name
        x['name'] = mod_name
        
        # Torque and Power curves
        x['torqueCurve'] = []
        x['powerCurve']  = []
        hp = d[0]*d[2]*0.00014
        for n in range(len(d[0])):
            x['torqueCurve'].append(['%.1f'%d[0][n], '%.1f'%d[2][n]])
            x['powerCurve'] .append(['%.1f'%d[0][n], '%.1f'%hp[n]  ])
        x['specs']['bhp']      = '%.0f bhp' % max(hp) 
        x['specs']['torque']   = '%.0f Nm'  % max(d[2])
        x['specs']['weight']   = '%.0f kg'  % mod_mass
        x['specs']['pwratio']  = '%.2f kg/bhp' % (mod_mass/max(hp))
        x['specs']['topspeed'] = 'buh?'
        
        x['minimodder'] = self.tree.get_dictionary()[1]
        
        # Dump the revised json
        json.dump(x, open(mod_ui, 'w'), indent=2)
        
        # Now delete the data.acd
        mod_data_acd = os.path.join(mod_car_path, 'data.acd')
        if os.path.exists(mod_data_acd):
            self.log('  Deleting mod data.acd (don\'t forget to pack!)')
            os.unlink(mod_data_acd)
        
        # Remember our selection and scan
        self.button_scan.click()
        self.combo_car.set_index(self.combo_car.get_index(car_name))
        
        # Open the mod car path
        os.startfile(mod_car_path)

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
        
        # Get the path to the car
        car  = self.srac[self.combo_car.get_text()]
        data = os.path.realpath(os.path.join(self.text_local(), 'content', 'cars', car, 'data'))

        self.log('Loading '+self.combo_car.get_text()+' data:')
        if not os.path.exists(data):
            self.log('  ERROR: '+data+ ' does not exist. Make sure you have unpacked data.acd.')
            self.button_create_mod.disable()
            self.plot.clear()
            self.plot.plot()
            self.grid_middle2.disable()
            return
        
        self.log('  Found '+data)
        self.button_create_mod.enable()
        self.grid_middle2.enable()
        
        # power.lut path
        power_lut = os.path.join(data, 'power.lut')
        
        # Make sure the first time we back up the original.
        # if not os.path.exists(power_lut+'.original'): 
        #     self.log('  Backing up power.lut -> power.lut.original')
        #     shutil.copy(power_lut, power_lut+'.original')
        
        # Delete data.acd if it exists
        # if os.path.exists(data+'.acd'):
        #     self.log('  Deleting data.acd for testing...')
        #     os.unlink(data+'.acd')

        self.plot.load_file(power_lut, delimiter='|')
        self.data = spinmob.data.databox()
        self.data.copy_all_from(self.plot)
        self.update_curves()        

    def update_curves(self):
        """
        Calculates and updates the plot.
        """
        if not len(self.plot): return
        
        self.plot.copy_all_from(self.data)
        
        # Update the plot
        x = self.plot[0]
        y = self.plot[1]
        
        # If we're smoothing
        if self.tree['Smooth']:
            
            # Sav-Gol filter
            x2 = linspace(min(x),max(x),self.tree['Smooth/Points'])
            y2 = interp(x2, x, y)
            x = self.plot[0] = x2
            y = self.plot[1] = savgol_filter(y2, self.tree['Smooth/Window'], self.tree['Smooth/Order'])
        
        x0 = max(self.plot[0])*self.tree['Restrictor Curve/RPM Range']
        p  = self.tree['Restrictor Curve/Exponent']
        self.plot['Restricted'] = y*((x0-x)/x0)**p
        self.plot['Scale'] = ((x0-x)/x0)**p
        
        self.plot.plot()

    def _tree_changed(self, *a):
        """
        Setting in the tree changed.
        """
        self.update_curves()
        

    def _button_scan_clicked(self, *a):
        """
        Scans the content directory for things to mod.
        """
        self.update_cars()

    def _button_browse_local_clicked(self, e):
        """
        Pop up the directory selector.
        """
        path = egg.dialogs.select_directory(text='Select the Assetto Corsa directory, apex-nerd.', default_directory='assetto_local')
        if(path):
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
        print('LOG:',text)
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
self = Modder()