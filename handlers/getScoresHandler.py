import json
import tornado.gen
import tornado.web
import time
from enum import IntEnum
from typing import Optional

from objects import beatmap
from objects import scoreboard
from common.constants import privileges
from common.log import logUtils as log
from common.ripple import userUtils
from common.web import requestsManager
from constants import exceptions, rankedStatuses
from objects import glob
from helpers.cache import LbCacheResult

from common.sentry import sentry
from common.ripple.userUtils import checkLogin as verify_password

BASE_QUERY = """
SELECT
	s.id,
	s.{scoring},
	s.max_combo,
	s.50_count,
	s.100_count,
	s.300_count,
	s.misses_count,
	s.katus_count,
	s.gekis_count,
	s.full_combo,
	s.mods,
	s.time,
	a.username,
	a.id,
	s.pp
FROM
	{table} s
INNER JOIN
	users a on s.userid = a.id
WHERE
	{where_clauses}
ORDER BY {order} DESC
LIMIT {limit}
"""

COUNT_QUERY = ("SELECT COUNT(*) FROM {table} s INNER JOIN users a on "
			   "s.userid = a.id WHERE {where_clauses}")

PB_BASE_QUERY = """
SELECT
	s.id,
	s.{scoring},
	s.max_combo,
	s.50_count,
	s.100_count,
	s.300_count,
	s.misses_count,
	s.katus_count,
	s.gekis_count,
	s.full_combo,
	s.mods,
	s.time,
	a.username,
	a.id,
	s.pp
FROM
	{table} s
INNER JOIN
	users a on s.userid = a.id
WHERE
	{where_clauses}
ORDER BY {order} DESC
LIMIT 1
"""

PB_COUNT_QUERY = """
SELECT
	COUNT(*) + 1
FROM
	{table} s
INNER JOIN
	users a on s.userid = a.id
WHERE
	{where_clauses}
ORDER BY {order} DESC
"""

class LeaderboardTypes(IntEnum):
	"""osu! in-game leaderboards"""

	LOCAL: int   = 0 # Not used online.
	TOP: int	 = 1 # Regular top leaderboards.
	MOD: int	 = 2 # Leaderboards for a specific mod combo.
	FRIENDS: int = 3 # Leaderboard containing only the user's friends.
	COUNTRY: int = 4 # Leaderboards containing only people from the user's nation.

def beatmap_header(bmap: beatmap.beatmap, has_lb: bool = True, score_count: int = 0) -> str:
	"""Creates a response header for a beatmap."""

	if not has_lb: return str(f"{bmap.rankedStatus}|false")

	return str((f"{bmap.rankedStatus}|false|{bmap.beatmapID}|{bmap.beatmapSetID}|{score_count}\n"
			f"0\n{bmap.songName}\n{bmap.rating}"))

def format_score(score: tuple, place: int) -> str:
	"""Formats a Database score tuple into a string format understood by the
	client."""

	return str((f"{score[0]}|{score[12]}|{round(score[1])}|{score[2]}|{score[3]}|"
			f"{score[4]}|{score[5]}|{score[6]}|{score[7]}|{score[8]}|"
			f"{score[9]}|{score[10]}|{score[13]}|{place}|{score[11]}|1"))

def glob_lb_from_cache(mode: int, rx: bool, bmap_md5: str) -> Optional[LbCacheResult]:
	"""Attempts to fetch global leaderboards from cache"""

	lb = glob.lb_cache.get_lb_cache(mode, rx)
	return lb.get((bmap_md5, 'g'))

def mod_lb_from_cache(mode: int, rx: bool, bmap_md5: str, mods: int) -> Optional[LbCacheResult]:
	"""Attempts to fetch mod-selected leaderboards from cache"""

	lb = glob.lb_cache.get_lb_cache(mode, rx)
	return lb.get((bmap_md5, 'm', mods,)) # strings to differentiate potential int overlaps

def friend_lb_from_cache(mode: int, rx: bool, bmap_md5: str, user_id: int) -> Optional[LbCacheResult]:
	"""Attempts to fetch a user's friend leaderboards from cache"""

	lb = glob.lb_cache.get_lb_cache(mode, rx)
	return lb.get((bmap_md5, 'f', user_id,)) # strings to differentiate potential int overlaps

def country_lb_from_cache(mode: int, rx: bool, bmap_md5: str, country: str) -> Optional[LbCacheResult]:
	"""Attempts to fetch a country's leaderboards from cache"""

	lb = glob.lb_cache.get_lb_cache(mode, rx)
	return lb.get((bmap_md5, 'c', country,))

def glob_lb_add(mode: int, rx: bool, bmap_md5: str, _lb: LbCacheResult) -> None:
	lb = glob.lb_cache.get_lb_cache(mode, rx)
	lb.cache((bmap_md5, 'g',), _lb)

def mod_lb_add(mode: int, rx: bool, bmap_md5: str, mods: int, _lb: LbCacheResult) -> None:
	lb = glob.lb_cache.get_lb_cache(mode, rx)
	lb.cache((bmap_md5, 'm', mods,), _lb)

