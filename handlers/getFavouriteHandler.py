import tornado.gen
import tornado.web

from common.web import requestsManager
from common.ripple import userUtils
from objects import glob

'''
Favourites handler by github.com/SakuruWasTaken
'''

class handler(requestsManager.asyncRequestHandler):
	@tornado.web.asynchronous
	@tornado.gen.engine
	def asyncGet(self):
		ip = self.getRequestIP()
		username = self.get_argument("u")
		password = self.get_argument("h")

		#We probably don't need this
		userID = userUtils.getID(username)
		if userID == 0:
			return
		if not userUtils.checkLogin(userID, password, ip):
			return

		favourites = glob.db.fetchAll("SELECT beatmapset_id FROM favourite_beatmaps WHERE userid = %s", [userID])

		self.write("\n".join([str(favourite["beatmapset_id"]) for favourite in favourites]).encode())



