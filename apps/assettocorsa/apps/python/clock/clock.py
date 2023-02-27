import ac
from time import strftime, time
from os.path import exists

# App name and geometry
app_name = 'Clock'
width   = 97 # Width in AM/PM format
width24 = 61 # Width in 24-hour format
height  = 30

# Path to the ini file for remembering the mode
# The default working directory is assettocorsa\
path_ini = 'apps\\python\\clock\\clock.ini'

def log(*a):
    """
    Send the string form of the supplied arguments to the log and console.
    """
    a = list(a)
    for n in range(len(a)): a[n] = str(a[n])
    s = app_name + ': ' + ' '.join(a)
    ac.log(s)
    ac.console(s)

class Clock():
    """
    Container class for all the clock's internal attributes and functions.
    """

    def __init__(self):

        # Last update time
        self.t0    = 0 

        # Whether we're in am_pm mode or not
        self.am_pm = True
        self.t_click = 0
        
        # Make the app and set its size
        self.app_window = ac.newApp(app_name)
        ac.setSize(self.app_window, width, height)
	
        # Make the label for the time
        self.label_time = ac.addLabel(self.app_window, "TIME")
        ac.setPosition(self.label_time, width/2, 0)
        ac.setFontAlignment(self.label_time, 'center')
        ac.setFontSize(self.label_time, 20)

        # Hide the needless window stuff.
        ac.drawBackground(self.app_window, 0)
        ac.drawBorder(self.app_window, 0)
        ac.setTitle(self.app_window, "")
        ac.setIconPosition(self.app_window, 10000, 10000)

        # Clicks toggle the format
        ac.addOnClickedListener(self.app_window, app_window_clicked)
    
        # Load the previous settings
        self.load_ini()

    def load_ini(self):
        """
        Loads the previous settings if they exist.
        """
        if exists(path_ini): 
            with open(path_ini, 'r') as f:
                self.am_pm = eval(f.readline())
                self.set_am_pm()
        
    def save_ini(self):
        """
        Saves the settings to the ini file
        """
        with open(path_ini, 'w') as f: f.write(str(self.am_pm))

    def set_am_pm(self):
        """
        Updates the gui based on am_pm
        """
        # Update width
        if self.am_pm: 
            ac.setSize(self.app_window, width, height)
            ac.setPosition(self.label_time, width/2, 0)
        else:     
            ac.setSize(self.app_window, width24, height)
            ac.setPosition(self.label_time, width24/2, 0)
        

# Main function called at first run.
clock = None # Instance of Clock()
def acMain(ac_version):
    global clock

    # Create an instance. This also populates the gui.
    clock = Clock()
    
    # This needs to be here for AC.
    return app_name

# This function is called every frame in game,
# with dt being the time in seconds since the last call.
def acUpdate(dt):
    global clock

    # Save CPU cycles and rendering
    t = time()
    if t - clock.t0 < 1: return
    clock.t0 = t
    
    # Set the text
    if clock.am_pm: 
        ac.setText(clock.label_time, strftime('%I:%M %p'))
    else:
        ac.setText(clock.label_time, strftime('%H:%M'))


##################
# OTHER EVENTS
##################
def app_window_clicked(*a):
    """
    Switches format.
    """
    global clock
    
    # Look for double-click, toggle mode
    t = time()
    if t-clock.t_click < 0.3: clock.am_pm = not clock.am_pm
    clock.t_click = t

    # Updates the gui
    clock.set_am_pm()

    # Save it
    clock.save_ini()

    # Trigger immediate refresh
    clock.t0 = 0

