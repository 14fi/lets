import tornado.gen
import tornado.web

from common.web import requestsManager
from common.log import logUtils as log
from objects import glob
from constants import exceptions


class handler(requestsManager.asyncRequestHandler):
	@tornado.web.asynchronous
	@tornado.gen.engine
	def asyncGet(self):
		MODULE_NAME = "CHECK_UPDATES"
		try:
			log.info("client checked for updates")
			if not requestsManager.checkArguments(self.request.arguments, ["f", "h", "t"]):
				raise exceptions.invalidArgumentsException(MODULE_NAME)

			hash = self.get_argument("h")

			query = glob.db.fetch("SELECT current FROM client_update WHERE hash = %s ORDER BY id DESC LIMIT 1", [hash])
			
			if query:
				if query["current"] == 0:
					self.write("1")
					return

			self.write("0")
		except Exception as e:
			log.error(f"Error in CHECK_UPDATES: {e}")
			self.write("0")
