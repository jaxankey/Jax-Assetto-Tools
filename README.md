# Jack's Assetto Server Tutorial & Tools (UNDER CONSTRUCTION)
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

## About Amazon Web Services (AWS) Servers
In principle, the rest of this document will work with any Ubuntu- or Debian-based Linux server, and can be readily adapted to other operating systems. I choose AWS to host because they have a very fast internet connection, nearly 100% uptime, and solid security measures. I also don't have any personal information on their network and really do not care if someone smashes their server to pieces. Just make sure you have a really strong password ;).

In Canadia and Murrica at least, AWS offers an ["Always Free Tier"](https://aws.amazon.com/free/), providing 1 full-time processor, plenty of RAM / storage, 15GB of free outbound traffic, and additional traffic at about $0.09 (CAD) per GB. We are still benchmarking usage, but preliminary tests suggest small weekly races may not hit the limit, and bigger grids may cost about $3-$7 per month, which is competitive with my favorite hosting company, [GTX Gaming](https://www.gtxgaming.co.uk/). 

I will not include much information about AWS (Amazon will do a better job of this), except to say that I set up the following:
 * A `t2.micro` instance with Ubuntu Linux on it
 * SSH login enabled via a key file (\*.pem) that I generated and downloaded from the AWS web interface

## 
