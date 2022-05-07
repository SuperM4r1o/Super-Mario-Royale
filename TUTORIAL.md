# Mario Royale Self Host Tutorial
Guide to self-hosting your own Mario Royale server, whether it'd be to play with friends or to host on your own.

## Windows
Thanks to a unicode decode error, the server doesn't work on Windows. Cool.

## Installation
To get started, you will have to download Python 3 [here](https://www.python.org/downloads/).<br>
If you are running MacOS or Linux, Python should already be installed with the command `python3`.

## Cloning
To clone the repository from the command line use [Git](https://git-scm.com/), which you can download [here](https://git-scm.com/downloads).<br><br>

To clone the client, use this command: `git clone https://github.com/mroyale/mroyale-client.git`<br>
To clone the server, use this command: `git clone https://github.com/mroyale/mroyale-server.git`

## Setup
Once you've cloned both, `cd` to `mroyale-server`, then install the dependencies listed in the README file.<br>
After that rename `server.cfg.example` to `server.cfg` (If you'd like, you can setup or change some values there too).<br>
If you don't plan on using TLS go to the last few lines in `server.py` and change the `reactor.listenSSL(factory.listenPort, factory, contextFactory)` line to `reactor.listenTCP(factory.listenPort, factory)`

## Levels
The server has 2 ways of getting level data:
- From the `levels` folder which doesn't exist by default
- From the web server (/game/world-x)<br>
For the first method, create a `levels` folder where the server files are, then put in worlds as you like (required: lobby.json)<br>
For the second method, you'll need to make a `game` folder where the the game files are hosted (ex: /var/www/html/game), put in the worlds (again, required: lobby.json), then in `server.cfg` (assuming you renamed it), scroll down to the `Worlds:` part, then insert the filename of the world (minus the .json part, ex: `Worlds: world-1,world-p`)

## Client
To setup the client, just install nginx/Apache and paste the client files in the main directory (`/var/www/html` by default on Debian-based systems), if you've changed the port then change it in `/js/server.js`, and you'll be done.

## End
Run `server.py` in the `mroyale-server` directory, and if all has gone well, you have successfully setup your very own Mario Royale self host.
