import os
import json

skins = {}
skinCount = 0

def loadData():
    global skins, skinCount
    try:
        if os.path.exists("database/assets.json"):
            with open("database/assets.json", "r") as f:
                f = json.loads(f.read())
                skins = f["skins"]["shop"]

    except Exception as e:
        print(e)

def getSkins():
    return skins

def getSkinID(id):
    for skin in skins:
        if skin["id"] == id:
            return skin

def getSkinName(name):
    for skin in skins:
        if skin["name"] == name:
            return skin

loadData()