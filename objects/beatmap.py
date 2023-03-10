import time
import datetime

from common.log import logUtils as log
from constants import rankedStatuses
from helpers import osuapiHelper
import objects.glob


class beatmap:
	__slots__ = ("songName", "fileMD5", "artist", "title", "creator", "difficulty", "rankedStatus", "rankedStatusFrozen", "beatmapID", "beatmapSetID", "offset",
	             "rating", "starsStd", "starsTaiko", "starsCtb", "starsMania", "AR", "OD", "maxCombo", "hitLength",
	             "bpm", "rankingDate", "playcount" ,"passcount", "refresh", "fileName")

	def __init__(self, md5 = None, beatmapSetID = None, gameMode = 0, refresh=False, fileName=None):
		"""
		Initialize a beatmap object.

		md5 -- beatmap md5. Optional.
		beatmapSetID -- beatmapSetID. Optional.
		"""
		self.songName = ""
		self.fileMD5 = ""
		self.artist = ""
		self.title = ""
		self.creator = ""
		self.difficulty = ""
		self.fileName = fileName
		self.rankedStatus = rankedStatuses.NOT_SUBMITTED
		self.rankedStatusFrozen = 0
		self.beatmapID = 0
		self.beatmapSetID = 0
		self.offset = 0		# Won't implement
		self.rating = 0.0
		self.starsStd = 0.0	# stars for converted
		self.starsTaiko = 0.0	# stars for converted
		self.starsCtb = 0.0		# stars for converted
		self.starsMania = 0.0	# stars for converted
		self.AR = 0.0
		self.OD = 0.0
		self.maxCombo = 0
		self.hitLength = 0
		self.bpm = 0

		self.rankingDate = 0
		
		# Statistics for ranking panel
		self.playcount = 0

		# Force refresh from osu api
		self.refresh = refresh

		if md5 is not None and beatmapSetID is not None:
			self.setData(md5, beatmapSetID)

	def addBeatmapToDB(self):
		"""
		Add current beatmap data in db if not in yet
		"""
		if self.fileMD5 is None:
			self.rankedStatus = rankedStatuses.NOT_SUBMITTED
			return
		
		# Make sure the beatmap is not already in db
		bdata = objects.glob.db.fetch(
			"SELECT id, ranked_status_freezed, ranked FROM beatmaps "
			"WHERE beatmap_md5 = %s OR beatmap_id = %s LIMIT 1",
			(self.fileMD5, self.beatmapID)
		)
		if bdata is not None:
			# This beatmap is already in db, remove old record
			# Get current frozen status
			frozen = bdata["ranked_status_freezed"]
			if frozen == 1:
				self.rankedStatus = bdata["ranked"]
			log.debug("Deleting old beatmap data ({})".format(bdata["id"]))
			objects.glob.db.execute("DELETE FROM beatmaps WHERE id = %s LIMIT 1", [bdata["id"]])
		else:
			# Unfreeze beatmap status
			frozen = False

		if objects.glob.conf.extra["mode"]["rank-all-maps"]:
			self.rankedStatus = 2

		# Add new beatmap data
		log.debug("Saving beatmap data in db...")
		params = [
			self.beatmapID,
			self.beatmapSetID,
			self.fileMD5,
			self.songName.encode("utf-8", "ignore").decode("utf-8"),
			self.AR,
			self.OD,
			self.starsStd,
			self.starsTaiko,
			self.starsCtb,
			self.starsMania,
			self.maxCombo,
			self.hitLength,
			self.bpm,
			self.rankedStatus if frozen == 0 else 2,
			int(time.time()),
			self.creator,
			self.artist,
			self.title,
			self.difficulty,
			frozen,
		#)
		]
		if self.fileName is not None:
			params.append(self.fileName)
		objects.glob.db.execute(
			"INSERT INTO `beatmaps` (`id`, `beatmap_id`, `beatmapset_id`, `beatmap_md5`, `song_name`, "
			"`ar`, `od`, `difficulty_std`, `difficulty_taiko`, `difficulty_ctb`, `difficulty_mania`, "
			"`max_combo`, `hit_length`, `bpm`, `ranked`, "
			"`latest_update`, `creator`, `artist`, `title`, `version`, `ranked_status_freezed`{extra_q}) "
			"VALUES (NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s{extra_p})".format(
				extra_q=", `file_name`" if self.fileName is not None else "",
				extra_p=", %s" if self.fileName is not None else "",
			), params
		)

	def saveFileName(self, fileName):
		# Temporary workaround to avoid re-fetching all beatmaps from osu!api
		r = objects.glob.db.fetch("SELECT file_name FROM beatmaps WHERE beatmap_md5 = %s LIMIT 1", (self.fileMD5,))
		if r is None:
			return
		if r["file_name"] is None:
			objects.glob.db.execute(
				"UPDATE beatmaps SET file_name = %s WHERE beatmap_md5 = %s LIMIT 1",
				(self.fileName, self.fileMD5)
			)

	def setDataFromDB(self, md5):
		"""
		Set this object's beatmap data from db.

		md5 -- beatmap md5
		return -- True if set, False if not set
		"""

		# THERE IS SO MUCH BROKEN IN THIS FUNCTION I WANT TO DIE

		# We check for dupes here because if a score is submitted on a map with duplicate entries in the db, it will appear twice on the users profile, ripplecode

		# Get data from DB

		# Removed the LIMIT 1 here so we can check for dupes
		resp = objects.glob.db.fetchAll("SELECT * FROM beatmaps WHERE beatmap_md5 = %s", [md5])

		# will be 1 if no dupes, more if there are dupes
		dupes = 0

		data = {}

		for row in resp:
			if dupes == 0:
				# make the first row the value for data
				data = row

			#increment the number of dupes
			dupes = dupes + 1

		if dupes > 1:
			# We have dupes, delete them.
			objects.glob.db.execute("DELETE FROM beatmaps WHERE beatmap_md5 = %s ORDER BY id DESC LIMIT 1", [data["beatmap_md5"]])

		# Make sure the query returned something
		if dupes == 0:
			return False

		#log.info(data)

		# Make sure the beatmap is not an old one

		'''
		# Set cached data period
		expire = int(objects.glob.conf.config["server"]["beatmapcacheexpire"])

		# If the map is qualified, we need to check much more often, so we'll make it 2 hours.
		if data["ranked"] == rankedStatuses.QUALIFIED and data["ranked_status_freezed"] == 0:
			expire = 7200

		# If the beatmap is ranked, we don't need to refresh data from osu!api that often
		if data["ranked"] >= rankedStatuses.RANKED and data["ranked_status_freezed"] == 0:
			expire *= 3

		# Make sure the beatmap data in db is not too old
		if int(expire) > 0 and time.time() > data["latest_update"]+int(expire) and not data["ranked_status_freezed"]:
			return False
		'''

		# this is stupid, there needs to be a more reliable way to check for this.
		# i would say this check is unneccicary, but knowing ripplecode, it probably is.
		#if data["difficulty_taiko"] == 0.0 and data["difficulty_ctb"] == 0.0 and data["difficulty_mania"] == 0.0:
		#	log.debug("Difficulty for non-std gamemodes not found in DB, refreshing data from osu!api...")
		#	return False

		# Data in DB, set beatmap data
		log.debug("Got beatmap data from db")
		self.setDataFromDict(data)
		return True

	def setDataFromDict(self, data):
		"""
		Set this object's beatmap data from data dictionary.

		data -- data dictionary
		return -- True if set, False if not set
		"""
		self.songName = data["song_name"]
		self.fileMD5 = data["beatmap_md5"]
		self.rankedStatus = int(data["ranked"])
		self.rankedStatusFrozen = int(data["ranked_status_freezed"])
		self.beatmapID = int(data["beatmap_id"])
		self.beatmapSetID = int(data["beatmapset_id"])
		self.AR = float(data["ar"])
		self.OD = float(data["od"])
		self.starsStd = float(data["difficulty_std"])
		self.starsTaiko = float(data["difficulty_taiko"])
		self.starsCtb = float(data["difficulty_ctb"])
		self.starsMania = float(data["difficulty_mania"])
		self.maxCombo = int(data["max_combo"])
		self.hitLength = int(data["hit_length"])
		self.bpm = int(data["bpm"])
		# Ranking panel statistics
		self.playcount = int(data["playcount"]) if "playcount" in data else 0
		self.passcount = int(data["passcount"]) if "passcount" in data else 0

	def setDataFromOsuApi(self, md5, beatmapSetID):
		"""
		Set this object's beatmap data from osu!api.

		md5 -- beatmap md5
		beatmapSetID -- beatmap set ID, used to check if a map is outdated
		return -- True if set, False if not set
		"""
		# Check if osuapi is enabled
		mainData = None
		dataStd = osuapiHelper.osuApiRequest("get_beatmaps", "h={}&a=1&m=0".format(md5))
		dataTaiko = osuapiHelper.osuApiRequest("get_beatmaps", "h={}&a=1&m=1".format(md5))
		dataCtb = osuapiHelper.osuApiRequest("get_beatmaps", "h={}&a=1&m=2".format(md5))
		dataMania = osuapiHelper.osuApiRequest("get_beatmaps", "h={}&a=1&m=3".format(md5))
		if dataStd is not None:
			mainData = dataStd
		elif dataTaiko is not None:
			mainData = dataTaiko
		elif dataCtb is not None:
			mainData = dataCtb
		elif dataMania is not None:
			mainData = dataMania

		# If the beatmap is frozen and still valid from osu!api, return True so we don't overwrite anything
		if mainData is not None and self.rankedStatusFrozen == 1 and self.beatmapSetID > 100000000:
			return True

		# Can't fint beatmap by MD5. The beatmap has been updated. Check with beatmap set ID
		if mainData is None:
			log.debug("osu!api data is None")
			dataStd = osuapiHelper.osuApiRequest("get_beatmaps", "s={}&a=1&m=0".format(beatmapSetID))
			dataTaiko = osuapiHelper.osuApiRequest("get_beatmaps", "s={}&a=1&m=1".format(beatmapSetID))
			dataCtb = osuapiHelper.osuApiRequest("get_beatmaps", "s={}&a=1&m=2".format(beatmapSetID))
			dataMania = osuapiHelper.osuApiRequest("get_beatmaps", "s={}&a=1&m=3".format(beatmapSetID))
			if dataStd is not None:
				mainData = dataStd
			elif dataTaiko is not None:
				mainData = dataTaiko
			elif dataCtb is not None:
				mainData = dataCtb
			elif dataMania is not None:
				mainData = dataMania

			if mainData is None:
				# Still no data, beatmap is not submitted
				return False
			else:
				# We have some data, but md5 doesn't match. Beatmap is outdated
				self.rankedStatus = rankedStatuses.NEED_UPDATE
				return True


		# We have data from osu!api, set beatmap data
		log.debug("Got beatmap data from osu!api")
		self.songName = "{} - {} [{}]".format(mainData["artist"], mainData["title"], mainData["version"])
		self.fileName = "{} - {} ({}) [{}].osu".format(
			mainData["artist"], mainData["title"], mainData["creator"], mainData["version"]
		).replace("\\", "")
		self.artist = mainData["artist"]
		self.title = mainData["title"]
		self.creator = mainData["creator"]
		self.difficulty = mainData["version"]
		self.fileMD5 = md5
		self.rankedStatus = convertRankedStatus(int(mainData["approved"]))
		
		# Make maps newer than July 8, 2014 23:59:59 UTC unranked

		if self.rankedStatus > 1:
			
			self.rankingDate = int(time.mktime(datetime.datetime.strptime(mainData["approved_date"], "%Y-%m-%d %H:%M:%S").timetuple()))
			if self.rankingDate > 1404863999:
				self.rankedStatus = 0
		else:
			self.rankingDate = int(time.mktime(datetime.datetime.strptime(mainData["last_update"], "%Y-%m-%d %H:%M:%S").timetuple()))
			
		self.beatmapID = int(mainData["beatmap_id"])
		self.beatmapSetID = int(mainData["beatmapset_id"])
		self.AR = float(mainData["diff_approach"])
		self.OD = float(mainData["diff_overall"])

		# Determine stars for every mode
		self.starsStd = 0.0
		self.starsTaiko = 0.0
		self.starsCtb = 0.0
		self.starsMania = 0.0
		if dataStd is not None:
			self.starsStd = float(dataStd.get("difficultyrating", 0))
		if dataTaiko is not None:
			self.starsTaiko = float(dataTaiko.get("difficultyrating", 0))
		if dataCtb is not None:
			self.starsCtb = float(
				next((x for x in (dataCtb.get("difficultyrating"), dataCtb.get("diff_aim")) if x is not None), 0)
			)
		if dataMania is not None:
			self.starsMania = float(dataMania.get("difficultyrating", 0))

		self.maxCombo = int(mainData["max_combo"]) if mainData["max_combo"] is not None else 0
		self.hitLength = int(mainData["hit_length"])
		if mainData["bpm"] is not None:
			self.bpm = int(float(mainData["bpm"]))
		else:
			self.bpm = -1
		return True

	def setData(self, md5, beatmapSetID):
		"""
		Set this object's beatmap data from highest level possible.

		md5 -- beatmap MD5
		beatmapSetID -- beatmap set ID
		"""
		# Get beatmap from db
		dbResult = self.setDataFromDB(md5)

		# Force refresh from osu api.
		# We get data before to keep frozen maps ranked
		# if they haven't been updated
		if dbResult and self.refresh:
			dbResult = False

		if not dbResult:
			log.debug("Beatmap not found in db")
			# If this beatmap is not in db, get it from osu!api
			apiResult = self.setDataFromOsuApi(md5, beatmapSetID)
			if not apiResult:
				# If it's not even in osu!api, this beatmap is not submitted
				self.rankedStatus = rankedStatuses.NOT_SUBMITTED
			elif self.rankedStatus != rankedStatuses.NOT_SUBMITTED and self.rankedStatus != rankedStatuses.NEED_UPDATE:
				# We get beatmap data from osu!api, save it in db
				self.addBeatmapToDB()
		else:
			log.debug("Beatmap found in db")

		log.debug("{}\n{}\n{}\n{}".format(self.starsStd, self.starsTaiko, self.starsCtb, self.starsMania))

	def getData(self, totalScores=0, version=4):
		"""
		Return this beatmap's data (header) for getscores

		return -- beatmap header for getscores
		"""
		# Fix loved maps for old clients
		if version < 4 and self.rankedStatus == rankedStatuses.LOVED:
			rankedStatusOutput = rankedStatuses.QUALIFIED
		else:
			rankedStatusOutput = self.rankedStatus
		data = "{}|false".format(rankedStatusOutput)
		if self.rankedStatus != rankedStatuses.NOT_SUBMITTED and self.rankedStatus != rankedStatuses.NEED_UPDATE and self.rankedStatus != rankedStatuses.UNKNOWN:
			# If the beatmap is updated and exists, the client needs more data
			data += "|{}|{}|{}\n{}\n{}\n{}\n".format(self.beatmapID, self.beatmapSetID, totalScores, self.offset, self.songName, self.rating)

		# Return the header
		return data

	def getCachedTillerinoPP(self):
		"""
		Returned cached pp values for 100, 99, 98 and 95 acc nomod
		(used ONLY with Tillerino, pp is always calculated with oppai when submitting scores)

		return -- list with pp values. [0,0,0,0] if not cached.
		"""
		data = objects.glob.db.fetch("SELECT pp_100, pp_99, pp_98, pp_95 FROM beatmaps WHERE beatmap_md5 = %s LIMIT 1", [self.fileMD5])
		if data is None:
			return [0,0,0,0]
		return [data["pp_100"], data["pp_99"], data["pp_98"], data["pp_95"]]

	def saveCachedTillerinoPP(self, l):
		"""
		Save cached pp for tillerino

		l -- list with 4 default pp values ([100,99,98,95])
		"""
		objects.glob.db.execute("UPDATE beatmaps SET pp_100 = %s, pp_99 = %s, pp_98 = %s, pp_95 = %s WHERE beatmap_md5 = %s", [l[0], l[1], l[2], l[3], self.fileMD5])

	@property
	def is_rankable(self):
		return self.rankedStatus >= rankedStatuses.RANKED and self.rankedStatus != rankedStatuses.UNKNOWN

def convertRankedStatus(approvedStatus):
	"""
	Convert approved_status (from osu!api) to ranked status (for getscores)

	approvedStatus -- approved status, from osu!api
	return -- rankedStatus for getscores
	"""

	approvedStatus = int(approvedStatus)
	if approvedStatus <= 0:
		return rankedStatuses.PENDING
	elif approvedStatus == 1:
		return rankedStatuses.RANKED
	elif approvedStatus == 2:
		return rankedStatuses.APPROVED
	elif approvedStatus == 3:
		return rankedStatuses.QUALIFIED
	elif approvedStatus == 4:
		return rankedStatuses.LOVED
	else:
		return rankedStatuses.UNKNOWN

def incrementPlaycount(md5, passed):
	"""
	Increment playcount (and passcount) for a beatmap

	md5 -- beatmap md5
	passed -- if True, increment passcount too
	"""
	objects.glob.db.execute(
		f"UPDATE beatmaps "
		f"SET playcount = playcount+1{', passcount = passcount+1' if passed else ''} "
		f"WHERE beatmap_md5 = %s LIMIT 1",
		[md5]
	)

