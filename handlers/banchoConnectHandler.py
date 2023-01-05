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
from secret.discord_hooks import Webhook

MODULE_NAME = "bancho_connect"
class handler(requestsManager.asyncRequestHandler):
	"""
	Handler for /web/bancho_connect.php
	"""
	@tornado.web.asynchronous
	@tornado.gen.engine
	@sentry.captureTornado
	def asyncGet(self):
		try:
			# Get request ip
			ip = self.getRequestIP()

			# Argument check
			if not requestsManager.checkArguments(self.request.arguments, ["u", "h"]):
				raise exceptions.invalidArgumentsException(MODULE_NAME)

			# Get user ID
			username = self.get_argument("u")
			userID = userUtils.getID(username)
			if userID is None:
				self.write("error: pass\n")
				return

			# Check login
			log.info("{} ({}) wants to connect".format(username, userID))
			if not userUtils.checkLogin(userID, self.get_argument("h"), ip):
				self.write("error: pass\n")
				return

			# Ban check
			if userUtils.isBanned(userID):
				return

			# Lock check
			if userUtils.isLocked(userID):
				return
			# 2FA check
			if userUtils.check2FA(userID, ip):
				self.write("error: verify\n")


			# Update latest activity
			userUtils.updateLatestActivity(userID)

			if "x" in self.request.arguments:
				if len(self.get_argument("x")) > 4:
					'''
					When "x" is found in the arguments, it means two things,
					1. "Monitor" has just been triggered (desktop screenshot """"""anticheat"""""")
					2. Files named "LL" (used by *a certain cheat website* for login data) have been found on the users computer.
					This should *NEVER* happen, but just incase it does, i'll send a notification to the discord.
					'''
					webhook = Webhook(glob.conf.config["discord"]["ahook"], #send shit to discord hq
					color=0xc32c74,
					footer="stupid anticheat")
					if glob.conf.config["discord"]["enable"]:
							webhook.set_title(title=f"Catched some cheater {username} ({userID})")
							webhook.set_desc(f'They just tried to send bancho_monitor and they have LL files!')
							webhook.set_footer(text="peppycode anticheat")
							webhook.post()


			# Get country and output it
			country = glob.db.fetch("SELECT country FROM users_stats WHERE id = %s", [userID])["country"]
			self.write(country)
		except exceptions.invalidArgumentsException:
			pass
		except exceptions.loginFailedException:
			self.write("error: pass\n")
		except exceptions.userBannedException:
			pass
		except exceptions.userLockedException:
			pass
		except exceptions.need2FAException:
			self.write("error: verify\n")
