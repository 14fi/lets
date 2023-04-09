# General imports
import os
import sys
from multiprocessing.pool import ThreadPool
import asyncio
import tornado.gen
import tornado.httpserver
import tornado.ioloop
import tornado.web
from raven.contrib.tornado import AsyncSentryClient
import redis

import json
import shutil
from distutils.version import LooseVersion

from constants import rankedStatuses
import prometheus_client
from common.constants import bcolors, mods
from common.db import dbConnector
from common.ddog import datadogClient
from common.log import logUtils as log
from common.redis import pubSub
from common.web import schiavo
from handlers import apiCacheBeatmapHandler, rateHandler, changelogHandler
from handlers import apiPPHandler
from handlers import apiStatusHandler
from handlers import banchoConnectHandler
from handlers import defaultHandler
from handlers import downloadMapHandler
from handlers import emptyHandler
from handlers import getFullReplayHandler
from handlers import getFullReplayHandlerRelax
from handlers import getFullReplayHandlerAuto
from handlers import getReplayHandler
from handlers import getScoresHandler
from handlers import getScreenshotHandler
from handlers import loadTestHandler
from handlers import mapsHandler
from handlers import inGameRegistrationHandler
from handlers import getFullErrorHandler
from handlers import osuErrorHandler
from handlers import osuSearchHandler
from handlers import osuSearchSetHandler
from handlers import redirectHandler
from handlers import lastFMHandler
from handlers import submitModularHandler
from handlers import submitHandler
from handlers import uploadScreenshotHandler
from handlers import commentHandler
from handlers import difficultyRatingHandler
from handlers import osuGetFriends
from handlers import getFavouriteHandler
from handlers import setFavouriteHandler
from handlers import checkForUpdatesHandler
from handlers import updateDownloadHandler
from handlers import updateDownloadHandler2
from handlers import updateListHandler
from handlers import getUntoneTokenHandler
from helpers import config
from helpers import consoleHelper
from common import generalUtils
from common import agpl
from objects import glob
from pubSubHandlers import beatmapUpdateHandler
from objects.achievement import Achievement
import traceback
def make_app():
	return tornado.web.Application([
		(r"/users", inGameRegistrationHandler.handler), 
		(r"/web/bancho_connect.php", banchoConnectHandler.handler),
		(r"/web/osu-osz2-getscores.php", getScoresHandler.handler),
		(r"/web/osu-submit-modular.php", submitModularHandler.handler),
		(r"/web/14fi-submit.php", submitHandler.handler),
		(r"/web/osu-getreplay.php", getReplayHandler.handler),
		(r"/web/osu-screenshot.php", uploadScreenshotHandler.handler),
		(r"/web/osu-search.php", osuSearchHandler.handler),
		(r"/web/osu-search-set.php", osuSearchSetHandler.handler),
		(r"/web/osu-error.php", osuErrorHandler.handler),
		(r"/web/osu-comment.php", commentHandler.handler),
		(r"/p/changelog", changelogHandler.handler),
		(r"/web/changelog.php", changelogHandler.handler),
		(r"/home/changelog", changelogHandler.handler),
		(r"/web/osu-rate.php", rateHandler.handler),
		(r"/web/lastfm.php", lastFMHandler.handler),
		(r"/ss/(.*)", getScreenshotHandler.handler),
		(r"/web/maps/(.*)", mapsHandler.handler),
		(r"/d/(.*)", downloadMapHandler.handler),
		(r"/s/(.*)", downloadMapHandler.handler),
		(r"/web/replays/(.*)", getFullReplayHandler.handler),
		(r"/web/replays_relax/(.*)", getFullReplayHandlerRelax.handler),
		(r"/web/replays_auto/(.*)", getFullReplayHandlerAuto.handler),
		(r"/web/errorlogs/(.*)", getFullErrorHandler.handler),
		(r"/api/v1/status", apiStatusHandler.handler),
		(r"/api/v1/pp", apiPPHandler.handler),
		(r"/api/v1/cacheBeatmap", apiCacheBeatmapHandler.handler),

		(r"/letsapi/v1/status", apiStatusHandler.handler),
		(r"/letsapi/v1/pp", apiPPHandler.handler),
		(r"/letsapi/v1/cacheBeatmap", apiCacheBeatmapHandler.handler),

		(r"/web/osu-getfriends.php", osuGetFriends.handler),
		(r"/web/osu-addfavourite.php", setFavouriteHandler.handler),
		(r"/web/osu-getfavourites.php", getFavouriteHandler.handler),

		(r"/web/14fi-getuntonetoken.php", getUntoneTokenHandler.handler),

		(r"/release/update.php", checkForUpdatesHandler.handler),
		(r"/release/update", updateListHandler.handler),
		(r"/release/osu!.exe.zip", updateDownloadHandler.handler),
		#TODO: don't do it like this, this is shit
		(r"/release/osu!framework.dll", updateDownloadHandler2.handler),

		# Not done yet
		(r"/web/osu-get-beatmap-topic.php", emptyHandler.handler),
		(r"/web/osu-markasread.php", emptyHandler.handler),
		(r"/web/osu-checktweets.php", emptyHandler.handler),
		(r"/web/osu-getbeatmapinfo.php", emptyHandler.handler),
		(r"/home/notifications/endpoint", emptyHandler.handler),
		(r"/web/osu-getbeatmapinfo.php", emptyHandler.handler),
		(r"/web/osu-getcharts.php", emptyHandler.handler),

		(r"/loadTest", loadTestHandler.handler),
		(r"/difficulty-rating", difficultyRatingHandler.handler),
	], default_handler_class=defaultHandler.handler)


