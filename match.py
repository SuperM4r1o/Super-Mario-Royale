from twisted.internet import reactor, task
from buffer import Buffer
import os
import json
import random
import util
import copy
from profanity import has_profanity, censor_profanity, get_profanity

try:
    from discord_webhook import DiscordEmbed, DiscordWebhook
except Exception as e:
    pass

class Match(object):
    def __init__(self, server, roomName, private, gameMode):
        self.server = server

        self.forceLevel = ""
        self.customLevelData = {}
        self.isLobby = True
        self.world = "lobby"
        self.roomName = roomName
        self.closed = False
        self.startedMsg = False
        self.private = private
        self.gameMode = gameMode
        self.levelMode = self.gameMode
        self.playing = False
        self.usingCustomLevel = False
        self.autoStartOn = not self.private or (self.roomName != "" and self.server.enableAutoStartInMultiPrivate)
        self.autoStartTimer = None
        self.autoStartTicks = 0
        self.tickTimer = None
        self.startTimer = int()
        self.votes = int()
        self.winners = int()
        self.lastId = -1
        self.players = list()
        self.getRandomLevel("lobby", None)
        self.instantiateLevel()
        self.initLevel()

    def getRandomLevel(self, type, mode):
        self.world, self.customLevelData = self.server.getRandomLevel(type, mode)

    def getLevel(self, level):
        if not self.usingCustomLevel:
            self.world, self.customLevelData = self.server.getLevel(level)

    def getNextPlayerId(self):
        self.lastId += 1
        return self.lastId

    def addPlayer(self, player):
        self.players.append(player)
        self.broadJSON({"type": "gsm", "message": player.name + " joined the game.", "global": 1, "warn": 3})
        return self.getNextPlayerId()

    def removePlayer(self, player):
        if player not in self.players:
            return
        self.players.remove(player)
        
        if len(self.players) == 0:
            try:
                self.autoStartTimer.cancel()
            except:
                pass
            self.server.removeMatch(self)
            return
        
        if not player.dead and not player.win: # Don't kill podium players
            self.broadBin(0x11, Buffer().writeInt16(player.id)) # KILL_PLAYER_OBJECT

        self.broadPlayerList()

        if player.voted:
            self.votes -= 1
        elif self.server.enableVoteStart and not self.playing and self.votes >= len(self.players) * self.server.voteRateToStart:
            self.start()

    def getPlayer(self, pid):
        for player in self.players:
            if player.id == pid:
                return player
        return None

    def getPlayerName(self, name):
        for player in self.players:
            if player.name.lower() == name.lower():
                return player
        return None
            
    def getWinners(self):
        self.winners += 1
        return self.winners

    def broadJSON(self, j):
        for player in self.players:
            if not player.loaded:
                continue
            player.sendJSON(j)

    def broadBin(self, code, buff, ignore = None):
        buff = buff.toBytes() if isinstance(buff, Buffer) else buff
        for player in self.players:
            if not player.loaded or (ignore is not None and player.id == ignore):
                continue
            player.sendBin(code, buff)

    def getLoadMsg(self):
        msg = {"game": self.world, "type": "g01"}
        if self.world == "custom":
            msg["levelData"] = json.dumps(self.level)
        j = {"packets": [msg], "type": "s01"}
        return json.dumps(j).encode('utf-8')

    def broadLoadWorld(self):
        msg = self.getLoadMsg() #only serialize once!
        for player in self.players:
            player.loadWorld(self.world, msg)

    def broadTick(self):
        self.broadJSON({"type":"gtk", "ticks":self.autoStartTicks, "votes":self.votes, "minPlayers":self.server.playerMin, "maxPlayers":self.server.playerCap,
            "voteRateToStart":self.server.voteRateToStart})

    def broadStartTimer(self, time):
        self.startTimer = time * 30
        for player in self.players:
            if not player.loaded:
                continue
            player.setStartTimer(self.startTimer)
        
        if time > 0:
            reactor.callLater(1, self.broadStartTimer, time - 1)
        else:
            self.closed = True

    def broadPlayerList(self):
        devOnly = self.playing   # Don't broad player list when in main game
        playersData = self.getPlayersData(False);
        playersDataDev = self.getPlayersData(True);
        data = {"packets": [
            {"players": playersData,
             "type": "g12"}
        ], "type": "s01"}
        dataDev = {"packets": [
            {"players": playersDataDev,
             "type": "g12"}
        ], "type": "s01"}
        for player in self.players:
            if player.isDev or not devOnly:
                if not player.loaded:
                    continue
                player.sendJSON(data if not player.isDev else dataDev)

    def getPlayersData(self, isDev):
        playersData = []
        for player in self.players:
            # We need to include even not loaded players as the remaining player count
            # only updates on the start timer screen
            playersData.append(player.getSimpleData(isDev))
        return playersData

    def broadPlayerUpdate(self, player, pktData):
        data = Buffer().writeInt16(player.id).write(pktData).toBytes()
        for p in self.players:
            if not p.loaded or p.id == player.id:
                continue
            if not p.win and (p.level != player.level or p.zone != player.zone):
                continue
            p.sendBin(0x12, data)

    def onPlayerEnter(self, player):
        pass

    def onPlayerReady(self, player):
        if self.autoStartOn and not self.playing: # Ensure that the game starts even with fewer players
            if self.autoStartTimer is not None:
                try:
                    self.autoStartTimer.reset(self.server.autoStartTime)
                except:
                    pass
            else:
                self.autoStartTimer = reactor.callLater(self.server.autoStartTime, self.start, True)
            self.autoStartTicks = self.server.autoStartTime

        if self.tickTimer is None:
            self.tickTimer = task.LoopingCall(self.tick)
            self.tickTimer.start(1.0)

        if self.gameMode == "pvp":
            if len(self.players) < 2:
                try:
                    self.tickTimer.stop()
                    self.tickTimer = 0
                except AttributeError:
                    print("AttributeError: self.tickTimer.stop()")
            else:
                self.tickTimer = task.LoopingCall(self.tick)
                self.tickTimer.start(1.0)

        if self.isLobby or not player.lobbier or self.closed:
            for p in self.players:
                if not p.loaded or p == player:
                    continue
                player.sendBin(0x10, p.serializePlayerObject())
            if self.startTimer != 0 or self.closed:
                player.setStartTimer(self.startTimer)
        self.broadPlayerList()

        if not self.playing:
            if len(self.players) >= self.server.playerCap:
                self.start(True)
            # This is needed because if the votes is sufficient to start but there isn't sufficient players,
            # when someone enters the game, it can make it possible to start the game.
            elif self.server.enableVoteStart and self.votes >= len(self.players) * self.server.voteRateToStart:
                self.start()

    def onPlayerWarp(self, player, level, zone):
        for p in self.players:
            if not p.loaded or p.lastUpdatePkt is None or p.id == player.id:
                continue
            # Tell fellows that the player warped
            if p.level == player.level and p.zone == player.zone:
                p.sendBin(0x12, Buffer().writeInt16(player.id).writeInt8(level).writeInt8(zone).write(player.lastUpdatePkt[2:]))
                continue
            elif p.level != level or p.zone != zone:
                continue
            player.sendBin(0x12, Buffer().writeInt16(p.id).write(p.lastUpdatePkt))

    def voteStart(self):
        self.votes += 1
        if self.server.enableVoteStart and not self.playing and self.votes >= len(self.players) * self.server.voteRateToStart:
            self.start()

    def start(self, forced = False):
        if self.playing or (not forced and len(self.players) < (1 if self.private and self.roomName == "" else self.server.playerMin)): # We need at-least 10 players to start
            return
        self.playing = True
        self.isLobby = False
        
        try:
            self.autoStartTimer.cancel()
        except:
            pass
        if self.tickTimer is not None:
            self.tickTimer.stop()
            self.tickTimer = None

        if self.forceLevel != "":
            self.getLevel(self.forceLevel)
        else:
            self.getRandomLevel("game", self.levelMode)

        #if not self.private:   #what's the reason for this? it makes players appear frozen mid-air for 3 seconds and keeps being reported as a bug
        #    reactor.callLater(3, self.broadLoadWorld)
        #    reactor.callLater(4, self.broadStartTimer, self.server.startTimer)
        #else:
        self.instantiateLevel()
        if (not self.private and self.gameMode == "royale"):
            self.addGoldFlower()
        self.broadLoadWorld()
        self.initLevel()
        reactor.callLater(1, self.broadStartTimer, self.server.startTimer)

    def instantiateLevel(self):
        self.level = copy.deepcopy(self.customLevelData)
        def fixLayersZ(x):
            if "data" in x:
                x["layers"]=[{"z":0, "data":x["data"]}]
                del x["data"]
        def fixLayersW(x):
            [fixLayersZ(z) for z in x["zone"]]
        [fixLayersW(w) for w in self.level["world"]]

    def addGoldFlower(self):
        b = self.level
        def g(a,b,c,x):
            res = []
            for i, e in enumerate(x):
                for j, ee in enumerate(e):
                    if ((ee>>16)&0xff) == 18:
                        res.append((a,b,c,i,j))
            return res
        raze = lambda x:[item for sublist in x for item in sublist]
        f = lambda a,b,x:[[] if l["z"]!=0 else g(a,b,i,l["data"]) for i,l in enumerate(x)]
        c = [[f(x["id"],y["id"],y["layers"]) for y in x["zone"]] for x in b["world"]]
        e = raze(raze(raze(c)))
        if len(e)==0:
            return
        target = random.choice(e)
        v = b["world"][target[0]]["zone"][target[1]]["layers"][target[2]]["data"][target[3]][target[4]]
        v = (v&0xffff) | (100 << 24) | (17 << 16)
        self.level["world"][target[0]]["zone"][target[1]]["layers"][target[2]]["data"][target[3]][target[4]]=v

    def initLevel(self):
        self.initObjects()

    def extractMainLayer(self, zone):
        if "data" in zone:
            return zone["data"]
        elif "layers" in zone:
            mainLayers = [x for x in zone["layers"] if x["z"] == 0]
            if len(mainLayers) != 1:
                raise Exception("invalid level - should have exactly one layer at depth 0")
            return mainLayers[0]["data"]
        else:
            raise Exception("invalid level - neither data or layers present")

    def initObjects(self):
        self.objects = [(lambda x:[(lambda x:{x["pos"]:x["type"] for x in x["obj"]})(x) for x in x["zone"]])(x) for x in self.level["world"]]
        self.allcoins = [(lambda x:[(lambda x:[y for y in x if x[y]==97])(x) for x in x])(x) for x in self.objects]
        self.tiles = [(lambda x:[self.extractMainLayer(x) for x in x["zone"]])(x) for x in self.level["world"]]
        self.zoneHeight = [[len(y) for y in x] for x in self.tiles]
        self.zoneWidth = [[len(y[0]) for y in x] for x in self.tiles]
        self.coins = copy.deepcopy(self.allcoins)
        self.powerups = {}

    def validateCustomLevel(self, level):
        lk = json.loads(level)
        util.validateLevel(lk)
        return lk

    def selectLevel(self, level):
        if level == "" or level in self.server.levels:
            self.forceLevel = level
            self.usingCustomLevel = False
            self.broadLevelSelect()

    def broadLevelSelect(self):
        data = {"type":"gsl", "name":self.forceLevel, "status":"update", "message":""}
        for player in self.players:
            player.sendJSON(data)

    def selectCustomLevel(self, level):
        lk = self.validateCustomLevel(level)
        self.usingCustomLevel = True
        self.forceLevel = "custom"
        self.customLevelData = lk
        self.broadLevelSelect()

    def objectEventTrigger(self, player, b, pktData):
        level, zone, oid, type = b.readInt8(), b.readInt8(), b.readInt32(), b.readInt8()
        allcoins = self.allcoins[level][zone]
        if oid in allcoins:
            player.addCoin()
            coins = self.coins[level][zone]
            if not oid in coins:
                return
            
            coins.remove(oid)
        if oid in self.powerups:
            powerup = self.powerups[oid]
            if powerup["type"] == 100:
                player.addLeaderBoardCoins(500)
            del self.powerups[oid]

        self.broadBin(0x20, Buffer().writeInt16(player.id).write(pktData))

    def getTile(self, level, zone, x, y):
        if x<0 or y<0 or x>=self.zoneWidth[level][zone] or y>=self.zoneHeight[level][zone]:
            return 30
        return self.tiles[level][zone][self.zoneHeight[level][zone]-1-y][x]

    def tileEventTrigger(self, player, b, pktData):

        level, zone, pos, type = b.readInt8(), b.readInt8(), b.readShor2(), b.readInt8()
        x = pos[0]
        y0 = pos[1]
        y = self.zoneHeight[level][zone]-1-y0
        tile = self.tiles[level][zone][y][x]
        id = (tile>>16)&0xff
        extraData = (tile>>24)&0xff
        if id==18 or id==22:    #normal and hidden coin blocks
            player.addCoin()
            self.tiles[level][zone][y][x] = 98331
        elif id==17:    #normal item block
            oid = x|(y0<<16)    #erroneously(?) uses y0 instead of y
            self.powerups[oid] = {"id":oid, "type": extraData}
            self.tiles[level][zone][y][x] = 98331
        elif id==19:    #multi-coin block
            if extraData > 1:
                player.addCoin()
                self.tiles[level][zone][y][x] = (tile&0xffffff)|((extraData-1)<<24)
            else:
                if extraData == 1:
                    player.addCoin()
                self.tiles[level][zone][y][x] = 98331

        self.broadBin(0x30, Buffer().writeInt16(player.id).write(pktData))

    def banPlayer(self, pid, ban):
        player = self.getPlayer(pid)
        if player is None:
            return
        player.ban(ban)

    def renamePlayer(self, pid, newName):
        player = self.getPlayer(pid)
        if player is None:
            return
        player.rename(newName)
        self.broadJSON({"type":"gnm", "pid":pid, "name":newName})

    def hurryUp(self, time):
        for player in self.players:
            player.hurryUp(time)

    def tick(self):
        if (self.autoStartOn):
            self.autoStartTicks -= 1
        self.broadTick()

    def sendMessage(self, player, message):
        if player.muted and not player.isDev and not player.isMod:
            self.sendMutedMessage(player, 1)
            return

        if player.strikes >= 5 and not player.isDev and not player.isMod:
            self.strikeMessage(player, 1)
            return

        if has_profanity(message) and not player.isDev and not player.isMod:
            message = censor_profanity(message)
            print(len(get_profanity(message, True)))
            if len(get_profanity(message, True)) >= 3:
                self.sendWarningMessage(player, 1)

        self.broadJSON({"type": "gsm", "name": player.name, "message": message, "global": 1, "warn": 0, "mod": player.isMod, "dev": player.isDev})
        if player.isDev or player.isMod:
            self.commandHandler(player, message)

    def sendSquadMessage(self, player, message):
        if player.muted and not player.isDev and not player.isMod:
            self.sendMutedMessage(player, 0)
            return

        if player.strikes >= 5 and not player.isDev and not player.isMod:
            self.strikeMessage(player, 0)
            return

        if has_profanity(message) and not player.isDev and not player.isMod:
            message = censor_profanity(message)
            if len(get_profanity(message, True)) >= 3:
                self.sendWarningMessage(player, 0)

        for p in self.players:
            if not p.loaded or p.team != player.team:
                continue
            p.sendJSON({"type": "gsm", "name": player.name, "message": message, "global": 0, "warn": 0, "mod": player.isMod, "dev": player.isDev})

    def sendWarningMessage(self, player, public):
        if player.strikes >= 5:
            self.strikeMessage(player, public)
            return

        self.strike(player)
        player.sendJSON({"type": "gsm", "message": "[WARNING] " + player.name + ", your message contains a blocked word! You have: " + str(player.strikes) + "/5 strikes.", "global": public, "warn": 1, "tag": 0})

    def strikeMessage(self, player, public):
        if player.strikes >= 5:
            player.sendJSON({"type": "gsm", "message": "[ERROR] " + player.name + ", you have too many strikes! You are unable to send messages anymore.", "global": public, "warn": 2, "tag": 0})
    
    def sendMutedMessage(self, player, public):
        if player.muted:
            player.sendJSON({"type": "gsm", "message": "[ERROR] " + player.name + ", you are muted, contact a mod on our Discord if you believe this is a mistake.", "global": public, "warn": 2, "tag": 0})
    
    def sendDisconnectMessage(self, player):
        self.broadJSON({"type": "gsm", "message": player.name + " left the game. ({msg})".format(msg=player.disconnectMessage), "global": 1, "warn": 1})

    def announceWinMessage(self, player, pos):
        self.broadJSON({"type": "gsm", "message": player.name + " achieved #" + str(pos) + " Victory Royale!", "global": 1, "warn": 4})

    def killMessage(self, player, killer, type):
        if type < 0:
            return

        feedMessages = [
            "{participant} was star-struck by {opponent}'s super star!",
            "{participant} got fired by {opponent}'s fire flower!",
            "{participant} got shell-shocked by {opponent}!"
            "{opponent} killed {participant}!"
        ]

        type = 3
        #message = feedMessages[type].format(participant=player.name, opponent=killer.name)
        message = "{opponent} killed {participant}".format(participant=player.name, opponent=killer.name)
        self.broadJSON({"type": "gsm", "message": message, "global": 1, "warn": 3})        

    def strike(self, player):
        player.strikes += 1
        if player.strikes >= 5:
            player.muted = True
            if self.server.blockedWebhook is not None:
                embed = DiscordEmbed(title="Player Striked Out", color=0x267B8B)
                embed.add_embed_field(name="Player Name", value=player.name, inline=True)
                embed.add_embed_field(name="Strike Count", value=player.strikes, inline=True)
                
                self.server.blockedWebhook.add_embed(embed)
                self.server.blockedWebhook.execute()
                self.server.blockedWebhook.remove_embed(0)


    def commandHandler(self, player, message):
        args = message.split(" ", 1)
        if args[0] == "/kick":
            p = self.getPlayerName(args[1])
            if p is not None:
                p.disconnectMessage = "Kicked by moderator"
                p.client.sendClose()
                self.broadJSON({"type": "gsm", "message": "[MOD] Successfully kicked " + p.name, "global": 1, "warn": 3, "tag": 0})

                if self.server.blockedWebhook is not None:
                    embed = DiscordEmbed(title="Player Kicked", color=0x267B8B)
                    embed.add_embed_field(name="Player", value=p.name, inline=True)
                    embed.add_embed_field(name="Moderator", value=player.name, inline=True)
                
                    self.server.blockedWebhook.add_embed(embed)
                    self.server.blockedWebhook.execute()
                    self.server.blockedWebhook.remove_embed(0)
            else:
                self.broadJSON({"type": "gsm", "message": "[MOD] Could not kick " + args[1], "global": 1, "warn": 2, "tag": 0})

        elif args[0] == "/mute":
            p = self.getPlayerName(args[1])
            if p is not None:
                p.muted = True
                self.broadJSON({"type": "gsm", "message": "[MOD] Successfully muted " + p.name, "global": 1, "warn": 3, "tag": 0})

                if self.server.blockedWebhook is not None:
                    embed = DiscordEmbed(title="Player Muted", color=0x267B8B)
                    embed.add_embed_field(name="Player", value=p.name, inline=True)
                    embed.add_embed_field(name="Moderator", value=player.name, inline=True)
                
                    self.server.blockedWebhook.add_embed(embed)
                    self.server.blockedWebhook.execute()
                    self.server.blockedWebhook.remove_embed(0)
            else:
                self.broadJSON({"type": "gsm", "message": "[MOD] Could not mute " + args[1], "global": 1, "warn": 2, "tag": 0})

        elif args[0] == "/unmute":
            p = self.getPlayerName(args[1])
            if p is not None:
                p.muted = False
                self.broadJSON({"type": "gsm", "message": "[MOD] Successfully unmuted " + p.name, "global": 1, "warn": 3, "tag": 0})

                if self.server.blockedWebhook is not None:
                    embed = DiscordEmbed(title="Player Unmuted", color=0x267B8B)
                    embed.add_embed_field(name="Player", value=p.name, inline=True)
                    embed.add_embed_field(name="Moderator", value=player.name, inline=True)
                
                    self.server.blockedWebhook.add_embed(embed)
                    self.server.blockedWebhook.execute()
                    self.server.blockedWebhook.remove_embed(0)

            else:
                self.broadJSON({"type": "gsm", "message": "[MOD] Could not unmute " + args[1], "global": 1, "warn": 2, "tag": 0})

        elif args[0] == "/start":
            if not self.startedMsg:
                self.broadJSON({"type": "gsm", "message": "[MOD] " + player.name + " manually started the match", "global": 1, "warn": 3})
            self.start(True)

        elif args[0] == "/stats":
            p = self.getPlayerName(args[1])
            if p is not None:
                if len(p.client.username) == 0:
                    self.broadJSON({"type": "gsm", "message": "[MOD] " + p.name + " does not have an account.", "global": 1, "warn": 1})
                    return

                acc = p.client.account
                result = "{win}x wins, {death}x deaths, {kill}x kills and {coin} coins.".format(win=acc.wins, death=acc.deaths, kill=acc.kills, coin=acc.coins)

                self.broadJSON({"type": "gsm", "message": "[MOD] " + p.name + " has:\n\n" + result, "global": 1, "warn": 1})

        elif args[0] == "/help":
            commands = [
                ["/kick [player]", "Kick a player from the match\n\n"],
                ["/mute [player]", "Mutes a player\n\n"],
                ["/unmute [player]", "Unmutes a player\n\n"],
                ["/start", "Starts the match without having to wait for the timer\n\n"],
                ["/stats [player]", "View the stats of a player, provided they have an account"]
            ]

            msg = ""
            for command in commands:
                msg += "{cmd} :: {desc}".format(cmd=command[0], desc=command[1])

            #self.broadJSON({"type": "gsm", "message": "[MOD] Commands:\n\n/kick [player] :: Kick a player from the match\n\n/mute [player] :: Mutes a player, stopping them from sending messages.\n\n/unmute [player] :: Unmutes a player if already muted.\n\n/start :: When in the lobby, using this command starts the match.", "global": 1, "warn": 1})
            self.broadJSON({"type": "gsm", "message": "[MOD] Commands:\n\n" + msg, "global": 1, "warn": 1})