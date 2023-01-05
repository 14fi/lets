from time import time

import tornado.gen
import tornado.web
from common.log import logUtils as log
from common.ripple import userUtils
from common.web import requestsManager
from constants import exceptions
from objects import glob

MODULE_NAME = 'osu_session'
class handler(requestsManager.asyncRequestHandler):
    """
    Handler for /web/osu-session.php
    """
	# thank you very much josh akatsuki
    @tornado.web.asynchronous
    @tornado.gen.engine
    def asyncPost(self) -> None:

        if not requestsManager.checkArguments(self.request.arguments, ['u', 'h', 'action']):
            raise exceptions.invalidArgumentsException(MODULE_NAME)

        if self.get_argument('action') != 'submit':
            self.write('Not yet')
            return

        content = self.get_argument("content")

        try:
            glob.db.execute('INSERT INTO osu_session (id, user, ip, content, time) VALUES (NULL, %s, %s, %s, %s);', [
                userUtils.getID(self.get_argument('u')),
                self.getRequestIP(),
                content,
                time()
            ])
        except: log.error(f'osu session failed to save!\n\n**Content**\n{content}')

        self.write("Not yet")
        return