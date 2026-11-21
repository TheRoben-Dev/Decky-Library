"""Sign in from your phone: a one-time page the handheld serves on the local network (see
lanlink.py) links to GOG's own sign-in. GOG then lands on a page whose address carries a one-time
code; pasting that address back sends the code to the handheld, which trades it for a GOG token.
The password never touches the handheld and nothing is typed on the on-screen keyboard."""
import html

from .api import LOGIN_URL
from .lanlink import LanPage

FORM = """<ol><li>Sign in to GOG (opens in a new tab):</li></ol>
<a class="go" href="%LOGIN%" target="_blank" rel="noopener noreferrer">Sign in to GOG</a>
<ol start="2"><li>After signing in, GOG shows a mostly empty page. Its address starts with
<b>embed.gog.com/on_login_success</b> and contains <b>code=</b>. Copy that whole address
(tap the address bar → Copy).</li><li>Come back to this tab, paste it below and send it. Codes expire after a few minutes.</li></ol>
<form method="post"><input name="code" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Paste the address (or just the code)" required>
<button type="submit">Send to handheld</button></form>%ERR%""".replace("%LOGIN%", html.escape(LOGIN_URL, quote=True))


class Handoff(LanPage):
    def __init__(self, on_key):
        """on_key(pasted text) -> (ok, message), called from the server thread."""
        super().__init__("gog-library", "GOG Library", lambda err: FORM.replace("%ERR%", err),
                         lambda form: on_key((form.get("code") or [""])[0].strip()), ttl=600, max_body=8192)
