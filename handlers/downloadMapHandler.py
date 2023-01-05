import tornado.gen
import tornado.web

from common.web import requestsManager

MODULE_NAME = "direct_download"

#thank you josh akatsuki

class handler(requestsManager.asyncRequestHandler):
    """
    Handler for /d/
    """

    @tornado.web.asynchronous
    @tornado.gen.engine
    def asyncGet(self, beatmap_id_str: str) -> None:
        try:
            # TODO: re-add no-video support??
            no_video = int(beatmap_id_str.endswith("n"))
            if no_video:
                beatmap_id_str = beatmap_id_str[:-1]

            beatmap_id = int(beatmap_id_str)
            self.redirect(
                url=f"https://catboy.best/d/{beatmap_id}",
                permanent=False,
            )
        except ValueError:
            self.set_status(400)
            self.write("Invalid set id")