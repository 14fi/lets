import personalBestCache
import personalBestCacheRX
import personalBestCacheAP
import userStatsCache
import userStatsCacheRX
import userStatsCacheAP
from helpers.cache import LeaderboardCache, PersonalBestCache
from common.ddog import datadogClient
from common.files import fileBuffer, fileLocks
from common.web import schiavo
import prometheus_client

try:
	with open("version") as f:
		VERSION = f.read().strip()
except:
	VERSION = "Unknown"
ACHIEVEMENTS_VERSION = 1

DATADOG_PREFIX = "lets"
BEATMAPS_PATH = '.data/beatmaps'
db = None
redis = None
conf = None
application = None
pool = None
pascoa = {}
achievements = []
no_check_md5s = {}
debug = False
sentry = False
bcrypt_cache = {}
def add_nocheck_md5(md5: str, status: int) -> None:
	"""Adds a beatmap MD5 to the list of md5s not to call osu api for.
	Also makes sure the list doesn't get too large so we dont run out of
	memory.
	"""

	no_check_md5s[md5] = status

	# What did I just make?
	if len(no_check_md5s) > 5000: del no_check_md5s[tuple(no_check_md5s)[0]]

stats = {
	"request_latency_seconds": prometheus_client.Histogram(
		"request_latency_seconds",
		"Time spent processing requests",
		("method", "endpoint")
	),
	"pp_calc_latency_seconds": prometheus_client.Histogram(
		"pp_calc_latency_seconds",
		"Time spent calculating pp",
		("game_mode",),
		buckets=(
			.0005, .001, .0025, .005, .0075, .01, .025, .05, .075,
			.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0, float("inf")
		)
	),

	"pp_calc_failures": prometheus_client.Counter(
		"pp_failures",
		"Number of scores that couldn't have their pp calculated",
		("game_mode",)
	),
	"replay_upload_failures": prometheus_client.Counter(
		"replay_failures",
		"Number of replays that couldn't be uploaded to S3",
	),
	"replay_download_failures": prometheus_client.Counter(
		"replay_download_failures",
		"Number of replays that couldn't be served",
	),
	"osu_api_failures": prometheus_client.Counter(
		"osu_api_failures",
		"Number of osu! api errors",
		("method",)
	),
	"osu_api_requests": prometheus_client.Counter(
		"osu_api_requests",
		"Number of requests towards the osu!api",
		("method",)
	),
	"submitted_scores": prometheus_client.Counter(
		"submitted_scores",
		"Number of submitted scores",
		("game_mode", "completed")
	),
	"served_leaderboards": prometheus_client.Counter(
		"served_leaderboards",
		"Number of served leaderboards",
		("game_mode",)
	),

	"in_progress_requests": prometheus_client.Gauge(
		"in_progress_requests",
		"Number of in-progress requests",
		("method", "endpoint")
	),
}
# Cache and objects
fLocks = fileLocks.fileLocks()
userStatsCache = userStatsCache.userStatsCache()
userStatsCacheRX = userStatsCacheRX.userStatsCacheRX()
userStatsCacheAP = userStatsCacheAP.userStatsCacheAP()
personalBestCache = personalBestCache.personalBestCache()
personalBestCacheRX = personalBestCacheRX.personalBestCacheRX()
personalBestCacheAP = personalBestCacheAP.personalBestCacheAP()
fileBuffers = fileBuffer.buffersList()
dog = datadogClient.datadogClient()
schiavo = schiavo.schiavo()
achievementClasses = {}
pb_cache = PersonalBestCache()
lb_cache = LeaderboardCache()
topPlays = {'relax': 9999, 'vanilla': 9999}
ignoreMapsCache = {} # getscores optimization
# Additional modifications
COMMON_VERSION_REQ = "1.2.1"
try:
	with open("common/version") as f:
		COMMON_VERSION = f.read().strip()
except:
	COMMON_VERSION = "Unknown"

time_since_last_debug_log = 0.0
