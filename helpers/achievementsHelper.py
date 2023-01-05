from objects import glob
from common.log import logUtils as log
import time

class achievementData:
    def __init__(self, userID, beatmapObject, scoreObject, db_achievements):

            self.userID = userID

            #Beatmap data
            self.beatmapName = beatmapObject.songName
            self.beatmapSetID = beatmapObject.beatmapSetID
            self.beatmapID = beatmapObject.beatmapID
            self.beatmapAR = beatmapObject.AR
            self.beatmapOD = beatmapObject.OD
            self.beatmapMaxCombo = beatmapObject.maxCombo
            self.beatmapHitLength = beatmapObject.hitLength
            self.beatmapbpm = beatmapObject.bpm
            self.beatmapRankedStatus = beatmapObject.rankedStatus
            self.beatmapMD5 = beatmapObject.fileMD5

            #Score data
            self.scoreMods = scoreObject.mods
            self.scoreMaxCombo = scoreObject.maxCombo
            self.scoreC50 = scoreObject.c50
            self.scoreC100 = scoreObject.c100
            self.scoreC300 = scoreObject.c300
            self.scoreCMiss = scoreObject.cMiss
            self.scoreCKatu = scoreObject.cKatu
            self.scoreCGeki = scoreObject.cGeki
            self.scoreScore = scoreObject.score
            self.scoreGameMode = scoreObject.gameMode
            self.scoreRank = scoreObject.rank
            self.scorePlayTime = scoreObject.playTime
            self.scoreFullPlayTime = scoreObject.fullPlayTime
            self.currentAchievements = db_achievements

            #Achievents to unlock
            self.unlockYandere = False
            self.unlockSRanker = False
            self.unlockMostImproved = False
            self.unlockObsessed = False
            self.unlockObamaCode = False


            self.checkAchievements()
    
    def checkAchievements(self):
        #TODO: dont check medals user already has
        checkYandere(self)
        checkSRanker(self)
        checkMostImproved(self)
        checkObsessed(self)
        checkObamaCode(self)




def checkUserPlayedBeatmapSet(userID, beatmapSetID):
    req = glob.db.fetch("SELECT 1 FROM users_beatmap_playcount WHERE user_id = %s AND beatmap_id in (SELECT beatmap_id FROM beatmaps WHERE beatmapset_id = %s)", [userID, beatmapSetID])
    if req:
        return True
    else:
        return False
def checkUserPlayedBeatmap(userID, beatmapID):
    req = glob.db.fetch("SELECT 1 FROM users_beatmap_playcount WHERE user_id = %s AND beatmap_id = %s", [userID, beatmapID])
    if req:
        return True
    else:
        return False

def checkYandere(self):
    # Check if we already have the achievement.
    if not 136 in self.currentAchievements:
        #check if we can unlock yandere achievement
        if(
            self.beatmapSetID == 935098
            or self.beatmapSetID == 959688
            or self.beatmapSetID == 1016769
            or self.beatmapSetID == 744593
        ):
            if checkUserPlayedBeatmapSet(self.userID, 935098):
                if checkUserPlayedBeatmapSet(self.userID, 959688):
                    if checkUserPlayedBeatmap(self.userID, 2128030):
                        if checkUserPlayedBeatmap(self.userID, 1569904):
                            self.unlockYandere = True

def checkSRanker(self):
    # Check if we already have the achievement.
    if not 139 in self.currentAchievements:
        good_time = int(time.time()) - 3600
        count = glob.db.fetch(f"SELECT COUNT(distinct beatmap_md5) FROM scores WHERE userid = %s AND rank IN ('S','SH','XH','X') AND time > %s", [self.userID, good_time])
        log.debug(f"s ranker count: {count}")
        if int(count["COUNT(distinct beatmap_md5)"]) >= 5:
            self.unlockSRanker = True

def checkMostImproved(self):
    # Check if we already have the achievement.
    if not 140 in self.currentAchievements:
        if self.scoreRank == 'S' or self.scoreRank == 'SH' or self.scoreRank == 'A' or self.scoreRank == 'X' or self.scoreRank == 'XH':
            # TODO: for some reason when i use prepared queries here it breaks, it dosent matter because this isnt injectable anyways, but this needs investigation
            count = glob.db.fetch(f"SELECT COUNT(*) FROM scores WHERE userid = '{self.userID}' and beatmap_md5 = '{self.beatmapMD5}' AND rank IN('S', 'SH', 'A', 'X', 'XH') and time > (SELECT min(time) FROM scores WHERE userid = '{self.userID}' AND rank = 'D' AND score > 100000 AND beatmap_md5 = '{self.beatmapMD5}')")
            log.debug(f"most improved count: {count}")
            if int(count["COUNT(*)"]) > 0:
                self.unlockMostImproved = True

def checkObsessed(self):
    # Check if we already have the achievement.
    if not 141 in self.currentAchievements:
        count = glob.db.fetch("SELECT COUNT(*) FROM scores WHERE userid = %s AND beatmap_md5 = %s AND completed = 1 OR completed = 0", [self.userID, self.beatmapMD5])
        if int(count["COUNT(*)"]) >= 100:
            self.unlockObsessed = True

def checkObamaCode(self):
    # Check if we already have the achievement.
    if not 143 in self.currentAchievements:
        obamaFavourites = glob.db.fetchAll("SELECT * FROM favourite_beatmaps WHERE userid = 1000")
        for favourite in obamaFavourites:
            beatmapSetID = favourite["beatmapset_id"]
            if not checkUserPlayedBeatmapSet(self.userID, beatmapSetID):
                return
        self.unlockObamaCode = True
