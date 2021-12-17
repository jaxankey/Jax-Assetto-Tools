# Jack's Assetto Server Tutorial & Tools
This repository is for me to remember how I configured my Assetto Corsa (AC) Ubuntu server running on Amazon Web Services (AWS), and to not lose the precious, precious scripts I wrote to automate it. 

**Targeted Workflow:** I host weekly races with the [League of Perpetual Novices](https://discord.me/LoPeN), which has
 * a practice server open 24/7
 * car reservation via a simple [Google Sheet](https://www.google.ca/sheets/about/)  

The server is run in "pickup" mode, meaning people who don't sign up can still hop in at any time. Unfortunately, due to limitations in AC's server code, pickup mode precludes specific people choosing specific skins, ballasts, or restrictor settings. Combined with how busy I am, I need:
 1. A quick method for choosing a track-cars combo, uploading (via `ssh`), restarting the server, setting up the reservations sheet, and informing everyone on the discord server.
 2. A discord bot that monitors the server, sending Discord messages with lap times and who is on the server
 3. A script that grabs the reservation data, reconfigures the server, starts the event, and notifies the Discord group

**To be included here:**
 * Some basic information about Amazon Web Services
 * Instructions for setting up a remote Ubuntu AC server
 * Instructions for setting up a google reservations sheet
 * Information about how to use the scripts

See the [wiki](https://github.com/jaxankey/Jax-Assetto-Tools/wiki) for more information!