def friend_lb_add(mode: int, rx: bool, bmap_md5: str, user_id: int, _lb: LbCacheResult) -> None:
	lb = glob.lb_cache.get_lb_cache(mode, rx)
	lb.cache((bmap_md5, 'f', user_id,), _lb)

def country_lb_add(mode: int, rx: bool, bmap_md5, country: str, _lb: LbCacheResult) -> None:
	lb = glob.lb_cache.get_lb_cache(mode, rx)
	lb.cache((bmap_md5, 'c', country,), _lb)

LB_MAINTENENCE_RES = "999|Leaderboard Maintenence|0|0|0|0|0|0|0|0|0|0|999|0|0|1"
MODULE_NAME = "get_scores"
REQUIRED_ARGS = ('c', 'f', 'i', 'm', 'us', 'ha', 'v', 'vv', 'mods')
ip = ""
md5 = ""
fileName = ""
beatmapSetID = ""
gameMode = ""
username = ""
password = ""
scoreboardType = 0
scoreboardVersion = 0
privs = 0

# Scoreboard type
isDonor = 0
country = 0
friends = 0
modsFilter = 0
#cdef int mods
fileNameShort = ""
data = ""
userID = 0
class handler(requestsManager.asyncRequestHandler):

	@tornado.web.asynchronous
	@tornado.gen.engine
	def asyncGet(self) -> None:
			#i dont understand why but if this is at the top it dosent compile
			from common.constants import mods

			"""
			Handler for /web/osu-osz2-getscores.php
			"""
			try:
				start_time = time.perf_counter()

				# Print arguments
				if glob.debug:
					requestsManager.printArguments(self)

				# TODO: Maintenance check

				# Check required arguments
				if not requestsManager.checkArguments(self.request.arguments, REQUIRED_ARGS):
					raise exceptions.invalidArgumentsException(MODULE_NAME)

				md5 = self.get_argument('c')

				if md5 in glob.ignoreMapsCache:
					# we already know this map can be ignored
					status = glob.ignoreMapsCache[md5]
					self.write(f'{status}|false|0|0|0\n0\n\n10.0\n'.encode())
					return

				username = self.get_argument('us')

				# Login and ban check
				user_id = userUtils.getID(username)
				if not user_id:
					self.write("error: pass")
					return
				if not userUtils.checkLogin(user_id, self.get_argument("ha", ''), self.getRequestIP()):
					self.write("error: pass")
					return

				if self.get_argument('vv') != '2':
					log.warning(f"{username} ({user_id}) tried to request a leaderboard with the wrong scoreboard version")

				score_mods = int(self.get_argument('mods'))
				privs = userUtils.getPrivileges(user_id)

				# Scoreboard type
				lb_type = LeaderboardTypes(int(self.get_argument('v')))

				# Create beatmap object and set its data
				set_id = int(self.get_argument('i'))
				bmap_file_name = self.get_argument('f')
				mode = int(self.get_argument('m'))

				bmap = beatmap.beatmap(md5, set_id, bmap_file_name)
				glob.redis.publish('peppy:update_cached_stats', user_id)

				if bmap.rankedStatus in (-1, 1):
					# we can ignore this md5 in the future
					# TODO: PERHAPS these could be cached on disk? even with
					# a timeout it might be worth the reduced api requests
					glob.ignoreMapsCache[md5] = bmap.rankedStatus
					self.write(beatmap_header(bmap, False).encode())

					time_taken_ms = (time.perf_counter() - start_time) * 1000
					log.info(f'Added {md5} to filtered leaderboard requests. ({time_taken_ms:.2f}ms elapsed)')
					return

				cache_hit = False
				limit = 500 if privs & privileges.USER_DONOR else 150
				rx = False

				lb = None

				if lb_type == LeaderboardTypes.TOP:
					lb_add_func = glob_lb_add
					_args = (mode, rx, md5,)
				elif lb_type == LeaderboardTypes.MOD:
					lb_add_func = mod_lb_add
					_args = (mode, rx, md5, score_mods,)
				elif lb_type == LeaderboardTypes.FRIENDS:
					lb_add_func = friend_lb_add
					_args = (mode, rx, md5, user_id,)
				elif lb_type == LeaderboardTypes.COUNTRY:
					lb_add_func = country_lb_add
					_args = (mode, rx, md5, userUtils.getCountry(user_id),)

				# If the map is qualified or pending, we always want to bypass the cache so we dont 
				# end up with maps being stuck as qualified or pending even though they no longer are.
				if not lb_type in (LeaderboardTypes.COUNTRY, LeaderboardTypes.FRIENDS) and not bmap.rankedStatus in (rankedStatuses.PENDING, rankedStatuses.QUALIFIED):
					if lb_type == LeaderboardTypes.TOP:
						lb = glob_lb_from_cache(mode, rx, md5)
					elif lb_type == LeaderboardTypes.MOD:
						lb = mod_lb_from_cache(mode, rx, md5, score_mods)

					if lb: cache_hit = True

					if not lb: # construct cache ourself
						where_clauses = [
							f'a.privileges & {privileges.USER_PUBLIC}',
							's.beatmap_md5 = %s',
							's.play_mode = %s',
							's.completed = 3',
						]

						if lb_type == LeaderboardTypes.MOD: where_clauses.append('s.mods = %s')

						where_vals = [
							md5,
							mode,
						]

						if lb_type == LeaderboardTypes.MOD: where_vals.append(score_mods)

						query_str = " AND ".join(where_clauses)
						query = BASE_QUERY.format(
							scoring='pp' if rx else 'score',
							table='scores_relax' if rx else 'scores',
							where_clauses=query_str,
							limit=500,
							order='pp' if bmap.rankedStatus in (rankedStatuses.RANKED, rankedStatuses.APPROVED) else 'score'
						)

						scores_db = glob.db.fetchAll(query, where_vals)

						count = len(scores_db)
						if count == 500:
							count = glob.db.fetch(
								COUNT_QUERY.format(
									table='scores_relax' if rx else 'scores',
									where_clauses=query_str
								), where_vals
							)

						lb = LbCacheResult(count, scores_db)
						lb_add_func(*_args, lb)
				else:
					#sboard: scoreboard = scoreboard.scoreboard(
						#username, mode, bmap,
						#setScores = True, country = lb_type == LeaderboardTypes.COUNTRY,
						#friends = lb_type == LeaderboardTypes.FRIENDS, mods = score_mods,
						#relax = rx
						sboard = scoreboard.scoreboard(
						username, mode, bmap, setScores=True, country = lb_type == LeaderboardTypes.COUNTRY, mods=score_mods, friends = lb_type == LeaderboardTypes.FRIENDS)

						lb = LbCacheResult(sboard.totalScores, sboard.score_rows)
						lb_add_func(*_args, lb)

				personal_best = glob.pb_cache.get_user_pb(mode, user_id, md5, rx)
				if not personal_best:
					# first attempt to get our scores from pre-existing score list

					for idx, _score in enumerate(lb.scores):
						score = tuple(_score.values())
						if score[13] == user_id:
							personal_best = format_score(score, idx + 1)

					if len(lb.scores) < 500 and not personal_best:
						personal_best = None
					elif not personal_best:
						where_clauses = (
							f'a.privileges & {privileges.USER_PUBLIC}',
							's.beatmap_md5 = %s',
							's.play_mode = %s',
							's.completed = 3',
							f'a.id = %s'
						)

						where_vals = (
							md5,
							mode,
							user_id,
						)

						query_str = " AND ".join(where_clauses)
						query = PB_BASE_QUERY.format(
							scoring='pp' if rx else 'score',
							table='scores_relax' if rx else 'scores',
							where_clauses=query_str,
							order='pp' if bmap.rankedStatus in (rankedStatuses.RANKED, rankedStatuses.APPROVED) else 'score'
						)

						personal_best = glob.db.fetch(query, where_vals)

						if personal_best:
							personal_vals = tuple(personal_best.values())
							place_clauses = (
								f"a.privileges & {privileges.USER_PUBLIC}",
								"s.beatmap_md5 = %s",
								"s.play_mode = %s",
								f"s.pp > {personal_vals[14]}",
								f"s.completed = 3",
							)

							query_str = " AND ".join(place_clauses)
							query = PB_COUNT_QUERY.format(
								table='scores_relax' if rx else 'scores',
								where_clauses=query_str,
								order='pp' if bmap.rankedStatus in (rankedStatuses.RANKED, rankedStatuses.APPROVED) else 'score'
							)

							where_vals = where_vals[:2]
							personal_place = glob.db.fetch(query, where_vals)

							personal_best = format_score(personal_vals, personal_place)
							glob.pb_cache.set_user_pb(mode, user_id, md5, personal_best, rx)

				# Now we do the actual fetching.
				res = "\n".join([
					beatmap_header(bmap, True, lb.count),
					personal_best or "",
					*[format_score(tuple(s.values()), idx + 1) for idx, s in enumerate(lb.scores[:limit])]
				])

				# Datadog stats
				glob.dog.increment(f'{glob.DATADOG_PREFIX}.served_leaderboards')

				redis_stuff = "lets:user_current_gamemode:{}".format(user_id)
				log.debug("Setting user gamemode key {}".format(redis_stuff))
				glob.redis.set(redis_stuff, "1")
					
				time_taken_ms = (time.perf_counter() - start_time) * 1000
				hit_or_miss = f'\x1b[0;9{2 if cache_hit else 1}mCache\x1b[0m' # i guess they never miss huh
                #thanks josh akatsuki for your outdated memes
				log.info(f'[{hit_or_miss}; {time_taken_ms:.2f}ms] "{username}" requested {lb_type!r} lb for "{bmap.songName}".')
				self.write(res.encode())
			except exceptions.invalidArgumentsException:
				self.write("error: meme")
			except exceptions.userBannedException:
				self.write("error: ban")
			except exceptions.loginFailedException:
				self.write("error: pass")
