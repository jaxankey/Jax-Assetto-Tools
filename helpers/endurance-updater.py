#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, json, pprint, codecs, shutil, sys
import pandas, discord

# Change to the directory of this script
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# These are defined by endurance-updater.ini or endurance-updater.ini.private
csv_path          = ''
assetto_path      = ''
championship_path = ''
max_drivers       = 4
car_folders       = {}
filler_cars       = []

# Get the user values from the ini file
if os.path.exists('endurance-updater.ini.private'): p = 'endurance-updater.ini.private'
else                                              : p = 'endurance-updater.ini'
exec(open(p, 'r', encoding="utf8").read())

# Get the csv from the csv, either on the web or locally
data = pandas.read_csv(csv_path, dtype=str)

# Master data we assemble while looping
teams = dict() # Dictionary of team info by team name
ids   = dict() # Dictionary of activity by steam id

print('-----------------------------------------------')
print('CSV PARSE\n')

# Run through the spreadsheet in reverse order to favor later submissions.
for n in range(len(data['Team Car'])-1,-1,-1): 
    
    # Empty lines
    if not type(data['Team Car'][n]) == str: continue

    # Get the team name
    driver_names = []
    for m in range(1,max_drivers+1):
        driver_name = data['Driver '+str(m)+' Short Name'][n]
        if type(driver_name) == str:
            driver_name = driver_name.strip()[0:8]

            # No id
            if type(data['Driver '+str(m)+' Steam ID'][n]) != str:
                driver_name = driver_name+' [No SteamID] '
                print(driver_name)

            driver_names.append(driver_name)
    team_name = '/'.join(driver_names)

    # Get the car folder
    car       = car_folders[data['Team Car'][n].strip()].strip()
    livery    = str(data['Livery FOLDER Name'][n]).strip()
    if livery == 'nan': livery = 'random_skin'

    # If we have not already made this team (i.e., favoring later entries)
    if not team_name in teams:

        # create the dictionary for it
        teams[team_name] = dict(ids=[], names=[])
        teams[team_name]['car']    = car
        teams[team_name]['livery'] = livery
        #print(n, repr(team_name), car, livery)

        # Loop over the up to 8 drivers, adding their names and ids
        for m in range(1,max_drivers+1):
            
            key_name = 'Driver '+str(m)+' Short Name'
            key_id   = 'Driver '+str(m)+' Steam ID'
            
            if type(data[key_id][n])==str:
                
                # Get the driver name and steam id
                # n is the row number, m is column
                name = data[key_name][n]
                id   = data[key_id  ][n]
                if id in ids.keys(): 
                    print('  WARNING: ', id, '('+name+')', 'is in', repr(team_name), 'and', repr(ids[id]), '('+name+')')
                    print('            ID was not added to the earlier entry', repr(team_name))
                
                # Otherwise we add it to the dictionary
                else:
                    #print(' ', m, id, name)
                    ids[id] = team_name
                    teams[team_name]['ids']  .append(id)
                    teams[team_name]['names'].append(name)

# Pop all teams with no ids
team_names = list(teams.keys())
for team_name in team_names:
    if len(teams[team_name]['ids'])==0:
        teams.pop(team_name)

# print('-----------------------------------------------')
#pprint.pprint(teams)
print('\n-----------------------------------------------')
print('CHAMPIONSHIP UPDATE')

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
    print(championship_path, 'did not load.')
    pprint.pprint(teams)

# Start the show
else:
    # All the team names
    team_names = list(teams.keys())
    
    # List of missing skins to print for the user at the end.
    missing_skins = []

    # Loop over the entrylist for the event in the championship json
    for n in range(len(list(c['Events'][0]['EntryList'].keys()))): 
        
        # If we have not yet depleted our teams
        if n < len(team_names):
            
            # Get earliest entry first.
            team_name = team_names[len(team_names)-1-n]

            # Get the car folder
            car = teams[team_name]['car']

            # If the livery folder exists, use it; otherwise, use 'random_skin'
            livery = teams[team_name]['livery']
            ids = ';'.join(teams[team_name]['ids'])
            
            print(str(n+1)+'.', repr(team_name), repr(car), repr(livery)) #, repr(ids))
            print('    '+'\n    '.join(teams[team_name]['names']))
            
            if livery != 'random_skin' and not os.path.exists(os.path.join(assetto_path, 'content', 'cars', car, 'skins', livery)): 
                missing_skins.append('  '+ repr(teams[team_name]['livery']) + ' ('+team_name+', '+car+')')
                livery = 'random_skin'
            
        # One of the remaining slots. Make sure to overwrite what's there with "no team" and "no ids"
        else: 
            team_name = ''
            car       = filler_cars[n%len(filler_cars)]
            livery    = 'random_skin'
            ids       = ''

        # Some instances start with CAR_0 and some start with CAR_1
        if 'CAR_0' in c['Classes'][0]['Entrants']: m = n
        else:                                      m = n+1

        # Make sure the internal uuid's match
        uuid = c['Classes'][0]['Entrants']['CAR_%d'%(m)]['InternalUUID']
        classID = c['Classes'][0]['ID']        
        c['Events'][0]['EntryList']['CAR_%d'%(n)]['InternalUUID'] = uuid
        c['Events'][0]['EntryList']['CAR_%d'%(n)]["ClassID"]      = classID

        c['Classes'][0]['Entrants']['CAR_%d'%(m)]['PitBox'] = n
        c['Events'][0]['EntryList']['CAR_%d'%(n)]['PitBox'] = n

        c['Classes'][0]['Entrants']['CAR_%d'%(m)]['Name'] = team_name
        c['Events'][0]['EntryList']['CAR_%d'%(n)]['Name'] = team_name

        c['Classes'][0]['Entrants']['CAR_%d'%(m)]['Model'] = car
        c['Events'][0]['EntryList']['CAR_%d'%(n)]['Model'] = car

        c['Classes'][0]['Entrants']['CAR_%d'%(m)]['Skin'] = livery
        c['Events'][0]['EntryList']['CAR_%d'%(n)]['Skin'] = livery

        c['Classes'][0]['Entrants']['CAR_%d'%(m)]['GUID'] = ids
        c['Events'][0]['EntryList']['CAR_%d'%(n)]['GUID'] = ids

    if len(missing_skins): 
        s = 'MISSING SKIN FOLDERS\n'+'\n'.join(missing_skins)
        print('\n-------------------------------------\n'+s)
    
        
    print()

    if len(sys.argv) > 1 and sys.argv[1] == 'yes' or input('Do it? ').strip() == 'yes':

        shutil.move(championship_path, championship_path+'.backup', )
        f = open(championship_path, 'w', encoding="utf8")
        json.dump(c, f, indent=2)
        f.close()

    else: 
        pprint.pprint(c)