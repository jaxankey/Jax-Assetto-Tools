# Jack's Assetto Tools
This repository is for me to remember how I configured my Assetto Corsa (AC) Ubuntu server running on Amazon Web Services (AWS), and to not lose the precious, precious scripts I wrote to automate it. 

**Targeted Workflow:** I host a weekly race night at the [League of Perpetual Novices](https://discord.me/LoPeN), which has a practice server open 24/7 and car reservation via a simple [Google Sheet](https://www.google.ca/sheets/about/). The server is run in "pickup" mode, meaning people who don't sign up can (and do!) hop in at any time. Unfortunately, due to limitations in AC's server code, pickup mode precludes assigning specific skins, ballasts, or restrictors to specific people. Combine this with how busy I am, and I want the following:
 1. A few-click method for me to automatically: 
    * upload the minimum required files to the AC server
    * reconfigure and restart the server
    * set up the reservations sheet
    * inform everyone about the event on [our Discord server](https://discord.me/LoPeN).
 2. A simple-to-configure bot that monitors the server, sending Discord messages with lap times and who is on the server
 3. An event-night script that grabs the current reservation data, reconfigures the server, starts the event, and notifies everyone

**To be included here:**
 * Some basic information about Amazon Web Services
 * Instructions for setting up a remote Ubuntu AC server
 * Instructions for setting up a google reservations sheet
 * Information about how to use the scripts

**[See the Wiki](https://github.com/jaxankey/Jax-Assetto-Tools/wiki/Jax-Assetto-Tools-Wiki)** for more information!
