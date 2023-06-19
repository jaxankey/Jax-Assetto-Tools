#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pandas, os, json, pprint, codecs, shutil, sys

# Change to the directory of this script
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# These are defined by endurance-updater.ini or endurance-updater.ini.private
csv_path          = ''
assetto_path      = ''
championship_path = ''
car_folders       = {}

# Get the user values from the ini file
if os.path.exists('endurance-updater.ini.private'): p = 'endurance-updater.ini.private'
else                                              : p = 'endurance-updater.ini'
exec(open(p, 'r', encoding="utf8").read())

# Get the csv from the csv, either on the web or locally
data = pandas.read_csv(csv_path, dtype=str)

# Master data we assemble while looping
teams = dict() # Dictionary of team info by team name
ids   = dict() # Dictionary of activity by steam id

# Run through the spreadsheet in reverse order to favor later submissions.
for n in range(len(data['Team Name'])-1,-1,-1): 
    
    # Empty lines
    if not type(data['Team Name'][n]) == str: continue

    # Get the team name and car folder
    team_name = data['Team Name'][n].strip()
    car       = car_folders[data['Team Car'][n].strip()].strip()
    livery    = str(data['Livery FOLDER Name'][n]).strip()

    # If we have not already made this team (i.e., favoring later entries)
    if not team_name in teams:

        # create the dictionary for it
        teams[team_name] = dict(ids=[], names=[])
        teams[team_name]['car']    = car
        teams[team_name]['livery'] = livery
        print(n, repr(team_name), car, livery)

        # Loop over the up to 8 drivers, adding their names and ids
        for m in range(1,9):
            
            key_name = 'Driver '+str(m)+' Discord Name'
            key_id   = 'Driver '+str(m)+' Steam ID'
            
            if type(data[key_id][n])==str:
                
                # Get the driver name and steam id
                # n is the row number, m is column
                name = data[key_name][n]
                id   = data[key_id  ][n]
                print(' ', m, id, name)
                if id in ids.keys(): 
                    print('  WARNING: ', id, '('+name+')', 'is in', team_name, 'and', ids[id], '('+name+')')
                    print('  They were not added to the earlier entry', team_name)
                
                # Otherwise we add it to the dictionary
                else:
                    ids[id] = team_name
                    teams[team_name]['ids']  .append(id)
                    teams[team_name]['names'].append(name)

# print('-----------------------------------------------')
pprint.pprint(teams)
# print('-----------------------------------------------')

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

# Now loop over the teams and update the championship
# Function for loading a json at the specified path
c = load_json(championship_path)

if c == None: 
    print('NOPE', championship_path, 'did not load.')
    quit()

team_names = list(teams.keys())
for n in range(len(list(c['Events'][0]['EntryList'].keys()))): 
    print('Entry', n+1)

    # If we have a team fill the slot and there are id's left in this team
    if n < len(team_names) and len(teams[team_names[len(team_names)-1-n]]['ids']):

        # Get earliest entry first.
        team_name = team_names[len(team_names)-1-n]

        # Get the car folder
        car = teams[team_name]['car']

        # If the livery folder exists, use it; otherwise, use 'random_skin'
        if os.path.exists(os.path.join(assetto_path, 'content', 'cars', car, 'skins', teams[team_name]['livery'])): 
            livery = teams[team_name]['livery']
        else:                                                               
            livery = 'random_skin'
            print('  WARNING: No skin folder', repr(teams[team_name]['livery']))
        ids = ';'.join(teams[team_name]['ids'])
        print(' ', repr(team_name), repr(livery), repr(ids))
    
    # One of the remaining slots. Make sure to overwrite what's there with "no team"
    else: 
        team_name = ''
        livery = 'random_skin'
        ids = ''

    # Make sure the internal uuid's match
    uuid = c['Classes'][0]['Entrants']['CAR_%d'%(n+1)]['InternalUUID']
    c['Events'][0]['EntryList']['CAR_%d'%(n  )]['InternalUUID'] = uuid

    c['Classes'][0]['Entrants']['CAR_%d'%(n+1)]['PitBox'] = n
    c['Events'][0]['EntryList']['CAR_%d'%(n  )]['PitBox'] = n

    c['Classes'][0]['Entrants']['CAR_%d'%(n+1)]['Name'] = team_name
    c['Events'][0]['EntryList']['CAR_%d'%(n  )]['Name'] = team_name

    c['Classes'][0]['Entrants']['CAR_%d'%(n+1)]['Model'] = car
    c['Events'][0]['EntryList']['CAR_%d'%(n  )]['Model'] = car

    c['Classes'][0]['Entrants']['CAR_%d'%(n+1)]['Skin'] = livery
    c['Events'][0]['EntryList']['CAR_%d'%(n  )]['Skin'] = livery

    c['Classes'][0]['Entrants']['CAR_%d'%(n+1)]['GUID'] = ids
    c['Events'][0]['EntryList']['CAR_%d'%(n  )]['GUID'] = ids

if len(sys.argv) > 1 and sys.argv[1] == 'yes' or input('Do it? ').strip() == 'yes':

    shutil.move(championship_path, championship_path+'.backup', )
    f = open(championship_path, 'w', encoding="utf8")
    json.dump(c, f, indent=2)
    f.close()

else: 
    pprint.pprint(c)