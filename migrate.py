from sqlalchemy import Column, ForeignKey, Integer, Boolean, create_engine
from sqlalchemy.dialects.mysql import VARCHAR
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.schema import MetaData
import pickle
import re

Base = declarative_base()

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True)
    username = Column(VARCHAR(20), nullable=False, unique=True)
    salt = Column(VARCHAR(64), nullable=False)
    pwdhash = Column(VARCHAR(128), nullable=False)
    nickname = Column(VARCHAR(50, charset='utf8mb4'), nullable=False, unique=True)
    skin = Column(Integer, nullable=False)
    squad = Column(VARCHAR(10), nullable=False)
    isDev = Column(Boolean, nullable=False, default=False)
    coins = Column(Integer, nullable=False, default=0)
    def summary(self):
        return {"username":self.username, "nickname":self.nickname, "skin":self.skin, "squad":self.squad, "isDev":self.isDev, "coins":self.coins}

engine = create_engine("mysql+mysqlconnector://root:af9fb5c7538225acabbc93bd59405f04317352b811a5e304@localhost/mroyale?charset=utf8mb4&collation=utf8mb4_general_ci", echo=True, pool_recycle=3600)
Base.metadata.bind = engine
Base.metadata.reflect()
DBSession = sessionmaker(bind=engine)
session = DBSession()
Base.metadata.create_all()

with open("server.dat", "rb") as f:
    accounts = pickle.load(f)

uniqueNick=[]

def haircut(s):
    return s.upper().strip()

for name in accounts:
    if not re.match('^[a-zA-Z0-9]+$', name):
        continue
    acc = accounts[name]
    uppernick = haircut(acc["nickname"])
    counter=1
    if uppernick in uniqueNick:
        while uppernick in uniqueNick:
            counter+=1
            uppernick = haircut(acc["nickname"])+str(counter)
        acc["nickname"] = acc["nickname"]+str(counter)
    uniqueNick.append(uppernick)
    if len(acc["squad"])>3:
        acc["squad"] = acc["squad"][:3]
    newacc = Account(username=name, salt=acc["salt"], pwdhash=acc["pwdhash"], nickname=acc["nickname"], skin=acc["skin"], squad=acc["squad"])
    if name.lower() in ["taliondiscord",
                    "damonj17",
                    "ddmil@marioroyale:~$",
                    "pixelcraftian",
                    "igor",
                    "minus",
                    "cyuubi",
                    "gyorokpeter",
                    "zizzydizzymc",
                    "nuts & milk",
                    "jupitersky",
                    "nethowarrior",
                    "rothiseph",
                    "granimated",
                    "weegeepie",
                    "matt8088",
                    "piesel13",
                    "solareon",
                    "tsg"]:
        newacc.isDev=True
    session.add(newacc)

session.commit()
