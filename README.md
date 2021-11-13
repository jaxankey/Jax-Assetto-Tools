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

## Amazon Web Services (AWS)
I choose AWS to host because they have a very fast internet connection, nearly 100% uptime, and solid security measures. I also don't have any personal information on their network and really do not care if someone smashes their server to pieces. Just make sure you have a really strong password ;).

In Canadia and Murrica at least, AWS offers an ["Always Free Tier"](https://aws.amazon.com/free/), providing 1 full-time processor, plenty of RAM / storage, 15GB of free outbound traffic, and additional traffic at about $0.09 (CAD) per GB. We are still benchmarking usage, but preliminary tests suggest small weekly races may not hit the limit, and bigger grids may cost about $3-$7 per month, which is competitive with my favorite hosting company, [GTX Gaming](https://www.gtxgaming.co.uk/). 

I will not include much information about AWS (Amazon will do a better job of this), except to say that I set up the following:
 * A `t2.micro` instance with Ubuntu Linux on it
 * SSH login enabled using an identity file (\*.pem) that I generated and downloaded from the AWS web interface

In principle, the rest of this document will work with any Ubuntu- or Debian-based Linux server, and can be readily adapted to other operating systems. 

## Installing Assetto Server On Ubuntu

Once you have an Ubuntu server with `ssh` access installed via an identity file (something.pem), you can login with a command like `ssh -i "/path/to/identity/file.pem" username@blah-blah`, and similarly use `scp` to transfer files. To get `ssh` and `scp` on your Windows machine, I recommend [Cygwin](https://cygwin.com/): run the installer, and make sure to choose the latest `OpenSSH` package. Then the Windows console will have these commands. 

At this point, we can do the following to install the AC server:

First we need to make sure we have a few libraries installed, by trying to install them:

```console
username@blah-blah:~$ sudo apt-get install lib32gcc1 zlib1g
```

For me, zlib1g was already installed. Next, we can install Steam to the home directory:

```console
username@blah-blah:~$ mkdir ~/steam
username@blah-blah:~$ cd ~/steam
username@blah-blah:~/steam$ wget http://media.steampowered.com/client/steamcmd_linux.tar.gz
username@blah-blah:~/steam$ tar -xvf steamcmd_linux.tar.gz 
username@blah-blah:~/steam$ rm steamcmd_linux.tar.gz
```

Pop open the steam console with 
```console
username@blah-blah:~/steam$ ./steamcmd.sh +@sSteamCmdForcePlatformType windows
```
and install the AC server:
```console
Steam> login <username>;
Steam> passwd
Steam> enter security code sent to you registration email of your steam account 
Steam> force_install_dir ./assetto
Steam> app_update 302550  
Steam> exit
```

Check the directory `~/steam/assetto/cfg/` (e.g. by typing `ls ~/steam/assetto/cfg`) for configuration files. You can view / edit this file with `nano ~/steam/assetto/cfg/server_cfg.ini` (or use relative paths). I would change the variable `NAME` to something easy to find, so you can test the server, but leave the rest as is. 

Also check out `UDP_PORT`, `TCP_PORT`, and `HTTP_PORT`, so you know what ports you need to open. For my AWS server, I opened firewall ports `TCP/UDP 9600` and `TCP 8081` using the web interface, but you can also use a tool like `ufw` to configure your firewall. Make sure any hardware interfaces (e.g., routers) also forward these ports to the right computer. 

Next, change to the assetto directory, and start the server!

```console
username@blah-blah:~/steam$ cd assetto
username@blah-blah:~/steam/assetto$ ./acServer &> ~/ac-server-log.txt &
```

In the second command, we redirect the server output to the text file `~/ac-server-log.txt`, which you can view with `cat ~/ac-server-log.txt` or `nano` as above, and the last `&` makes it persist after I log out. Make sure the log file doesn't have any (serious) errors (you will see warnings), and check that you can find the `acServer` process with the command `htop` (may need to install this with `sudo apt install htop`). You can also run the `./acServer` with nothing to see the output in real time, which helps for troubleshooting.

Go find and try to connect to the server!

If you want to stop the server,

```console
pkill acServer
```

## Configuring a Reservations Google Sheet

More to come...

## server-uploader.py

I've used several server managers, and they're all clunky. All my server settings are the same every week except for the tracks and cars. Also, for pickup races, skins cannot be assigned to drivers, so they may as well just be random. As such, I wrote one that let's me do everything I need in one click. More to come...

![alt text](https://raw.githubusercontent.com/jaxankey/Jax-Assetto-Tools/main/screenshots/uploader.png)

### Installing & Running
* Python installation & libraries
* Relies on 7-zip: Windows needs a path

### Configuring

## Automatically Starting the Race

Set the server's local timezone, restart crontab, verify local timezone settings:
```
sudo dpkg-reconfigure tzdata
sudo service cron restart
timedatectl
```
More to come...
