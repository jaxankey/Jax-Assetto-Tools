# Jack's Assetto Server Tutorial & Tools (UNDER CONSTRUCTION)
This repository is for me to remember how I configured my Assetto Corsa (AC) Ubuntu server running on Amazon Web Services (AWS), and to not lose scripts I wrote to automate it. Most of this will work for any remote Linux-based AC server, though.

**Targeted Workflow:** I host weekly races with the [League of Perpetual Novices](https://discord.me/LoPeN) with a 24/7 practice server, and car reservation via a simple [Google Sheet](https://www.google.ca/sheets/about/). The server is run in "pickup" mode, meaning people who don't sign up can still hop in at any time. Unfortunately, due to limitations in AC's server code, pickup mode precludes people choosing specific skins. I am also incredibly busy. As such, I need:
 1. A quick method for choosing a track-cars combo, uploading (via `ssh`), restarting the server, setting up the reservations sheet, and informing everyone on the discord server.
 2. A discord bot that monitors the server, sending Discord messages with lap times and who is on the server
 3. A script that grabs the reservation data, reconfigures the server, starts the event, and notifies the Discord group

**To be included here:**
 * Some basic information about Amazon Web Services
 * Instructions for setting up a remote Ubuntu AC server
 * Instructions for setting up a google reservations sheet
 * Information about how to use the scripts

## Amazon Web Services (AWS)
**About:** I choose AWS to host because they have a very fast internet connection, nearly 100% uptime, and solid security measures. I also don't have any personal information on their network and really do not care if someone smashes their server to pieces, either digitally or mechanically. In Canadia and 'Murrica (at least), AWS offers an ["Always Free Tier"](https://aws.amazon.com/free/), providing 1 full-time processor, plenty of RAM / storage, 15GB of free outbound bandwidth per month, and additional traffic at $0.09 (CAD) per GB. 

**Bandwidth Usage:** Hosting a weekly event with 10-15 drivers (two 40-minute heats, qualifying, and a 24/7 practice server) uses a few GB of outbound bandwidth per month. With the server set to 18 Hz refresh rate (plenty), we measured that ~10 cars use ~170 KiB/s, meaning a solid hour of racing uses about 630 MB. For N clients, the server must send N people N packets each, so this data rate should nominally scale as N *squared*, meaning 24 clients should use at most ~4 GB/hour, while a handful of people randomly practicing during the week use essentially nothing. Additionally, Assetto does some optimization, sending less information for cars that are farther away, meaning N-squared is a generous upper bound. To get a sense of potential cost beyond 15 GB, if you get 40 people to race a full hour 5 times a month, the N-squared upper bound is about 50 GB or ~$5 CAD. This is competitive with my favorite hosting company, [GTX Gaming](https://www.gtxgaming.co.uk/), which provided me 24 slots for about $5-$6 CAD a month (note these could be *fully utilized 24/7*; it's a very different pricing model!). I switched to AWS because we do weekly races and I wanted to automate everything to encourage participation and reduce my workload!

**AWS Configuration:** I will not include much information about how to set up and access an AWS server (Amazon will do a better job of this), except to say that you need to create an "EC2 Instance", and mine is configured with the following:
 * A `t2.micro` instance with Ubuntu Linux on it
 * SSH login enabled using an identity file (\*.pem) generated and downloaded from the AWS web interface

In principle, the rest of this document will work with any Ubuntu- or Debian-based Linux server, and can be readily adapted to other operating systems. 

## Installing and Running the Assetto Corsa Server on Ubuntu

Once we have a remote Ubuntu server with `ssh` access via an identity file, we can login with a command like `ssh -i "C:\local\path\to\identity_file.pem" username@blah-blah` (AWS provides this command via the "Connect" button associated with your instance, under "SSH Client"). To get a nice version of `ssh` on a Windows machine, I recommend [Cygwin](https://cygwin.com/): run the installer, and make sure to include the latest `OpenSSH` package; then the Windows console will have these command. Note this comes with `scp`, which allows for uploading over `ssh` connections (used by the content uploader!), but for simple file transfers you can also use something like [FileZilla](https://filezilla-project.org/), connecting via "SFTP" with the same identity file.

Once we are logged in via `ssh`, we can install the Assetto Corsa server. First we need to make sure we have a few libraries installed:

```console
username@blah-blah:~$ sudo apt-get install lib32gcc1 zlib1g
```

For me, zlib1g was already installed. Next we install Steam (I installed to the home directory `~`, i.e., `/home/ubuntu`):

```console
username@blah-blah:~$ mkdir ~/steam
username@blah-blah:~$ cd ~/steam
username@blah-blah:~/steam$ wget http://media.steampowered.com/client/steamcmd_linux.tar.gz
username@blah-blah:~/steam$ tar -xvf steamcmd_linux.tar.gz 
username@blah-blah:~/steam$ rm steamcmd_linux.tar.gz
```

Then open the steam console with 
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

Next, we check the directory `~/steam/assetto/cfg/` (e.g. by typing `ls ~/steam/assetto/cfg`) for configuration files. We can view / edit the `server_cfg.ini` file with `nano ~/steam/assetto/cfg/server_cfg.ini` (or use relative paths). To get the server running, I recommend only changing the variable `NAME` to something that will be easy to find in the Kunos list. Also look for and note the values of `UDP_PORT`, `TCP_PORT`, and `HTTP_PORT`, so you know what ports you need to open. On my AWS server, I ended up opening firewall ports `TCP/UDP 9600` and `TCP 8081` using the web interface (instance page -> "Security" -> link below "Security Groups" -> "Edit Inbound Rules"), but you can also use a tool like `ufw` or something fancier to configure your firewall. If you're running a home server, also make sure any routers etc are forwarding these ports to the right computer.

Finally, change to the assetto directory, and start the server:

```console
username@blah-blah:~/steam$ cd assetto
username@blah-blah:~/steam/assetto$ ./acServer
```

Now go find and try to connect to the server! You will see information logged to the running terminal as server events happen. 

If you want the server to continue running after you logout, first kill the current server with `ctrl`+`c`, then use the command

```
username@blah-blah:~/steam/assetto$ ./acServer &> ~/acServer.log &
```

Here, `&>` redirects the output to the file `~/acServer.log`, which we can view with `cat ~/acServer.log` or `nano ~/acServer.log` as above. The last `&` ensures this will continue to run after we log out. Make sure the log file doesn't have any (serious) errors (some warnings are normal), and check that you can find the `acServer` process with the command `htop` (installed with `sudo apt install htop`). 

If you want to stop the server, you can do so from `htop`, or run a command like

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
