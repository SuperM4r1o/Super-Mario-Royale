# Mario Royale NoSQL
An open-source server emulator for Mario Royale browser game.

![ScreenShot](https://i.imgur.com/4gpGSLs.png)

This is a project to backport MySQL functions to work without MySQL. Want to help us? Create a pull request!

You can discuss about the game and this emulator in [our discord](https://discord.gg/kV72ezsQwt).

## Binaries
If you are on Windows and don't want to install python to run this server, you can use the latest binary released in the [releases page](https://github.com/Igoorx/PyRoyale/releases).

## Dependencies
This project uses Python <b>3.7</b> and the following dependencies:
- twisted
- autobahn
- emoji
- configparser
- jsonschema
- discord_webhook **[OPTIONAL]**
- captcha **[OPTIONAL, REQUIRED IF ARGON2-CFFI IS INSTALLED]**
- argon2-cffi **[OPTIONAL]**

<b>If you are on Windows, the module <u>pypiwin32</u> may also be required.</b> 

## Tutorial
Install dependencies listed above, then run **server.py**
