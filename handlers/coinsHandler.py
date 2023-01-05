from helpers import aobaHelper
import tornado.gen
import tornado.web
from common.log import logUtils as log
from common.ripple import userUtils
from common.web import requestsManager
from objects import glob
from secret.discord_hooks import Webhook
'''
osu!coins handler made by github.com/SakuruWasTaken
This code was released under the GNU AGPL 3.0, please review the included copy of the licence.
Please do not remove this notice.
'''

MODULE_NAME = "coinsHandler"
class handler(requestsManager.asyncRequestHandler):
    @tornado.web.asynchronous
    @tornado.gen.engine
    def asyncGet(self):

        ip = self.getRequestIP()
        if not requestsManager.checkArguments(self.request.arguments, ["u", "cs", "action"]):
            return self.write("error: args")



        username = self.get_argument("u")
        password = self.get_argument("cs")

        userID = userUtils.getID(username)
        if userID == 0:
            self.write("error: auth")
            return
        if not userUtils.checkLogin(userID, password, ip):
            self.write("error: auth")
            return
        action = self.get_argument("action")
        coinAmountunparsed = glob.db.fetch(f"SELECT coins FROM users WHERE id = %s", [userID])
        coinAmount = int(coinAmountunparsed["coins"])

        if action == "use":
            glob.db.execute(f"UPDATE users SET coins = coins - 1 WHERE id = %s;", [userID])
        if action == "earn":
            glob.db.execute(f"UPDATE users SET coins = coins + 1 WHERE id = %s;", [userID])
        if action == "recharge":
            glob.db.execute(f"UPDATE users SET coins = 99 WHERE id = %s;", [userID])
        self.write(f"{coinAmount}")
        clientmodallowed = glob.db.fetch("SELECT clientmodallowed FROM users WHERE id = %s LIMIT 1", [userID])
        clientmodallowed = int(clientmodallowed["clientmodallowed"])
        gaming = aobaHelper.getOsuVer(userID).split(".")
        gamer = gaming[0].strip()
        gamed = gamer.lstrip("b")
        brazil = int(gamed) #come to brazil you motherfucker
        if brazil >= 20150403 and clientmodallowed != 1:
                if glob.conf.config["discord"]["enable"]:
                        webhook = Webhook(glob.conf.config["discord"]["ahook"],
                                color=0xadd836,
                                footer="[ Client AC ]")
                        webhook.set_title(title=f"Caught cheater {username} ({userID})")
                        webhook.set_desc(f"They tried to use osu!coins on a client which shouldn't have them!")
                        webhook.set_footer(text="ghostbusters")
                        webhook.post()
        return



