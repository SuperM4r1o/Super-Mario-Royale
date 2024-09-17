from datetime import datetime
import os
from queue import Empty
import sys
import datastore
import shop
import util
#import objgraph

if sys.version_info.major != 3:
    sys.stderr.write("You need python 3.7 or later to run this script\n")
    if os.name == 'nt': # Enforce that the window opens in windows
        print("Press ENTER to exit")
        input()
    exit(1)



from twisted.python import log
from twisted.internet import task, ssl
log.startLogging(sys.stdout)

from autobahn.twisted import install_reactor
# we use an Autobahn utility to import the "best" available Twisted reactor
reactor = install_reactor(verbose=False,
                          require_optimal_reactor=False)

try:
    from discord_webhook import DiscordWebhook
    DWH_IMPORT = True
except Exception as e:
    print("Can't import discord_webhook, discord functioning will be disabled.")
    DWH_IMPORT = False

try:
    from captcha.image import ImageCaptcha
    CP_IMPORT = True
except:
    print("Can't import captcha, captcha functioning will be disabled.")
    CP_IMPORT = False

LOG_ENABLED = True


from autobahn.twisted.websocket import WebSocketServerProtocol, WebSocketServerFactory
from twisted.internet.protocol import Factory
import json
import jsonschema
import string
import random
import base64
import hashlib
import traceback
import configparser
from io import BytesIO
from buffer import Buffer
from player import Player
from match import Match

NUM_GM = 3

