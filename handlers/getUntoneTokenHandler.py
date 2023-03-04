import tornado.gen
import tornado.web

from common.web import requestsManager
from common.log import logUtils as log
from objects import glob
import hashlib
from common.ripple import userUtils

class handler(requestsManager.asyncRequestHandler):
	@tornado.web.asynchronous
	@tornado.gen.engine
	def asyncGet(self):
		try:
			key = self.get_argument("k")

			query = glob.db.fetch("SELECT token_plaintext, user_id FROM untone_id_login_tokens WHERE client_key = %s ORDER BY id DESC LIMIT 1", [key])

			if query:
				# TODO: get username in the first query
				self.write(f'key|{query["token_plaintext"]}|{userUtils.getUsername(query["user_id"])}')
				glob.db.execute("UPDATE untone_id_login_tokens SET client_key = '0', token_plaintext = '0' WHERE client_key = %s", [key])
				return

			self.write("0")
		except Exception as e:
			log.error(e)
			self.write("-1")
