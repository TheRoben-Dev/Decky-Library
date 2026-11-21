"""Sign in from your phone: the user pastes their itch.io API key on a one-time page the handheld
serves on the local network (see lanlink.py), so nothing is typed on the on-screen keyboard."""
from .lanlink import LanPage

FORM = """<ol><li>Open <a href="https://itch.io/user/settings/api-keys" target="_blank" rel="noopener noreferrer">itch.io → Settings → API keys</a>
and sign in if asked.</li><li>Press <b>Generate new API key</b>, then copy the key.</li><li>Come back to this tab, paste it below and send it to your handheld.</li></ol>
<form method="post"><input name="key" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Paste your API key" required>
<button type="submit">Send to handheld</button></form>%ERR%"""


class Handoff(LanPage):
    def __init__(self, on_key):
        """on_key(key) -> (ok, message), called from the server thread."""
        super().__init__("itch-library", "Itch Library", lambda err: FORM.replace("%ERR%", err),
                         lambda form: on_key((form.get("key") or [""])[0].strip()), ttl=600, max_body=4096)
