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
		beatmapset = self.get_argument("a")

		userID = userUtils.getID(username)
		if userID == 0:
			return
		if not userUtils.checkLogin(userID, password, ip):
			return

		favourite = glob.db.fetch("SELECT 1 FROM favourite_beatmaps WHERE userid = %s AND beatmapset_id = %s", [userID, beatmapset])

		if favourite:
			self.write("You've already favourited this beatmap!")
			return

		glob.db.execute("INSERT INTO favourite_beatmaps (userid, beatmapset_id) VALUES(%s, %s);", [userID, beatmapset])
		self.write("")



