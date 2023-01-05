import os
import sys
import tornado.gen
import tornado.web
import json
from objects import glob
import traceback
from common.web import requestsManager
from common.log import logUtils as log
from constants import exceptions
from common import generalUtils
from common.ripple import userUtils
from common.ripple.userUtils import checkLogin as verify_password
import time
from secret.discord_hooks import Webhook
MODULE_NAME = "error_handler"

class handler(requestsManager.asyncRequestHandler):
	@tornado.web.asynchronous
	@tornado.gen.engine
	def asyncPost(self):
		#send the response immidiately so we arent delaying other requests as we do this
		self.write("")
		self.flush()
		self.finish()
		try:

			#make everything zero if nothing is sent so if the client dosent send something (old client version) we can still put the error in the db
			#this code is shit

			timestamp = 0
			timestamp = int(time.time()) # get the unix timestamp at the time the error was sent

			if "feedback" in self.request.arguments:
				feedback = str(self.get_argument("feedback"))
			else:
				feedback = "0"


			if "u" in self.request.arguments:
				username = str(self.get_argument("u"))
			else:
				username = "0"

			if username != "0":
				userid = userUtils.getID(username)
			else:
				return
		
			log.info(f"{userid} just sent an error!")

			passw = 0


			if "osumode" in self.request.arguments:
				osumode = str(self.get_argument("osumode"))
			else:
				osumode = "0"

			if "gamemode" in self.request.arguments:
				gamemode = str(self.get_argument("gamemode"))
			else:
				gamemode = "0"

			if "gametime" in self.request.arguments:
				gametime = int(self.get_argument("gametime"))
			else:
				gametime = 0

			if "audiotime" in self.request.arguments:
				audiotime = int(self.get_argument("audiotime"))
			else:
				audiotime = 0
			
			if "culture" in self.request.arguments:
				culture = str(self.get_argument("audiotime"))
			else:
				culture = "0"

			if "beatmap_id" in self.request.arguments:
				beatmap_id = int(self.get_argument("beatmap_id"))
			else:
				beatmap_id = 0

			if "beatmap_checksum" in self.request.arguments:
				beatmap_checksum = str(self.get_argument("beatmap_checksum"))
			else:
				beatmap_checksum = "0"
		
			if "exception" in self.request.arguments:
				exception = str(self.get_argument("exception"))
			else:
				exception = "0"

			if "stacktrace" in self.request.arguments:
				stacktrace = str(self.get_argument("stacktrace"))
			else:
				stacktrace = "0"

			if "iltrace" in self.request.arguments:
				iltrace = str(self.get_argument("iltrace"))
			else:
				iltrace = "0"

			if "soft" in self.request.arguments:
				soft = str(self.get_argument("soft"))
			else:
				soft = "0"

			if "beatmap_count" in self.request.arguments:
				beatmap_count = int(self.get_argument("beatmap_count"))
			else:
				beatmap_count = 0

			if "compatibility" in self.request.arguments:
				compatibility = int(self.get_argument("compatibility"))
			else:
				compatibility = 0

			if "ram" in self.request.arguments:
				ram = int(self.get_argument("ram"))
			else:
				ram = 0

			if "version" in self.request.arguments:
				version = str(self.get_argument("version"))
			else:
				version = "0"

			if "exehash" in self.request.arguments:
				exehash = str(self.get_argument("exehash"))
			else:
				exehash = "0"

			if "ss" in self.request.arguments:
				'''
				This appears when the client sends a bancho_monitor """"""anticheat"""""" screenshot,
				We won't save it, but we will send a notitication to the discord.
				'''
				webhook = Webhook(glob.conf.config["discord"]["ahook"],
				color=0xc32c74,
				footer="stupid anticheat")
				if glob.conf.config["discord"]["enable"]:
						webhook.set_title(title=f"Catched some cheater {username} ({userid})")
						webhook.set_desc(f'They just tried to send bancho_monitor!')
						webhook.set_footer(text="peppycode anticheat")
						webhook.post()

			else:
				pass


			if "config" in self.request.arguments:
				config1 = str(self.get_argument("config"))
				config = ""
				#don't save their password
				for line in config1.splitlines():
					if not (line.startswith('Password')):
						config = (f"{config}\n"+ f"{line}")
				config1 = "0"
			else:
				config = "0"
			if userid != 0:
				clientmodallowed = glob.db.fetch("SELECT clientmodallowed FROM users WHERE id = %s LIMIT 1", [userid])
				clientmodallowed = int(clientmodallowed["clientmodallowed"])
			else:
				# We don't care if they're not logged in.
				clientmodallowed = 1
			try:
				if not "cuttingedge" in version or not "beta" in version or "ce45" in version or "dev" in version:
					aversion = version.split(".")
					gamer = aversion[0].strip()
					gamed = gamer.lstrip("b")
					brazil = int(gamed)
				else:
					brazil = 20142014

			except:
				brazil = 20142014
			#TODO: make word and version black/whitelist
			if(
			"OsuMain" in stacktrace
			or "GameBase" in stacktrace 
			or "osu_common" in stacktrace 
			or "Bancho" in stacktrace 
			or brazil > 2015401 
			and "#=" not in stacktrace
			):
				if(
					not clientmodallowed == 1
				):
					webhook = Webhook(glob.conf.config["discord"]["ahook"],
					color=0xc32c74,
					footer="stupid anticheat")
					if glob.conf.config["discord"]["enable"]:
						webhook.set_title(title=f"Catched some cheater {username} ({userid})")
						webhook.set_desc(f"They sent a suspicious stacktrace! ```{stacktrace}``` osuver: {version}, exehash: {exehash} ")
						webhook.set_footer(text="peppycode anticheat")
						webhook.post()

		
			#put it in the db
			query = "INSERT INTO osuerrors (id, userid, time, username, osumode, gamemode, gametime, audiotime, culture, beatmap_id, beatmap_checksum, exception, feedback, stacktrace, iltrace, soft, beatmap_count, compatibility, ram, version, exehash, config) VALUES (NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s ,%s ,%s)"
			glob.db.execute(query, [userid, timestamp, username, osumode, gamemode, gametime, audiotime, culture, beatmap_id, beatmap_checksum, exception, feedback, stacktrace, iltrace, soft, beatmap_count, compatibility, ram, version, exehash, config])
			log.info(f"error inserted into db")
		except:
			# Try except block to avoid more errors
			try:
				log.error("Unknown error in {}!\n```{}\n{}```".format(MODULE_NAME, sys.exc_info(), traceback.format_exc()))
				if glob.sentry:
					yield tornado.gen.Task(self.captureException, exc_info=True)
			except:
				pass

