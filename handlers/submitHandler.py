import base64
import collections
import json
import sys
import threading
import traceback
from urllib.parse import urlencode
import math
import time
import os 
import hashlib
import requests
import tornado.gen
import tornado.web

from common.constants import privileges
from common import generalUtils
from common.constants import gameModes
from common.constants import mods
from common.log import logUtils as log
from common.ripple import userUtils
from common.web import requestsManager
from constants import exceptions
from constants import rankedStatuses
from constants.exceptions import ppCalcException
from helpers import aeshelper
from helpers import replayHelper
from helpers import replayHelperRelax
from helpers import replayHelperAuto
from helpers import leaderboardHelper
from helpers import leaderboardHelperRelax
from helpers import leaderboardHelperAuto
from helpers import kotrikhelper
from helpers import aobaHelper
from helpers import achievementsHelper
from helpers.generalHelper import zingonify, getHackByFlag
from objects import beatmap
from objects import glob
from objects import score
from objects import scoreboard
from objects.charts import BeatmapChart, OverallChart , OverallChartFailed , BeatmapChartFailed
from secret.discord_hooks import Webhook
#from circleguard import *
#import matplotlib.pyplot as plt
#from circleparse import replay as circleparse
MODULE_NAME = "submit_modular"

#TODO: use cdef
class handler(requestsManager.asyncRequestHandler):
	"""
	Handler for /web/osu-submit-modular.php
	"""
	@tornado.web.asynchronous
	@tornado.gen.engine
	#@sentry.captureTornado
	def asyncPost(self):
		try:
			# Resend the score in case of unhandled exceptions
			keepSending = True

			timestart = float(time.time())

			# Print arguments
			if glob.debug:
				requestsManager.printArguments(self)
			old_osu = True
			if not requestsManager.checkArguments(self.request.arguments, ["score", "iv", "pass"]):
				raise exceptions.invalidArgumentsException(MODULE_NAME)

			if not "ft" in self.request.arguments:
				if not requestsManager.checkArguments(self.request.arguments, ["fs", "a"]):
					raise exceptions.invalidArgumentsException(MODULE_NAME)
				
				

			# Get parameters and IP
			scoreDataEnc = self.get_argument("score")
			iv = self.get_argument("iv")
			password = self.get_argument("pass")
			ip = self.getRequestIP()
			quit_ = 0
			try:
				failTime = max(0, int(self.get_argument("ft", 0)))
			except ValueError:
				raise exceptions.invalidArgumentsException(MODULE_NAME)
			failed = not quit_ and failTime > 0

			aeskey = glob.conf.config["server"]["scoresubkey"]
			OsuVer = "Really Old"

			# Get score data
			log.debug("Decrypting score data...")
			unsplitScoreData = aeshelper.decryptRinjdael(aeskey, iv, scoreDataEnc, True)
			scoreData = unsplitScoreData.split(":")
			if len(scoreData) < 16 or len(scoreData[0]) != 32:
				raise exceptions.invalidArgumentsException(MODULE_NAME)

			username = scoreData[1].strip()

			# Login and ban check
			userID = userUtils.getID(username)
			# User exists check
			if userID == 0:
				raise exceptions.loginFailedException(MODULE_NAME, userID)

			# Score submission lock check
			lock_key = "lets:score_submission_lock:{}:{}:{}".format(userID, scoreData[0], scoreData[2])
			if glob.redis.get(lock_key) is not None:
				# The same score score is being submitted and it's taking a lot
				log.warning("Score submission blocked because there's a submission lock in place ({})".format(lock_key))
				self.write("error: no")
				return

			log.debug(scoreData)

			# Set score submission lock
			log.debug("Setting score submission lock {}".format(lock_key))
			glob.redis.set(lock_key, "1", 120)


			# Bancho session/username-pass combo check
			if not userUtils.checkLogin(userID, password, ip):
				raise exceptions.loginFailedException(MODULE_NAME, username)
			# 2FA Check
			if userUtils.check2FA(userID, ip):
				raise exceptions.need2FAException(MODULE_NAME, userID, ip)

			user_privileges = userUtils.getPrivileges(userID)
			disabled = not user_privileges & privileges.USER_NORMAL
			restricted = not user_privileges & privileges.USER_PUBLIC

			if disabled: 
				raise exceptions.userBannedException(MODULE_NAME, username)

			# Data length check
			# TODO: do we need this?
			if len(scoreData) < 16:
				log.warning("score length less than 16")
				raise exceptions.invalidArgumentsException(MODULE_NAME)


			# Get variables for relax
			used_mods = int(scoreData[13])
			UsingRelax = used_mods & 128
			UsingAutopilot = used_mods & 8192

			if UsingRelax:
				self.write("error: no")
				return
			elif UsingAutopilot:
				self.write("error: no")
				return
			else:
				replay_mode_full = "_full"
				replay_mode = ""
				game_mode_str = "VANILLA"
				ProfAppend = ""
				rx_type = 0

			log.info("{} has submitted a score on {}...".format(username, scoreData[0]))
			s = score.score()
			log.debug("setting data from score data")
			s.setDataFromScoreData(scoreData, quit_=quit_, failed=failed)
			s.playerUserID = userID
			# Update beatmap playcount (and passcount)
			log.debug("incrementing beatmap playcount")
			beatmap.incrementPlaycount(s.fileMd5, s.passed)

			if s.completed == -1:
				# Duplicated score
				# log.warning("Duplicated score detected, this is normal right after restarting the server")
				self.write("error: no")
				return

			replays_path = glob.conf.config["server"]["replayspath"]

			# Set score stuff missing in score data
			s.playerUserID = userID
			midPPCalcException = None
			# Get beatmap info
			#beatmapInfo = beatmap.beatmap()
			#beatmapInfo.setDataFromDB(s.fileMd5)
			log.debug("getting beatmap info")
			beatmapInfo = beatmap.beatmap()
			log.debug("setting beatmap info data in db")
			beatmapInfo.setDataFromDB(s.fileMd5)
			# Make sure the beatmap is submitted and updated

			#TODO: send an chart even on unranked maps

			if beatmapInfo.rankedStatus in (
				rankedStatuses.NOT_SUBMITTED,
				rankedStatuses.NEED_UPDATE,	
				rankedStatuses.UNKNOWN
			):

				log.debug("Beatmap is not submitted/outdated/unknown. Score submission aborted.")
				self.write("error: beatmap")
				return


			# Check if the ranked status is allowed
			if beatmapInfo.rankedStatus not in glob.conf.extra["_allowed_beatmap_rank"]:
				log.debug("Beatmap's rankstatus is not allowed to be submitted. Score submission aborted.")
				self.write("error: no")
				return


			# Set play time and full play time
			s.fullPlayTime = beatmapInfo.hitLength
			if quit_ or failed:
				s.playTime = failTime // 1000

			relax = 1 if used_mods & 128 else 0

			#this was probably calculated earlier when we ran setDataFromScoreData but just incase we'll run it again if we need to.
			if not s.pp:
				log.debug("calculating pp")
				try:
					s.calculatePP(beatmapInfo)
				except Exception as e:
					log.error("Caught an exception in pp calculation, re-raising after saving score in db")
					s.pp = 0
					midPPCalcException = e
				log.debug("done calculating pp")

			userUtils.incrementUserBeatmapPlaycount(userID, s.gameMode, beatmapInfo.beatmapID)
			

			# Right before submitting the score, get the personal best score object (we need it for charts)
			log.debug("Getting personal best (if required)")
			if s.passed and s.oldPersonalBest > 0:
				log.debug("Getting Personal Best Cache")
				oldPersonalBestRank = glob.personalBestCache.get(userID, s.fileMd5)					
				if oldPersonalBestRank == 0:
					log.debug("We don't have personal best cache, calculating personal best.")
					# oldPersonalBestRank not found in cache, get it from db through a scoreboard object
					oldScoreboard = scoreboard.scoreboard(username, s.gameMode, beatmapInfo, False)
					oldScoreboard.setPersonalBestRank()
					oldPersonalBestRank = max(oldScoreboard.personalBestRank, 0)

				log.debug("Calculating old personal best")
				oldPersonalBest = score.score(s.oldPersonalBest, oldPersonalBestRank)
			else:
				oldPersonalBestRank = 0
				oldPersonalBest = None
			log.debug("Done getting personal best")

			# Save score in db
			s.saveScoreInDB()
				
			# Remove lock as we have the score in the database at this point
			# and we can perform duplicates check through MySQL
			log.debug("Resetting score lock key {}".format(lock_key))
			glob.redis.delete(lock_key)
			


			# Re-raise pp calc exception after saving score, cake, replay etc
			# so Sentry can track it without breaking score submission
			if midPPCalcException is not None:
				raise ppCalcException(midPPCalcException)

			# Always update users stats (total/ranked score, playcount, level, acc and pp)
			# even if not passed
			log.debug("Updating {}'s stats...".format(username))
			# Update personal beatmaps playcount
			
			userUtils.updateStats(userID, s)
			userUtils.updateTotalHits(score=s)
			
			# Get "after" stats for ranking panel
			# and to determine if we should update the leaderboard
			# (only if we passed that song)
			if s.passed:
				oldUserStats = glob.userStatsCache.get(userID, s.gameMode)
				oldRank = userUtils.getGameRank(userID, s.gameMode)
				newUserStats = userUtils.getUserStats(userID, s.gameMode)
				glob.userStatsCache.update(userID, s.gameMode, newUserStats)
				leaderboardHelper.update(userID, newUserStats["pp"], s.gameMode)
				maxCombo = userUtils.getMaxCombo(userID, s.gameMode)

				# Update leaderboard (global and country) if score/pp has changed
				if s.completed == 3 and newUserStats["pp"] != oldUserStats["pp"]:
					leaderboardHelper.update(userID, newUserStats["pp"], s.gameMode)
					leaderboardHelper.updateCountry(userID, newUserStats["pp"], s.gameMode)



			# Score submission and stats update done
			log.debug("Score submission and user stats update done!")
			oldStats = userUtils.getUserStats(userID, s.gameMode)

			# Score has been submitted, do not retry sending the score if
			# there are exceptions while building the ranking panel
			keepSending = False

			if s.completed == 3:
				lb_cache = glob.lb_cache.get_lb_cache(s.gameMode, False)
				glob.lb_cache.clear_lb_cache(lb_cache, beatmapInfo.fileMD5)
				glob.pb_cache.del_user_pb(s.gameMode, userID, beatmapInfo.fileMD5, False)


			# At the end, check achievements
			
			_mode = s.gameMode

			achievements = ""
			achievements_dict = []

			if s.passed:
				try:
					db_achievements = [ ach["achievement_id"] for ach in glob.db.fetchAll("SELECT achievement_id FROM users_achievements WHERE user_id = %s", [userID]) ]
					
					#get extra data for achievements
					achievementData = achievementsHelper.achievementData(userID, beatmapInfo, s, db_achievements)

					for ach in glob.achievements:
						if ach.id in db_achievements:
							continue
						if ach.cond(s, _mode, newUserStats, beatmapInfo, oldUserStats, achievementData):
							userUtils.unlockAchievement(userID, ach.id)
							achievements_dict.append(ach.file)
					achievements_done = 0
					for achievement in achievements_dict:
						if achievements_done == 0:
							achievements = f"{achievement}"
						else:
							achievements = f"{achievements} {achievement}"
						achievements_done += 1

					log.debug(achievements)
	
				except Exception as e:
					log.warning(f"error while processing achievements for score id {s.scoreID} exception: {e}")

			if beatmapInfo is not None and beatmapInfo != False and s.passed:
				log.debug("Started building ranking panel")

				# Trigger bancho stats cache update
				glob.redis.publish("peppy:update_cached_stats", userID)

				newScoreboard = scoreboard.scoreboard(username, s.gameMode, beatmapInfo, False)


				newScoreboard.setPersonalBestRank()
				personalBestID = newScoreboard.getPersonalBest()
				# Get rank info (current rank, pp/score to next rank, user who is 1 rank above us)
				rankInfo = leaderboardHelper.getRankInfo(userID, s.gameMode)
				currentPersonalBest = score.score(personalBestID, newScoreboard.personalBestRank)

				rankable = beatmapInfo.rankedStatus == rankedStatuses.RANKED or beatmapInfo.rankedStatus == rankedStatuses.APPROVED

				# Output dictionary
				log.debug("Using old charts")
				dicts = [
					collections.OrderedDict([
						("beatmapId", beatmapInfo.beatmapID),
						("beatmapSetId", beatmapInfo.beatmapSetID),
						("beatmapPlaycount", beatmapInfo.playcount),
						("beatmapPasscount", beatmapInfo.passcount),
						("approvedDate", beatmapInfo.rankingDate)
					]),
					collections.OrderedDict([
						("chartId", "overall"),
						("chartName", "Overall Ranking"),
						("chartEndDate", ""),
						("beatmapRankingBefore", oldPersonalBestRank),
						("beatmapRankingAfter", newScoreboard.personalBestRank),
						("rankedScoreBefore", oldUserStats["rankedScore"]),
						#bad fix for negative ranked score
						("rankedScoreAfter", newUserStats["rankedScore"] if s.completed == 3 else oldUserStats["rankedScore"]),
						("totalScoreBefore", oldUserStats["totalScore"]),
						("totalScoreAfter", newUserStats["totalScore"]),
						("playCountBefore", newUserStats["playcount"]),
						("accuracyBefore", float(oldUserStats["accuracy"])/100),
						("accuracyAfter", float(newUserStats["accuracy"])/100),
						("rankBefore", oldRank),
						("rankAfter", rankInfo["currentRank"]),
						("toNextRank", rankInfo["difference"]),
						("toNextRankUser", rankInfo["nextUsername"]),
						("achievements", achievements),
						("onlineScoreId", s.scoreID)
					])
				]				
				output = "\n".join(zingonify(x) for x in dicts)
				#log.info(secret.achievements.utils.achievements_response(new_achievements))
				# Some debug messages
				log.debug("Generated output for online ranking screen!")
				log.debug(output)

				# How many PP you got and did you gain any ranks?
				ppGained = newUserStats["pp"] - oldUserStats["pp"]
				gainedRanks = oldRank - rankInfo["currentRank"]

				# Get info about score if they passed the map (Ranked)
				userStats = userUtils.getUserStats(userID, s.gameMode)

				# Send message to #announce if we're rank #1
				if newScoreboard.personalBestRank == 1 and s.completed == 3 and not restricted:
					annmsg = "[https://14fi-web.tanza.me/{}u/{} {}] achieved rank #1 on [https://14fi-web.tanza.me/b/{} {}] ({}) with {}pp".format(
						ProfAppend,
						userID,
						username.encode().decode("ASCII", "ignore"),
						beatmapInfo.beatmapID,
						beatmapInfo.songName.encode().decode("ASCII", "ignore"),
						gameModes.getGamemodeFull(s.gameMode),
						int(s.pp)
					)
					params = urlencode({"k": glob.conf.config["server"]["apikey"], "to": "#announce", "msg": annmsg})
					requests.get("{}/api/v1/fokabotMessage?{}".format(glob.conf.config["server"]["banchourl"], params))

				# Write message to client
				self.write(output)
				log.debug("sent message to client")

			else:
				#thank you skyloc (please come back i miss you)
				#TODO: simplify skyloccode
				glob.redis.publish("peppy:update_cached_stats", userID)

				dicts = [
					collections.OrderedDict([
					("beatmapId", beatmapInfo.beatmapID),
					("beatmapSetId", beatmapInfo.beatmapSetID),
					("beatmapPlaycount", beatmapInfo.playcount + 1),
					("beatmapPasscount", None),
					("approvedDate", beatmapInfo.rankingDate)
				]),
					BeatmapChartFailed(
					0,
					score.score(),
					beatmapInfo.beatmapID,
				),
					OverallChartFailed(userID,0,0,0,"",0,0)
				]
    
				output = "\n".join(zingonify(x) for x in dicts)
				log.debug(output)

				# Write message to client
				self.write(output)	
				log.debug("sent message to client")
	
			self.flush()
			self.finish()
			timeend = float(time.time())
			total_time = (timeend - timestart) * 1000
			log.info(f"Score submission took {(timeend - timestart) * 1000}ms")
			log.debug("request finished")

			ppmsg = glob.redis.get(f"preferences:ppmsg:{userID}")
			if ppmsg and s.completed == 3:
				glob.redis.publish("peppy:notification", json.dumps({
					'userID': userID,
					'message': f"Your latest score is worth\n{s.pp:.2f} pp{' (personal best!)' if s.completed == 3 else ''}"
				}))


			# Datadog stats
			glob.dog.increment(glob.DATADOG_PREFIX+".submitted_scores")
			log.debug("updated datadog stats")

			# TODO: Update max combo
			
			# Update latest activity
			userUtils.updateLatestActivity(userID)

			# IP log
			userUtils.IPLog(userID, ip)

			# Let the api know of this score
			if s.scoreID:
				glob.redis.publish("api:score_submission", s.scoreID)

			#first places go brrr haha
			query = "INSERT INTO first_places (score_id, user_id, score, max_combo, full_combo, mods, 300_count, 100_count, 50_count, miss_count, timestamp, mode, completed, accuracy, pp, play_time, beatmap_md5, relax) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);"
			glob.db.execute(query, [s.scoreID, userID, s.score, s.maxCombo, s.fullCombo, s.mods, s.c300, s.c100, s.c50, s.cMiss, s.playDateTime, s.gameMode, s.completed, s.accuracy*100, s.pp, s.playTime if s.playTime is not None and not s.passed else s.fullPlayTime, s.fileMd5, rx_type])
			glob.db.execute(f"DELETE FROM first_places WHERE beatmap_md5 = %s AND mode = %s AND relax = %s", [s.fileMd5, s.gameMode, rx_type])
			log.debug("first place query done")

			# Save replay for all passed scores, do it after the score is submitted because it can take a long time
			# Make sure the score has an id as well (duplicated?, query error?)
			no_replay = False
			if s.completed == 3 and s.scoreID > 0 or glob.debug and s.passed:
				if "score" in self.request.files:
					# Save the replay if it was provided
					log.debug("Saving replay ({})...".format(s.scoreID))
					replay = self.request.files["score"][0]["body"]
					with open(f"{replays_path}{replay_mode}/replay_{s.scoreID}.osr", "wb") as f:
						f.write(replay)

					data = {
						"a": self.get_argument("a"),
						"u": userID, 
						"s": unsplitScoreData, 
						"p": s.pp,
						"r": base64.b64encode(replayHelper.buildFullReplay(s.scoreID, rawReplay=replay)).decode()
						}

					requests.post("http://127.0.0.1:5010", data=data)
				else:
					# Restrict if no replay was provided
					if not restricted:
						userUtils.restrict(userID)
						log.warning(f"{username} ({userID}) tried sending a score without a replay, they have now been restricted lol")

		except exceptions.invalidArgumentsException:
			pass
		except exceptions.loginFailedException:
			self.write("error: pass")
		except exceptions.need2FAException:
			# Send error pass to notify the user
			# resend the score at regular intervals
			# for users with memy connection
			self.set_status(408)
			self.write("error: 2fa")
		except exceptions.userBannedException:
			self.write("error: ban")
		except exceptions.noBanchoSessionException:
			self.set_status(408)
			self.write("error: pass")

		except Exception:
			# Try except block to avoid more errors
			try:
				log.error("Unknown error in {}!\n```{}\n{}```".format(MODULE_NAME, sys.exc_info(), traceback.format_exc()))
				if glob.sentry:
					yield tornado.gen.Task(self.captureException, exc_info=True)
			except:
				pass
	
		# Every other exception returns a 408 error (timeout)
		# This avoids lost scores due to score server crash
		# because the client will send the score again after some time.
		if keepSending:
			self.set_status(408)


