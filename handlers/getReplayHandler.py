import os
import sys
import traceback

import tornado.gen
import tornado.web
from raven.contrib.tornado import SentryMixin

from common.log import logUtils as log
from common.ripple import userUtils
from common.web import requestsManager
from constants import exceptions
from objects import glob
from common.sentry import sentry

MODULE_NAME = "get_replay"
class handler(requestsManager.asyncRequestHandler):
	"""
	Handler for osu-getreplay.php
	"""
	@tornado.web.asynchronous
	@tornado.gen.engine
	@sentry.captureTornado
	def asyncGet(self):
		try:
			# OOF
			UsingRelax = False
			UsingAuto = False

			# Get request ip
			ip = self.getRequestIP()

			# Check arguments
			if not requestsManager.checkArguments(self.request.arguments, ["c", "u", "h"]):
				raise exceptions.invalidArgumentsException(MODULE_NAME)

			# Get arguments
			username = self.get_argument("u")
			password = self.get_argument("h")
			replayID = self.get_argument("c")

			# Login check
			userID = userUtils.getID(username)
			if userID == 0:
				raise exceptions.loginFailedException(MODULE_NAME, userID)
			if not userUtils.checkLogin(userID, password, ip):
				raise exceptions.loginFailedException(MODULE_NAME, username)
			if userUtils.check2FA(userID, ip):
				raise exceptions.need2FAException(MODULE_NAME, username, ip)

			# Get user ID
			current_gamemode_redis = "lets:user_current_gamemode:{}".format(userID)
			cgamemode = int(glob.redis.get(current_gamemode_redis))
			replayData = glob.db.fetch("SELECT scores.*, users.username AS uname FROM scores LEFT JOIN users ON scores.userid = users.id WHERE scores.id = %s", [replayID])
			if cgamemode == 3:
				log.debug("autopilot")
				UsingRelax = False
				usingAuto = True
				fileName = "{}_ap/replay_{}.osr".format(glob.conf.config["server"]["replayspath"], replayID)
			if cgamemode == 2:
				log.debug("relax")
				fileName = "{}_relax/replay_{}.osr".format(glob.conf.config["server"]["replayspath"], replayID)
				UsingRelax = True
				UsingAuto = False
			if cgamemode == 1:
				log.debug("std")
				UsingRelax = False
				UsingAuto = False
				fileName = "{}/replay_{}.osr".format(glob.conf.config["server"]["replayspath"], replayID)

			# Increment 'replays watched by others' if needed
			if replayData is not None:
				if username != replayData["uname"]:
					userUtils.incrementReplaysWatched(replayData["userid"], replayData["play_mode"])

			Play = "VANILLA"
			if UsingRelax:
				Play = "RELAX"
			if UsingAuto:
				Play = "AUTOPILOT"
			# Serve replay
			log.info("[{}] Serving replay_{}.osr".format(Play, replayID))

			if os.path.isfile(fileName):
				with open(fileName, "rb") as f:
					fileContent = f.read()
				self.write(fileContent)
			else:
				log.info("Replay {} doesn't exist".format(replayID))
				self.write("")
		except exceptions.invalidArgumentsException:
			pass
		except exceptions.need2FAException:
			pass
		except exceptions.loginFailedException:
			pass