# Mario Royale Self Host Tutorial
Guide to self-hosting your own Mario Royale server, whether it'd be to play with friends or whatever.

## Installation
To get started, you will have to download Python 3 [here](https://www.python.org/downloads/).<br>
If you are running MacOS or Linux, Python should already be installed with the command `python3`, when you install Python on Windows, use `python`.

## Cloning
To clone the repository from the command line use [Git](https://git-scm.com/), which you can download [here](https://git-scm.com/downloads).<br><br>

To clone the client, use this command: `git clone https://github.com/mroyale/mroyale-client.git`<br>
To clone the server, use this command: `git clone https://github.com/mroyale/mroyale-server.git`

## Setup
Once you've cloned both, `cd` to `mroyale-server`, then install the dependencies listen in the README file.<br>
After that rename `server.cfg.example` to `server.cfg` (If you'd like, you can setup or change some values there too).<br>
If you don't plan on using TLS go to the last few lines in `server.py` and change the `reactor.listenSSL(factory.listenPort, factory, contextFactory)` line to `reactor.listenTCP(factory.listenPort, factory)`

## Client
To setup the client, just install nginx/Apache and paste the client files in the main directory (`/var/www/html` by default on Debian-based systems), if you've changed the port then change it in `/js/server.js`, and you'll be done.

## End
Run `server.py` in the `mroyale-server` directory, and if all has gone well, you have successfully setup your very own Mario Royale self host.
