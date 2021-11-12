# Jack's Assetto Server Tools & Tutorials (UNDER CONSTRUCTION)
This repository is for me to remember how I configured my AWS Assetto Corsa (AC) Ubuntu server, and to not lose the precious, precious scripts I wrote to automate it. Most of these instructions will work for any Assetto Server, though. 

**Targeted Workflow:** I host weekly races with the [League of Perpetual Novices](https://discord.me/LoPeN) with a 24/7 practice server, and car reservation via a simple [Google Sheet](https://www.google.ca/sheets/about/). The server is run in "pickup" mode, meaning people who don't sign up can still hop in at any time. Unfortunately, due to limitations in AC's server code, pickup mode precludes people choosing specific skins. I am also incredibly busy. As such, I need:
 1. A one-step of choosing a track-cars combo, uploading via `ssh`, restarting the server
 2. A quick way to adjust the reservation sheet so people can only select the specified cars
 3. An automated server script that grabs the reservation data and starts qualification a few hours before the race

**To be included here:**
 * Some information about Amazon Web Services
 * Instructions for setting up an Ubuntu AC server remotely
 * Instructions for setting up the reservation sheet
 * A script for selecting tracks, selecting cars, randomizing skins, uploading via `ssh`, restarting the server, copying the car list to the clipboard, and forwarding me to the google sheet so I can paste this in (making it easy for people to choose a car).
 * A script for the server to automatically grabbing the reservation data, update the config files, and restart the server, along with instructions for automating this with `crontab`.

## Amazon Web Services Server
In Canadia and Murrica, AWS offers an ["Always Free Tier"](https://aws.amazon.com/free/), providing 1 full-time processor, plenty of RAM / storage for, 15GB of free outbound traffic, and additional traffic at about $0.09 (CAD) per GB. We are still benchmarking this, and I'll post the kinds of usages to expect for a weekly race night, but preliminary tests suggest small weekly races will not hit the limit, and bigger grids will cost about $5/month, which is competitive with my favorite hosting company, [GTX Gaming](https://www.gtxgaming.co.uk/). 

I will not include information about how to set this up (Amazon will do a better job of this), except to say that I use:
 * A t2.micro Ubuntu instance
 * SSH login via a key file (\*.pem) that I generated and downloaded via the web interface

##
