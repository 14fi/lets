import tornado.gen
import tornado.web

from common.web import requestsManager
from objects import glob
from common.ripple import userUtils


class handler(requestsManager.asyncRequestHandler):
    @tornado.web.asynchronous
    @tornado.gen.engine
    def asyncGet(self):
        egg = glob.db.fetchAll("SELECT id FROM users")

        for row in egg:
            userUtils.calculatePP(row["id"], 0)

        for row in egg:
            userUtils.calculatePP(row["id"], 1)

        for row in egg:
            userUtils.calculatePP(row["id"], 2)

        for row in egg:
            userUtils.calculatePP(row["id"], 3)

            
        self.write("done")