from urllib.parse import urlencode

import requests
import tornado.gen
import tornado.web

from common.log import logUtils as log
from common.web import requestsManager


class handler(requestsManager.asyncRequestHandler):
	@tornado.web.asynchronous
	@tornado.gen.engine
	def asyncGet(self):
		'''
		We have disabled check-updates as the client dosen't use it with -devserver.
		The only case someone would use this is if they were on an old client using a switcher, 
		meaning they probably don't want to update their client in the first place.
		'''
		self.write("{\"response\": \"check-updates is disabled on this server.\"}")

