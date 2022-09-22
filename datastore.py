import os
import hashlib
import traceback
import re
import util
import json
import requests

try:
    import argon2
    A2_IMPORT = True
except:
    # Maybe we can switch to a built-in passwordHasher?
    print("Can't import argon2-cffi, accounts functioning will be disabled.")
    A2_IMPORT = False

import pickle
import secrets

accounts = {}
session = {"passwordrestore": "KXE"}

if A2_IMPORT:
    ph = argon2.PasswordHasher()
else:
    ph = None

def loadState():
    global accounts
    try:
        if os.path.exists("database/server.dat"):
            with open("database/server.dat", "rb") as f:
                accounts = pickle.load(f)
    except Exception as e:
        print(e)

def persistState():
    with open("database/server.dat", "wb") as f:
        pickle.dump(accounts, f)

def resetLeaderboardCoins():
    for i in accounts:
        accounts[i]["coins"] = 0
    print("Reset all coins\n" + str(accounts["TERMINALKADE"]["coins"]))

def die():
    del accounts["CASINI LOOGI"]

def resetOwned():
    for i in accounts:
        accounts[i]["skins"] = [0, 1]
    print("Reset skins (OWNED)")

def register(username, password):
    if ph is None:
        return False, "account system disabled"
    if len(username) < 3:
        return False, "username too short"
    if len(username) > 20:
        return False, "username too long"
    if len(password) < 8:
        return False, "password too short"
    if len(password) > 120:
        return False, "password too long"
    if username in accounts:
        return False, "account already registered"
    
    salt = hashlib.sha256(os.urandom(60)).hexdigest().encode('ascii')
    pwdhash = ph.hash(password.encode('utf-8')+salt)
    
    acc = { "salt": salt,
            "pwdhash": pwdhash,
            "nickname": username,
            "skin": 0,
            "skins": [0, 1],
            "squad": "",
            "coins": 0,
            "wins": 0,
            "deaths": 0,
            "kills": 0,
            "isDev": False,
            "isBanned": False
            }
    if username.lower() in ["terminalkade", "dimension", "casini loogi", "arcadegamer1929"]:
        acc["isDev"] == True
    accounts[username] = acc
    persistState()
    
    acc2 = acc.copy()
    del acc2["salt"]
    del acc2["pwdhash"]
    
    token = secrets.token_urlsafe(32)
    session[token] = username
    acc2["session"] = token
    return True, acc2

def login(username, password):
    if ph is None:
        return False, "account system disabled"
    
    invalidMsg = "invalid user name or password"
    if len(username) < 3:
        return False, invalidMsg
    if len(username) > 20:
        return False, invalidMsg
    if len(password) < 8:
        return False, invalidMsg
    if len(password) > 120:
        return False, invalidMsg
    if username not in accounts:
        return False, invalidMsg
    acc = accounts[username]

    
    try:
        ph.verify(acc["pwdhash"], password.encode('utf-8')+acc["salt"])
    except:
        return False, invalidMsg
    
    if "skins" not in acc:
        acc["skins"] = [0, 1]

    acc2 = acc.copy()
    del acc2["salt"]
    del acc2["pwdhash"]
    
    token = secrets.token_urlsafe(32)
    session[token] = username
    acc2["session"] = token
    return True, acc2

def resumeSession(token):
    if token not in session:
        return False, "session expired, please log in"
    
    username = session[token]
    if username not in accounts:
        return False, "invalid user name or password"
    acc = accounts[username]


    if "skins" not in acc:
        acc["skins"] = [0, 1]
    
    acc2 = acc.copy()
    del acc2["salt"]
    del acc2["pwdhash"]
    
    acc2["username"] = username
    acc2["session"] = token
    return True, acc2

def returnCoins(username):
    if username not in accounts:
        return

    acc = accounts[username]["coins"]
    return acc

def allowedNickname(nickname):
    return not util.checkCurse(nickname)

def updateAccount(username, data):
    if username not in accounts:
        return
    
    acc = accounts[username]
    if "nickname" in data:
        acc["nickname"] = data["nickname"]
    if "squad" in data:
        acc["squad"] = data["squad"]
    if "skin" in data:
        acc["skin"] = data["skin"]
    persistState()

