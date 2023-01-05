from urllib.parse import urlencode

import requests
import tornado.gen
import tornado.web
from objects import glob
from common.log import logUtils as log
from common.web import requestsManager


class handler(requestsManager.asyncRequestHandler):
	@tornado.web.asynchronous
	@tornado.gen.engine
	def asyncGet(self):
		try:
			request_ip = self.getRequestIP()
			custom_backgrounds = glob.db.fetch("SELECT id, response FROM users_custom_seasonal WHERE ipv4 = %s OR ipv6 = %s ORDER BY id DESC LIMIT 1", [request_ip, request_ip])
			if custom_backgrounds:
				response = custom_backgrounds["response"]
			else:
				response = requests.get("https://osu.ppy.sh/web/osu-getseasonal.php").text
 
			self.write(response)
		except Exception as e:
			log.error("check-seasonal failed: {}".format(e))
			self.write("")