class MyServerProtocol(WebSocketServerProtocol):
    def __init__(self, server):
        WebSocketServerProtocol.__init__(self)

        self.server = server
        self.address = str()
        self.recv = bytearray()

        self.pendingStat = None
        self.stat = str()
        self.username = str()
        self.session = str()
        self.player = None
        self.blocked = bool()
        self.account = {}
        self.accountPriv = {}

        self.dcTimer = None
        #self.maxConLifeTimer = None

    def startDCTimerIndependent(self, time):
        reactor.callLater(time, self.sendClose2)

    def startDCTimer(self, time):
        self.stopDCTimer()
        self.dcTimer = reactor.callLater(time, self.sendClose2)

    def sendClose2(self):
        #this is a wrapper for debugging only
        #print("sendClose2")
        #self.crash()
        self.sendClose()

    def stopDCTimer(self):
        try:
            self.dcTimer.cancel()
        except:
            pass

    def onConnect(self, request):
        #print("Client connecting: {0}".format(request.peer))

        if "x-real-ip" in request.headers:
            self.address = request.headers["x-real-ip"]

    def onOpen(self):
        #print("WebSocket connection open.")

        if not self.address:
            self.address = self.transport.getPeer().host

        # A connection can only be alive for 20 minutes
        #self.maxConLifeTimer = reactor.callLater(20 * 60, self.sendClose2)
 
        self.startDCTimer(25)
        self.setState("l")

    def onClose(self, wasClean, code, reason):
        self.stopDCTimer()

        if self.address in self.server.captchas:
            del self.server.captchas[self.address]

        if self.username != "" and self.username in self.server.authd:
            self.server.authd.remove(self.username)

        if self.stat == "g" and self.player != None:
            self.player.match.sendDisconnectMessage(self.player)
            if self.username != "":
                stats={}
                if not self.player.match.private:
                    if self.player.wins > 0:
                        stats["wins"] = self.player.wins
                    if self.player.deaths > 0:
                        stats["deaths"] = self.player.deaths
                    if self.player.kills > 0:
                        stats["kills"] = self.player.kills
                    if self.player.coins != 0:
                        stats["coins"] = self.player.coins
                if self.blocked:
                    stats["isBanned"] = True
                if self.player.forceRenamed:
                    stats["nickname"] = self.player.name
                if self.player.client.username.lower() in ["terminalkade", "dimension", "casini loogi", "arcadegamer1929"]:
                    stats["isDev"] = True
                if self.player.isJunior:
                    stats["isJunior"] = True
                if self.player.muted:
                    stats["isMuted"] = True
                else:
                    stats["isMuted"] = True
                if self.player.isMod:
                    stats["isMod"] = self.player.isMod
                if 0<len(stats):
                    datastore.updateStats(self.player.client.username, stats)
            self.server.players.remove(self.player)
            self.player.match.removePlayer(self.player)
            self.player.match = None
            self.player = None
            self.pendingStat = None
            self.stat = str()
        # print("WebSocket connection closed: {0}".format(reason))
        

    def onMessage(self, payload, isBinary):
        if len(payload) == 0:
            return

        self.server.in_messages += 1

        try:
            if isBinary:
                self.recv += payload
                while len(self.recv) > 0:
                    if not self.onBinaryMessage():
                        break
            else:
                self.onTextMessage(payload.decode('utf8'))
        except Exception as e:
            traceback.print_exc()
            self.sendClose2()
            self.recv.clear()
            return

    def sendJSON(self, j):
        self.server.out_messages += 1
        #print("sendJSON: "+str(j))
        try:
            self.sendMessage(json.dumps(j).encode('utf-8'), False)
        except:
            print("sendJSON() exception")

    def sendText(self, t):
        self.server.out_messages += 1
        try:
            self.sendMessage(t, False)
        except:
            print("sendText() exception")

    def sendBin(self, code, buff):
        self.server.out_messages += 1
        msg=Buffer().writeInt8(code).write(buff.toBytes() if isinstance(buff, Buffer) else buff).toBytes()
        #print("sendBin: "+str(code)+" "+str(msg))
        try:
            self.sendMessage(msg, True)
        except:
            print("sendBin() exception")

    def loginSuccess(self):
        self.sendJSON({"packets": [
            {"name": self.player.name, "team": self.player.team, "type": "l01", "skin": self.player.skin}
        ], "type": "s01"})
    
    def setState(self, state):
        self.stat = self.pendingStat = state
        self.sendJSON({"packets": [
            {"state": state, "type": "s00"}
        ], "type": "s01"})

    def exception(self, message):
        self.sendJSON({"packets": [
            {"message": message, "type": "x00"}
        ], "type": "s01"})

    def block(self, reason):
        if self.blocked or len(self.player.match.players) == 1:
            return
        print("Player blocked: {0}".format(self.player.name))
        self.blocked = True
        if not self.player.dead:
            self.player.match.broadBin(0x11, Buffer().writeInt16(self.player.id), self.player.id) # KILL_PLAYER_OBJECT
        self.server.blockAddress(self.address, self.player.name, reason)

    def onTextMessage(self, payload):
        #print("Text message received: {0}".format(payload))
        packet = json.loads(payload)
        type = packet["type"]

        if self.stat == "l":
            if type == "l00": # Input state ready
                if self.player is not None or self.pendingStat is None:
                    self.sendClose2()
                    return
                self.pendingStat = None
                self.stopDCTimer()

                if self.address != "127.0.0.1" and self.server.getPlayerCountByAddress(self.address) >= self.server.maxSimulIP:
                    self.sendClose2()
                    return

                if self.server.shuttingDown:
                    self.setState("g") # Ingame
                    return
                #for b in self.server.blocked:
                #    if b[0] == self.address:
                #        self.blocked = True
                #        self.setState("g") # Ingame
                #        return

                name = packet["name"]
                team = packet["team"][:3].strip().upper()
                priv = packet["private"] if "private" in packet else False
                skin = packet["skin"] if "skin" in packet else 0
                gm = int(packet["gm"]) if "gm" in packet else 0
                gm = gm if gm in range(NUM_GM) else 0
                gm = ["royale", "pvp", "hell"][gm]
                isDev = self.account["isDev"] if "isDev" in self.account else False
                isMod = self.account["isMod"] if "isMod" in self.account else False
                isJunior = self.account["isJunior"] if "isDev" in self.account else False
                isMuted = self.account["isMuted"] if "isMuted" in self.account else False
                self.player = Player(self,
                                     name,
                                     (team if (team != "" or priv) else self.server.defaultTeam).lower(),
                                     self.server.getMatch(team, priv, gm),
                                     skin,
                                     gm,
                                     isDev,
                                     isJunior,
                                     isMod,
                                     isMuted
                                     )
                #if priv:
                #    self.maxConLifeTimer.cancel()
                self.loginSuccess()
                self.server.players.append(self.player)
                
                self.setState("g") # Ingame

            elif type == "llb": # Leaderboard
                leaderboard = datastore.getLeaderBoard()
                
                self.sendJSON({"packets": [{"data": leaderboard, "type": "slb"}], "type": "s01"})

            elif type == "llg": #login
                if self.username != "" or self.player is not None or self.pendingStat is None:
                    self.sendClose()
                    return
                self.stopDCTimer()
                
                username = packet["username"].upper()
                if self.address in self.server.loginBlocked:
                    self.sendJSON({"type": "llg", "status": False, "msg": "max login tries reached.\ntry again in one minute."})
                    return
                elif username in self.server.authd:
                    self.sendJSON({"type": "llg", "status": False, "msg": "account already in use"})
                    return

                status, msg = datastore.login(username, packet["password"])

                j = {"type": "llg", "status": status, "msg": msg}
                if status:
                    j["username"] = self.username = username
                    self.session = msg["session"]
                    self.server.authd.append(self.username)
                else:
                    if self.address not in self.server.maxLoginTries:
                        self.server.maxLoginTries[self.address] = 1
                    else:
                        self.server.maxLoginTries[self.address] += 1
                        if self.server.maxLoginTries[self.address] >= 4:
                            del self.server.maxLoginTries[self.address]
                            self.server.loginBlocked.append(self.address)
                            reactor.callLater(60, self.server.loginBlocked.remove, self.address)
                self.sendJSON(j)

            elif type == "llo": #logout
                if self.username == "" or self.player is not None or self.pendingStat is None:
                    self.sendClose()
                    return
                
                datastore.logout(self.session)
                self.sendJSON({"type": "llo"})

            elif type == "lrg": # Register
                if self.username != "" or self.address not in self.server.captchas or self.player is not None or self.pendingStat is None:
                    self.sendClose()
                    return
                self.stopDCTimer()
                
                username = packet["username"].upper()
                if CP_IMPORT and len(packet["captcha"]) != 5:
                    status, msg = False, "invalid captcha"
                elif CP_IMPORT and packet["captcha"].upper() != self.server.captchas[self.address]:
                    status, msg = False, "incorrect captcha"
                elif self.server.checkCurse(username):
                    status, msg = False, "please choose a different username"
                else:
                    status, msg = datastore.register(username, packet["password"])

                if status:
                    del self.server.captchas[self.address]
                    self.username = username
                    self.session = msg["session"]
                    self.server.authd.append(self.username)
                self.sendJSON({"type": "lrg", "status": status, "msg": msg})

            elif type == "lrg": #register
                if self.username != "" or self.address not in self.server.captchas or self.player is not None or self.pendingStat is None:
                    self.sendClose2()
                    return
                self.stopDCTimer()
                
                username = packet["username"].upper()
                if CP_IMPORT and len(packet["captcha"]) != 5:
                    status, msg = False, "invalid captcha"
                elif CP_IMPORT and packet["captcha"].upper() != self.server.captchas[self.address]:
                    status, msg = False, "incorrect captcha"
                elif util.checkCurse(username):
                    status, msg = False, "please choose a different username"
                else:
                    status, msg, self.accountPriv = datastore.register(self.dbSession, username, packet["password"])

                if status:
                    del self.server.captchas[self.address]
                    self.account = msg
                    self.username = username
                    self.session = msg["session"]
                    self.server.authd.append(self.username)
                self.sendJSON({"type": "lrg", "status": status, "msg": msg})

            elif type == "lrc": #request captcha
                if self.username != "" or self.player is not None or self.pendingStat is None:
                    self.sendClose()
                    return
                if not CP_IMPORT:
                    self.server.captchas[self.address] = ""
                    self.sendJSON({"type": "lrc", "data": ""})
                    return
                self.stopDCTimer()

                cp = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(5))
                self.server.captchas[self.address] = cp
                
                imageCaptcha = ImageCaptcha()
                image = imageCaptcha.generate_image(cp)
                
                imgByteArr = BytesIO()
                image.save(imgByteArr, format='PNG')
                imgByteArr = imgByteArr.getvalue()
                
                self.sendJSON({"type": "lrc", "data": base64.b64encode(imgByteArr).decode("utf-8")})
                

            elif type == "lrs": #resume session
                if self.username != "" or self.player is not None or self.pendingStat is None:
                    self.sendClose()
                    return
                self.stopDCTimer()
                
                status, msg = datastore.resumeSession(packet["session"])

                j = {"type": "lrs", "status": status, "msg": msg}
                if status:
                    if msg["username"] in self.server.authd:
                        self.sendJSON({"type": "lrs", "status": False, "msg": "account already in use"})
                        return
                    j["username"] = self.username = msg["username"]
                    self.session = msg["session"]
                    self.server.authd.append(self.username)
                self.sendJSON(j)

            elif type == "lpr": #update profile
                if self.username == "" or self.player is not None or self.pendingStat is None:
                    self.sendClose()
                    return
                
                datastore.updateAccount(self.username, packet)

            elif type == "lgs": #get skins
                if self.username == "" or self.player is not None or self.pendingStat is None:
                    self.sendClose()
                    return

                j = {"type": "lgs", "skins": shop.getSkins()}
                self.sendJSON(j)

            elif type == "lbs": #buy skin
                if self.username == "" or self.player is not None or self.pendingStat is None:
                    self.sendClose()
                    return

                pendingSkin = shop.getSkinID(packet["skin"])
                account = datastore.getAccountData(self.username)
                if pendingSkin is not None:
                    if account["coins"] < pendingSkin["coins"]:
                        j = {"type": "lbs", "success": False, "message": "Not enough coins for this skin."}
                        self.sendJSON(j)
                        return

                    if pendingSkin["id"] in account["skins"]:
                        j = {"type": "lbs", "success": False, "message": "You already have this skin."}
                        self.sendJSON(j)
                        return

                    datastore.purchaseSkin(self.username, pendingSkin)

                    j = {"type": "lbs", "coins": account["coins"], "skins": account["skins"], "success": True, "message": "Successfully purchased {skn}".format(skn=pendingSkin["name"])}
                    self.sendJSON(j)
                else:
                    self.sendClose()

            elif type == "lpc": #password change
                if self.username == "" or self.player is not None or self.pendingStat is None:
                    self.sendClose()
                    return

                datastore.changePassword(self.username, packet["password"])

        elif self.stat == "g":
            if type == "g00": # Ingame state ready
                if self.player is None or self.pendingStat is None:
                    if self.server.shuttingDown:
                        levelName, levelData = self.server.getRandomLevel("maintenance", None)
                        self.sendJSON({"packets": [{"game": levelName, "levelData": json.dumps(levelData), "type": "g01"}], "type": "s01"})
                        return
                    if self.blocked:
                        levelName, levelData = self.server.getRandomLevel("jail", None)
                        self.sendJSON({"packets": [{"game": levelName, "levelData": json.dumps(levelData), "type": "g01"}], "type": "s01"})
                        return
                    self.sendClose2()
                    return
                self.pendingStat = None
                
                self.player.onEnterIngame()

            elif type == "g03": # World load completed
                if self.player is None:
                    if self.blocked or self.server.shuttingDown:
                        self.sendBin(0x02, Buffer().writeInt16(0).writeInt16(0).writeInt8(0))
                        #self.startDCTimer(15)
                        return
                    self.sendClose2()
                    return
                self.player.onLoadComplete()

            elif type == "g50": # Vote to start
                if self.player is None or self.player.voted or self.player.match.playing:
                    return
                
                self.player.voted = True
                self.player.match.voteStart()

            elif type == "g51": # (SPECIAL) Force start 
                if not self.player.isDev:
                    self.sendClose2()
                self.player.match.start(True)

            elif type == "gsm":  # Send Message
                msg = packet["message"].strip()
                if len(msg) == 0 or len(msg) > 100 or self.player is None or len(self.username) == 0:
                    return

                #self.player.match.broadJSON({"type": "gsm", "name": self.player.name, "message": msg, "global": 1})
                if packet["global"] == True:
                    self.player.match.sendMessage(self.player, msg)
                else:
                    self.player.match.sendSquadMessage(self.player, msg)
                    
            
            elif type == "gsl":  # Level select
                if self.player is None or ((not self.server.enableLevelSelectInMultiPrivate and self.player.team != "") or not self.player.match.private) and not self.player.isDev:
                    return
                
                levelName = packet["name"]
                if levelName == "custom":
                    try:
                        self.player.match.selectCustomLevel(packet["data"])
                    except Exception as e:
                        estr = str(e)
                        estr = "\n".join(estr.split("\n")[:10])
                        self.sendJSON({"type":"gsl","name":levelName,"status":"error","message":estr})
                        return
                    
                    self.sendJSON({"type":"gsl","name":levelName,"status":"success","message":""})
                else:
                    self.player.match.selectLevel(levelName)
            elif type == "gbn":  # ban player
                if not self.player.isDev:
                    self.sendClose2()
                pid = packet["pid"]
                ban = packet["ban"]
                self.player.match.banPlayer(pid, ban)
            elif type == "gnm":  # rename player
                if not self.player.isDev:
                    self.sendClose2()
                pid = packet["pid"]
                newName = packet["name"]
                self.player.match.renamePlayer(pid, newName)
        
        else:
            print("unknown message! "+payload)


    def onBinaryMessage(self):
        pktLenDict = { 0x10: 6, 0x11: 0, 0x12: 12, 0x13: 1, 0x17: 2, 0x18: 4, 0x19: 0, 0x20: 7, 0x30: 7 }

        code = self.recv[0]
        if code not in pktLenDict:
            #print("Unknown binary message received: {1} = {0}".format(repr(self.recv[1:]), hex(code)))
            self.recv.clear()
            return False
            
        pktLen = pktLenDict[code] + 1
        if len(self.recv) < pktLen:
            return False
        
        b = Buffer(self.recv[1:pktLen])
        del self.recv[:pktLen]
        
        if self.player is None or not self.player.loaded or self.blocked or (not self.player.match.closed and self.player.match.playing):
            self.recv.clear()
            return False
        
        self.player.handlePkt(code, b, b.toBytes())
        return True