def validateSkin(username, skin):
    if username not in accounts:
        # Simple, if the username doesn't exist, use the guest method of validating skins
        return validateSkinGuest(skin)

    acc = accounts[username]["skins"]

    if skin not in acc:
        return 0
    else:
	    return skin

def validateSkinGuest(skin):
    # Guests cannot use skins with an ID over 1 (Luigi), so if it's higher than that, then return a value of zero, aka default to Mario from the get go
    if skin > 1:
        return 0

    return skin

def purchaseSkin(username, data):
    if username not in accounts:
        return

    acc = accounts[username]
    if data["id"] not in acc["skins"]:
        acc["skins"].append(data["id"])

        if int(data["coins"]) > int(acc["coins"]):
            return

        acc["coins"] = max(0,acc["coins"] - data["coins"])

    persistState()

def getSkinData(username):
    if username not in accounts:
        return False, False

    # Get skin data and coins
    acc = accounts[username]
    return acc["coins"], acc["skins"]

def getAccountData(username):
    if username not in accounts:
        return False

    return accounts[username]

def changePassword(username, password):
    if username not in accounts:
        return

    if len(password) < 8:
        return
    if len(password) > 120:
        return
    acc = accounts[username]
    salt = hashlib.sha256(os.urandom(60)).hexdigest().encode('ascii')
    pwdhash = ph.hash(password.encode('utf-8')+salt)

    acc["salt"] = salt
    acc["pwdhash"] = pwdhash
    
    persistState()

def logout(token):
    if token in session:
        del session[token]

def updateStats(username, stats):
    if username not in accounts:
        return

    acc = accounts[username]
    if "wins" in stats:
        acc["wins"] += stats["wins"]
    if "deaths" in stats:
        acc["deaths"] += stats["deaths"]
    if "kills" in stats:
        acc["kills"] += stats["kills"]
    if "coins" in stats:
        acc["coins"] = max(0,acc["coins"]+stats["coins"])
    if "isBanned" in stats:
        acc["isBanned"] = stats["isBanned"]
        print("Banned " + username)
    if "isDev" in stats:
        acc["isDev"] = stats["isDev"]
    if "isJunior" in stats:
        acc["isJunior"] = stats["isJunior"]
    if "isMod" in stats:
        acc["isMod"] = stats["isMod"]
    if "isMuted" in stats:
        acc["isMuted"] = stats["isMuted"]
    if "strikes" in stats:
        acc["strikes"] = stats["strikes"]

    persistState()

def getLeaderBoard(): # This is such bad code but I'm the only dev so I won't get fired
    leaderboard = []
    # Append account information to array
    for i in accounts:
        leaderboard.append(accounts[i])
    # Set and sort information of array by lambda idfk then cut down to 10 arrays
    winLB = leaderboard.sort(reverse=True, key=lambda x:x["wins"])
    winLB = winLB = leaderboard[:10]
    coinLB = leaderboard.sort(reverse=True, key=lambda x:x["coins"])
    coinLB = coinLB = leaderboard[:10]
    killsLB = leaderboard.sort(reverse=True, key=lambda x:x["kills"])
    killsLB = killsLB = leaderboard[:10]
    # Leaderboard variable and objects
    leaderBoard = {}
    # Create array for each menu in the GUI
    leaderBoard["winsLeaderBoard"] = []
    leaderBoard["coinLeaderBoard"] = []
    leaderBoard["killsLeaderBoard"] = []
    # Use for j in each leaderboard variable and then assign to each menu
    index = 0
    for j in winLB: # For win leaderboard
        index += 1
        obj = {"pos":index, "nickname": j['nickname'], "wins": j['wins'], "skin": j['skin']}
        leaderBoard["winsLeaderBoard"].append(obj)
    index = 0
    for j in coinLB: # For coin leaderboard
        index += 1
        obj = {"pos":index, "nickname": j['nickname'], "coins": j['coins'], "skin": j['skin']}
        leaderBoard["coinLeaderBoard"].append(obj)
    index = 0
    for j in killsLB: # For kill leaderboard
        index += 1
        obj = {"pos":index, "nickname": j['nickname'], "kills": j['kills'], "skin": j['skin']}
        leaderBoard["killsLeaderBoard"].append(obj)
    return leaderBoard


loadState()