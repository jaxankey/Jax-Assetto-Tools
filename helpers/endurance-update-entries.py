import pandas, os, json, pprint, codecs, shutil

# These are defined by endurance-updater.ini or endurance-updater.ini.private
csv_path          = ''
championship_path = ''

# Get the user values from the ini file
if os.path.exists('endurance-updater.ini.private'): p = 'endurance-updater.ini.private'
else                                              : p = 'endurance-updater.ini'
exec(open(p, 'r', encoding="utf8").read())

# Get the csv from the web or local
data = pandas.read_csv(csv_path, dtype=str)

# Put together a dictionary by team name, and keep track of all steam ids to make sure there are no duplicates
teams = dict()
ids   = dict()

# Reverse order to favor later submissions.
for n in range(len(data['Team Name'])-1,-1,-1):
    team_name = data['Team Name'][n].strip()

    # Get a dictionary for each team
    teams[team_name] = dict(ids=[], names=[], livery='')
    teams[team_name]['livery'] = str(data['Livery Name'][n]).strip()
    
    print(n, team_name)

    # Loop over the up to 6 drivers, adding their names and ids
    for m in range(1,7):
        
        key_name = 'Driver '+str(m)+' Discord Name'
        key_id   = 'Driver '+str(m)+' Steam ID'
        
        if type(data[key_id][n])==str:
            
            # n is the row number, m is column
            name = data[key_name][n]
            id   = data[key_id  ][n]
            print(' ', m, id, name)
            if id in ids.keys(): print('WARNING: ', id, 'is in', team_name, 'and', ids[id], '('+name+')')
            
            # Otherwise we add it to the dictionary
            else:
                ids[id] = team_name
                teams[team_name]['ids'].append(id)
                teams[team_name]['names'].append(name)

print('-----------------------------------------------')
pprint.pprint(teams)
print('-----------------------------------------------')

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
team_names = list(teams.keys())
for n in range(len(list(c['Events'][0]['EntryList'].keys()))): 
    print('Entry', n)

    # If we have a team fill it
    if n < len(team_names):
        team_name = team_names[n]
        skin = teams[team_name]['livery']
        ids = ';'.join(teams[team_name]['ids'])
        print(' ', team_name, skin, ids)
    else: 
        team_name = ''
        skin = ''
        ids = ''

    c['Classes'][0]['Entrants']['CAR_%d'%(n+1)]['Name'] = team_name
    c['Events'][0]['EntryList']['CAR_%d'%(n  )]['Name'] = team_name

    c['Classes'][0]['Entrants']['CAR_%d'%(n+1)]['Skin'] = skin
    c['Events'][0]['EntryList']['CAR_%d'%(n  )]['Skin'] = skin

    c['Classes'][0]['Entrants']['CAR_%d'%(n+1)]['GUID'] = ids
    c['Events'][0]['EntryList']['CAR_%d'%(n  )]['GUID'] = ids

shutil.move(championship_path, championship_path+'.backup', )
f = open(championship_path, 'w', encoding="utf8")
json.dump(c, f, indent=2)
f.close()