def main() -> int:
	# AGPL license agreement
	try:
		agpl.check_license("ripple", "LETS")
	except agpl.LicenseError as e:
		print(str(e))
		return 1

	try:
		consoleHelper.printServerStartHeader(True)

		# Read config
		consoleHelper.printNoNl("> Reading config file... ")
		glob.conf = config.config("config.ini")

		if glob.conf.default:
			# We have generated a default config.ini, quit server
			consoleHelper.printWarning()
			consoleHelper.printColored("[!] config.ini not found. A default one has been generated.", bcolors.YELLOW)
			consoleHelper.printColored("[!] Please edit your config.ini and run the server again.", bcolors.YELLOW)
			return 1

		# If we haven't generated a default config.ini, check if it's valid
		if not glob.conf.checkConfig():
			consoleHelper.printError()
			consoleHelper.printColored("[!] Invalid config.ini. Please configure it properly", bcolors.RED)
			consoleHelper.printColored("[!] Delete your config.ini to generate a default one", bcolors.RED)
			return 1
		else:
			consoleHelper.printDone()

		# Read additional config file
		consoleHelper.printNoNl("> Loading additional config file... ")
		try:
			if not os.path.isfile(glob.conf.config["custom"]["config"]):
				consoleHelper.printWarning()
				consoleHelper.printColored("[!] Missing config file at {}; A default one has been generated at this location.".format(glob.conf.config["custom"]["config"]), bcolors.YELLOW)
				shutil.copy("common/default_config.json", glob.conf.config["custom"]["config"])

			with open(glob.conf.config["custom"]["config"], "r") as f:
				glob.conf.extra = json.load(f)

			consoleHelper.printDone()
		except:
			consoleHelper.printWarning()
			consoleHelper.printColored("[!] Unable to load custom config at {}".format(glob.conf.config["custom"]["config"]), bcolors.RED)
			return 1

		# Create data/oppai maps folder if needed
		consoleHelper.printNoNl("> Checking folders... ")
		paths = [
			".data",
			".data/oppai",
			".data/catch_the_pp",
			glob.conf.config["server"]["replayspath"],
			"{}_relax".format(glob.conf.config["server"]["replayspath"]),
			glob.conf.config["server"]["beatmapspath"],
			glob.conf.config["server"]["screenshotspath"]
		]
		for i in paths:
			if not os.path.exists(i):
				os.makedirs(i, 0o770)
		consoleHelper.printDone()

		# Connect to db
		try:
			consoleHelper.printNoNl("> Connecting to MySQL database... ")
			glob.db = dbConnector.db(glob.conf.config["db"]["host"], glob.conf.config["db"]["username"], glob.conf.config["db"]["password"], glob.conf.config["db"]["database"], int(
				glob.conf.config["db"]["workers"]))
			consoleHelper.printNoNl(" ")
			consoleHelper.printDone()
		except:
			# Exception while connecting to db
			consoleHelper.printError()
			consoleHelper.printColored("[!] Error while connection to database. Please check your config.ini and run the server again", bcolors.RED)
			raise

		# Connect to redis
		try:
			consoleHelper.printNoNl("> Connecting to redis... ")
			glob.redis = redis.Redis(glob.conf.config["redis"]["host"], glob.conf.config["redis"]["port"], glob.conf.config["redis"]["database"], glob.conf.config["redis"]["password"])
			glob.redis.ping()
			consoleHelper.printNoNl(" ")
			consoleHelper.printDone()
		except:
			# Exception while connecting to db
			consoleHelper.printError()
			consoleHelper.printColored("[!] Error while connection to redis. Please check your config.ini and run the server again", bcolors.RED)
			raise

		# Empty redis cache
		#TODO: do we need this?
		try:
			glob.redis.eval("return redis.call('del', unpack(redis.call('keys', ARGV[1])))", 0, "lets:*")
		except redis.exceptions.ResponseError:
			# Script returns error if there are no keys starting with peppy:*
			pass

		# Save lets version in redis
		glob.redis.set("lets:version", glob.VERSION)

		# Create threads pool
		try:
			consoleHelper.printNoNl("> Creating threads pool... ")
			glob.pool = ThreadPool(int(glob.conf.config["server"]["threads"]))
			consoleHelper.printDone()
		except:
			consoleHelper.printError()
			consoleHelper.printColored("[!] Error while creating threads pool. Please check your config.ini and run the server again", bcolors.RED)

		# Load achievements
		consoleHelper.printNoNl("> Loading achievements... ")
		try:
			achievements = glob.db.fetchAll("SELECT * FROM achievements")
			for achievement in achievements:
				condition = eval(f"lambda score, mode_vn, stats, beatmapInfo, oldUserStats, achievementData: {achievement.pop('cond')}")
				glob.achievements.append(Achievement(
				_id= achievement['id'],
				file= achievement['icon'],
				name= achievement['name'],
				desc= achievement['description'],
				cond= condition
			))
		except Exception as e:
			consoleHelper.printError()
			consoleHelper.printColored(
				"[!] Error while loading achievements! ({})".format(traceback.format_exc()),
				bcolors.RED,
			)
			return 1
		consoleHelper.printDone()

		# Set achievements version
		glob.redis.set("lets:achievements_version", glob.ACHIEVEMENTS_VERSION)
		consoleHelper.printColored("Achievements version is {}".format(glob.ACHIEVEMENTS_VERSION), bcolors.YELLOW)

		# Print disallowed mods into console (Used to also assign it into variable but has been moved elsewhere)
		unranked_mods = [key for key, value in glob.conf.extra["common"]["rankable-mods"].items() if not value]
		consoleHelper.printColored("Unranked mods: {}".format(", ".join(unranked_mods)), bcolors.YELLOW)
		
		# Print allowed beatmap rank statuses
		allowed_beatmap_rank = [key for key, value in glob.conf.extra["lets"]["allowed-beatmap-rankstatus"].items() if value]
		consoleHelper.printColored("Allowed beatmap rank statuses: {}".format(", ".join(allowed_beatmap_rank)), bcolors.YELLOW)

		# Make array of bools to respective rank id's
		glob.conf.extra["_allowed_beatmap_rank"] = [getattr(rankedStatuses, key) for key in allowed_beatmap_rank] # Store the allowed beatmap rank id's into glob


		# Discord
		if generalUtils.stringToBool(glob.conf.config["discord"]["enable"]):
			glob.schiavo = schiavo.schiavo(glob.conf.config["discord"]["boturl"], "**lets**")
		else:
			consoleHelper.printColored("[!] Warning! Discord logging is disabled!", bcolors.YELLOW)

		# Check debug mods
		glob.debug = generalUtils.stringToBool(glob.conf.config["server"]["debug"])
		if glob.debug:
			consoleHelper.printColored("[!] Warning! Server running in debug mode!", bcolors.YELLOW)

		# Server port
		try:
			serverPort = int(glob.conf.config["server"]["port"])
		except:
			consoleHelper.printColored("[!] Invalid server port! Please check your config.ini and run the server again", bcolors.RED)

		# Make app
		glob.application = make_app()

		# Set up sentry
		try:
			glob.sentry = generalUtils.stringToBool(glob.conf.config["sentry"]["enable"])
			if glob.sentry:
				glob.application.sentry_client = AsyncSentryClient(glob.conf.config["sentry"]["dsn"], release=glob.VERSION)
			else:
				consoleHelper.printColored("[!] Warning! Sentry logging is disabled!", bcolors.YELLOW)
		except:
			consoleHelper.printColored("[!] Error while starting Sentry client! Please check your config.ini and run the server again", bcolors.RED)

		# Set up Datadog
		try:
			if generalUtils.stringToBool(glob.conf.config["datadog"]["enable"]):
				glob.dog = datadogClient.datadogClient(glob.conf.config["datadog"]["apikey"], glob.conf.config["datadog"]["appkey"])
			else:
				consoleHelper.printColored("[!] Warning! Datadog stats tracking is disabled!", bcolors.YELLOW)
		except:
			consoleHelper.printColored("[!] Error while starting Datadog client! Please check your config.ini and run the server again", bcolors.RED)

		# Connect to pubsub channels
		pubSub.listener(glob.redis, {
			"lets:beatmap_updates": beatmapUpdateHandler.handler(),
		}).start()
		# Prometheus port
		statsPort = None
		try:
			if glob.conf.config["prometheus"]["port"]:
				statsPort = int(glob.conf.config["prometheus"]["port"])
		except:
			consoleHelper.printColored("Invalid stats port! Please check your config.ini and run the server again", bcolors.YELLOW)
			raise

		if statsPort:
			consoleHelper.printColored("Stats exporter listening on localhost:{}".format(statsPort), bcolors.GREEN)
			prometheus_client.start_http_server(statsPort, addr="127.0.0.1")


		# Server start message and console output
		consoleHelper.printColored("> L.E.T.S. is listening for clients on {}:{}...".format(glob.conf.config["server"]["host"], serverPort), bcolors.GREEN)

		# Start Tornado
		glob.application.listen(serverPort, address=glob.conf.config["server"]["host"])
		tornado.ioloop.IOLoop.instance().start()
		
	finally:
		# Perform some clean up
		print("> Disposing server... ")
		glob.fileBuffers.flushAll()
		consoleHelper.printColored("Goodbye!", bcolors.GREEN)

	return 0

if __name__ == '__main__':
	raise SystemExit(main())
