import tornado.gen
import tornado.web

from common.ripple import userUtils
from common.web import requestsManager

MODULE_NAME = "osuGetFriendsHandler"
class handler(requestsManager.asyncRequestHandler):
    """
    Handler for /web/osu-getfriends.php

    Handler by @KotRikD
    """
    @tornado.web.asynchronous
    @tornado.gen.engine
    def asyncGet(self):
        ip = self.getRequestIP()
        if not requestsManager.checkArguments(self.request.arguments, ["h", "u"]):
            return

        username = self.get_argument("u")
        password = self.get_argument("h")

        userID = userUtils.getID(username)
        if userID == 0:
            return
        if not userUtils.checkLogin(userID, password, ip):
            return
        
        friends_list = userUtils.getFriendList(userID)
        if friends_list[0] == 0:
            return self.write('')
        
        return self.write('\n'.join(str(x) for x in friends_list))
