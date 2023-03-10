import tornado.gen
import tornado.web

from common.web import requestsManager


class handler(requestsManager.asyncRequestHandler):
	@tornado.web.asynchronous
	@tornado.gen.engine
	def asyncGet(self):
		with open("version.txt", "rb") as f:
			data = f.read()
			self.write(data)