class MyServerFactory(WebSocketServerFactory):

    def __init__(self, url):
        self.configFilePath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.cfg")
        self.blockedFilePath = os.path.join(os.path.dirname(os.path.abspath(__file__)),"database/blocked.json")
        self.levelsPath = os.path.join(os.path.dirname(os.path.abspath(__file__)),"levels")
        self.shutdownFilePath = os.path.join(os.path.dirname(os.path.abspath(__file__)),"shutdown")
        if not os.path.isdir(self.levelsPath):
            self.levelsPath = ""
        self.fileHash = {}
        self.levels = {}
        self.ownLevels = False
        self.shuttingDown = False
        if not self.tryReloadFile(self.configFilePath, self.readConfig):
            sys.stderr.write("The file \"server.cfg\" does not exist or is invalid, consider renaming \"server.cfg.example\" to \"server.cfg\".\n")
            if os.name == 'nt': # Enforce that the window opens in windows
                print("Press ENTER to exit")
                input()
            exit(1)
        if self.levelsPath:
            self.ownLevels = True
            self.reloadLevels()

        WebSocketServerFactory.__init__(self, url.format(self.listenPort))

        self.players = list()
        self.matches = list()

        self.curse = list()
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "words.json"), "r") as f:
                self.curse = json.loads(f.read())
        except:
            pass
        
        self.blocked = list()
        try:
            with open(self.blockedFilePath, "r") as f:
                self.blocked = json.loads(f.read())
        except:
            pass

        if DWH_IMPORT:
            self.discordWebhook = DiscordWebhook(url=self.discordWebhookUrl)
            self.blockedWebhook = DiscordWebhook(url=self.blockedWebhookUrl)
        else:
            self.discordWebhook = None
            self.blockedWebhook = None

        self.randomWorldList = dict()

        self.maxLoginTries = {}
        self.loginBlocked = []
        self.captchas = {}
        self.authd = []

        self.in_messages = 0
        self.out_messages = 0

        reactor.callLater(5, self.generalUpdate)

        #l = task.LoopingCall(self.updateLeaderBoard)
        #l.start(10.0)

    def updateLeaderBoard(self):
        if self.leaderBoardPath != '':
            leaderBoard = datastore.getLeaderBoard()
            with open(self.leaderBoardPath, "w") as f:
                f.write(json.dumps(leaderBoard))

    def reloadLevel(self, level):
        fullPath = os.path.join(self.levelsPath, level)
        try:
            with open(fullPath, "r", encoding="utf-8-sig") as f:
                content = f.read()
                lk = json.loads(content)
                util.validateLevel(lk)
                lk["mtime"] = os.stat(fullPath).st_mtime
                isNew = not level in self.levels
                self.levels[level] = lk
                print(level+" "+ ("loaded" if isNew else "reloaded") +".")
        except:
            print("error while loading "+level+":")
            raise


    def reloadLevels(self):
        files = os.listdir(self.levelsPath)
        files.sort()
        deletedLevels = set(self.levels.keys())-set(files)
        for f in deletedLevels:
            del self.levels[f]
            print(f+" deleted")
        newLevels = set(files)-set(self.levels.keys())
        for f in self.levels.keys(): #we do this first so levels only contains the still-existing levels
            oldMt = self.levels[f]["mtime"]
            newMt = os.stat(os.path.join(self.levelsPath, f)).st_mtime
            if (newMt>oldMt):
                self.reloadLevel(f)
        for f in newLevels:
            self.reloadLevel(f)

    def tryReloadFile(self, fn, callback):
        try:
            with open(fn, "r") as f:
                cfgHash = hashlib.md5(f.read().encode('utf-8')).hexdigest()
                if not fn in self.fileHash or cfgHash != self.fileHash[fn]:
                    self.fileHash[fn] = cfgHash
                    callback()
                    print(fn+" loaded.")
            return True
        except Exception as e:
            print("Failed to load "+fn)
            traceback.print_exc()
            return False

    def readConfig(self):
        config = configparser.ConfigParser()
        config.read('server.cfg')

        self.listenPort = config.getint('Server', 'ListenPort')
        self.mcode = config.get('Server', 'MCode').strip()
        self.statusPath = config.get('Server', 'StatusPath').strip()
        self.leaderBoardPath = config.get('Server', 'LeaderboardPath', fallback='').strip()
        self.defaultName = config.get('Server', 'DefaultName').strip()
        self.defaultTeam = config.get('Server', 'DefaultTeam').strip()
        self.maxSimulIP = config.getint('Server', 'MaxSimulIP')
        self.skinCount = config.getint('Server', 'SkinCount')
        self.discordWebhookUrl = config.get('Server', 'DiscordWebhookUrl').strip()
        self.blockedWebhookUrl = config.get('Server', 'BlockedWebhookUrl').strip()

        self.playerMin = config.getint('Match', 'PlayerMin')
        try:
            oldCap = self.playerCap
        except:
            oldCap = 0
        self.playerCap = config.getint('Match', 'PlayerCap')
        if self.playerCap < oldCap:
            try:
                for match in self.matches:
                    if len(match.players) >= self.playerCap:
                        match.start()
            except:
                print("Couldn't start matches after player cap change...")
        self.autoStartTime = config.getint('Match', 'AutoStartTime')
        self.startTimer = config.getint('Match', 'StartTimer')
        self.enableAutoStartInMultiPrivate = config.getboolean('Match', 'EnableAutoStartInMultiPrivate')
        self.enableLevelSelectInMultiPrivate = config.getboolean('Match', 'EnableLevelSelectInMultiPrivate')
        self.enableVoteStart = config.getboolean('Match', 'EnableVoteStart')
        self.voteRateToStart = config.getfloat('Match', 'VoteRateToStart')
        self.allowLateEnter = config.getboolean('Match', 'AllowLateEnter')
        if not self.levelsPath:
            self.worlds = config.get('Match', 'Worlds').strip().split(',')
            self.worldsPvP = config.get('Match', 'WorldsPVP').strip()
            if len(self.worldsPvP) == 0:
                self.worldsPvP = list(self.worlds)
            else:
                self.worldsPvP = self.worldsPvP.split(',')
            self.worldsHell = config.get('Match', 'WorldsHell').strip()
            if len(self.worldsHell) == 0:
                self.worldsHell = list(self.worlds)
            else:
                self.worldsHell = self.worldsHell.split(',')

    def generalUpdate(self):
        playerCount = len(self.players)

        if LOG_ENABLED:
            print("players: {0}, matches: {1}, in: {2}, out: {3}".format(playerCount, len(self.matches), self.in_messages, self.out_messages))
        self.in_messages = 0
        self.out_messages = 0

        self.updateLeaderBoard()

        self.tryReloadFile(self.configFilePath, self.readConfig)
        # Just to keep self.blocked synchronized with blocked.json
        try:
            with open(self.blockedFilePath, "r") as f:
                self.blocked = json.loads(f.read())
        except:
            pass

        if self.levelsPath:
            try:
                self.reloadLevels()
            except:
                traceback.print_exc()

        if os.path.exists(self.shutdownFilePath):
            self.shuttingDown = True
            print("shutting down...")
            os.remove(self.shutdownFilePath)
            for player in self.players:
                player.hurryUp(180)
            reactor.callLater(240, self.shutdown)

        if self.statusPath:
            try:
                with open(self.statusPath, "w") as f:
                    f.write(json.dumps({"active":playerCount, "maintenance":self.shuttingDown}))
            except:
                pass

        if self.shuttingDown and playerCount == 0:
            reactor.stop()

        reactor.callLater(5, self.generalUpdate)

    def shutdown(self):
        reactor.stop()

    def leet2(self, word):
        REPLACE = { str(index): str(letter) for index, letter in enumerate('oizeasgtb') }
        letters = [ REPLACE.get(l, l) for l in word.lower() ]
        return ''.join(letters)

    def checkCurse(self, str):
        if self.checkCheckCurse(str):
            return True
        str = self.leet2(str)
        if self.checkCheckCurse(str):
            return True
        str = str.replace("|", "i").replace("$", "s").replace("@", "a").replace("&", "e")
        str = ''.join(e for e in str if e.isalnum())
        if self.checkCheckCurse(str):
            return True
        return False

    def checkCheckCurse(self, str):
        if len(str) <= 3:
            return False
        str = str.lower()
        for w in self.curse:
            if len(w) <= 3:
                continue
            if w in str:
                return True
        return False

    def blockAddress(self, address, playerName, reason):
        if not address in self.blocked:
            self.blocked.append([address, playerName, reason])
            try:
                with open(self.blockedFilePath, "w") as f:
                    f.write(json.dumps(self.blocked))
            except:
                pass

    def getPlayerCountByAddress(self, address):
        count = 0
        for player in self.players:
            if player.client.address == address:
                count += 1
        return count

    def buildProtocol(self, addr):
        protocol = MyServerProtocol(self)
        protocol.factory = self
        return protocol

    def getMatch(self, roomName, private, gameMode):
        if private and roomName == "":
            return Match(self, roomName, private, gameMode)
        
        fmatch = None
        for match in self.matches:
            if not match.closed and len(match.players) < self.playerCap and gameMode == match.gameMode and private == match.private and (not private or match.roomName == roomName):
                if not self.allowLateEnter and match.playing:
                    continue
                fmatch = match
                break

        if fmatch == None:
            fmatch = Match(self, roomName, private, gameMode)
            self.matches.append(fmatch)

        return fmatch

    def removeMatch(self, match):
        if match in self.matches:
            self.matches.remove(match)
                

    def getLevel(self, level):
        if not self.ownLevels:
            return (level, "")
        else:
            return ("custom", self.levels[level])

    def getLevelList(self, type, mode):
        possibleLevels = [x for x in self.levels if self.levels[x]["type"] == type]
        if mode is not None:
            possibleLevels = [x for x in possibleLevels if self.levels[x]["mode"] == mode]
        if len(possibleLevels) == 0:
            raise Exception("no levels match type: {} mode: {}".format(type, mode))
        return possibleLevels

    def getRandomLevel(self, type, mode):
        if not self.ownLevels:
            if type == "lobby":
                return ("lobby", "")
            elif type == "jail":
                return ("jail", "")
            elif type == "game":
                if mode == "royale":
                    return (random.choice(self.worlds), "")
                elif mode == "pvp":
                    return (random.choice(self.worldsPVP), "")
                elif mode == "hell":
                    return (random.choice(self.worldsHell), "")
                else:
                    raise Exception("unknown game mode: "+mode)
            else:
                raise Exception("unknown level type: "+type)
        possibleLevels = self.getLevelList(type, mode)
        chosenLevel = random.choice(possibleLevels)
        return ("custom", self.levels[chosenLevel])

if __name__ == '__main__':
    contextFactory = ssl.DefaultOpenSSLContextFactory('ssl/privkey.pem','ssl/cert.pem')

    factory = MyServerFactory(u"ws://127.0.0.1:{0}/royale/ws")
    factory.setProtocolOptions(autoPingInterval=5, autoPingTimeout=5)

    reactor.listenTCP(factory.listenPort, factory, contextFactory)
    reactor.run()
