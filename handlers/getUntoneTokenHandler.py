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

			query = glob.db.fetch("SELECT token, user_id FROM untone_id_login_tokens WHERE client_key = %s ORDER BY id DESC LIMIT 1", [key])

			if query:
				# TODO: get username in the first query
				self.write(f'key|{query["token"]}|{userUtils.getUsername(query["user_id"])}')
				glob.db.execute("UPDATE untone_id_login_tokens SET client_key = '0', token = %s WHERE client_key = %s", [hashlib.md5(query["token"].encode('utf-8')).hexdigest(), key])
				return

			self.write("0")
		except Exception as e:
			log.error(e)
			self.write("-1")
