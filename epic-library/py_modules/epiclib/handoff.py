"""Sign in from your phone, the paste-a-code way: a one-time page the handheld serves on the local
network (see lanlink.py) links to Epic's own sign-in and takes the one-time authorization code Epic
shows. The device-code sign-in (device.py) is tried first because it needs no local page at all."""
from .lanlink import LanPage

LOGIN_URL = ("https://www.epicgames.com/id/login?redirectUrl="
             "https%3A%2F%2Fwww.epicgames.com%2Fid%2Fapi%2Fredirect%3FclientId%3D34a02cf8f4414e29b15921876da36f9a"
             "%26responseType%3Dcode")

FORM = """<ol><li>Open <a href="%LOGIN%" target="_blank" rel="noopener">Epic Games sign-in</a> and sign in
(this is Epic's own site).</li><li>Epic then shows a short block of text with <b>"authorizationCode"</b> in it.
Copy all of it, or just the 32-character code.</li><li>Paste it below and send it to your handheld. Codes work
once and expire after a few minutes.</li></ol>
<form method="post"><textarea name="key" rows="4" autocomplete="off" autocapitalize="off" spellcheck="false"
placeholder="Paste the code (or the whole text)" required></textarea>
<button type="submit">Send to handheld</button></form>%ERR%""".replace("%LOGIN%", LOGIN_URL)


class Handoff(LanPage):
    def __init__(self, on_key):
        """on_key(text) -> (ok, message), called from the server thread."""
        super().__init__("epic-library", "Epic Library", lambda err: FORM.replace("%ERR%", err),
                         lambda form: on_key((form.get("key") or [""])[0].strip()), ttl=600, max_body=4096)
