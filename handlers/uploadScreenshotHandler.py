import os
import sys
import traceback

import tornado.gen
import tornado.web
from raven.contrib.tornado import SentryMixin
from imghdr import test_jpeg, test_png

from common.log import logUtils as log
from common.ripple import userUtils
from common.web import requestsManager
from constants import exceptions
from common import generalUtils
from objects import glob
from common.sentry import sentry

MODULE_NAME = "screenshot"
class handler(requestsManager.asyncRequestHandler):
	"""
	Handler for /web/osu-screenshot.php
	"""
	@tornado.web.asynchronous
	@tornado.gen.engine
	@sentry.captureTornado
	def asyncPost(self):
		try:
			if glob.debug:
				requestsManager.printArguments(self)

			# Make sure screenshot file was passed
			if "ss" not in self.request.files:
				raise exceptions.invalidArgumentsException(MODULE_NAME)

			# Check user auth because of sneaky people
			if not requestsManager.checkArguments(self.request.arguments, ["u", "p"]):
				raise exceptions.invalidArgumentsException(MODULE_NAME)
			username = self.get_argument("u")
			password = self.get_argument("p")
			ip = self.getRequestIP()
			userID = userUtils.getID(username)
			if not userUtils.checkLogin(userID, password):
				raise exceptions.loginFailedException(MODULE_NAME, username)
			if not userUtils.checkBanchoSession(userID, ip):
				raise exceptions.noBanchoSessionException(MODULE_NAME, username, ip)
			# Rate limit
			if glob.redis.get("lets:screenshot:{}".format(userID)) is not None:
				self.write("no")
				return
			glob.redis.set("lets:screenshot:{}".format(userID), 1, 60)

			# Get a random screenshot id
			found = False
			screenshotID = ""
			while not found:
				screenshotID = generalUtils.randomString(8)
				if not os.path.isfile("{}/{}.jpg".format(glob.conf.config["server"]["screenshotspath"], screenshotID)):
					found = True

			# Check if the filesize is not ridiculous. Through my checking I
			# have discovered all screenshots on rosu are below 500kb.
			if sys.getsizeof(self.request.files["ss"][0]["body"]) > 500000:
				return self.write("no")
			
			# Check if the file contents are actually fine (stop them uploading eg videos).
			if (not test_jpeg(self.request.files["ss"][0]["body"], 0))\
			and (not test_png(self.request.files["ss"][0]["body"], 0)):
				return self.write("no")


			# Write screenshot file to screenshots folder
			with open("{}/{}.jpg".format(glob.conf.config["server"]["screenshotspath"], screenshotID), "wb") as f:
				f.write(self.request.files["ss"][0]["body"])

			# Output
			log.info("New screenshot ({})".format(screenshotID))

			glob.db.execute("INSERT INTO users_screenshots (id, filename, user_id) VALUES (NULL, %s, %s)", [screenshotID, userID])

			# Return screenshot link
			self.write("{}/ss/{}.jpg".format(glob.conf.config["server"]["publiclets"], screenshotID))
		except exceptions.need2FAException:
			return self.write("no")
		except exceptions.invalidArgumentsException:
			return self.write("no")
		except exceptions.loginFailedException:
			return self.write("no")
