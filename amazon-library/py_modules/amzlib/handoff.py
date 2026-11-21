"""Sign in from your phone: a one-time page the handheld serves on the local network (see
lanlink.py) links to Amazon's sign-in (made on the handheld, so the code it returns only works
here). After signing in, the phone pastes the amazon.com address it lands on back into the page.
Nothing is typed on the handheld."""
import html

from .lanlink import LanPage

FORM = """<ol><li>Open the Amazon sign-in in a <b>new tab</b> and sign in (2-step codes work as usual).</li>
<li>You end up on the amazon.com home page. Copy that page's <b>full address</b> from the address bar.</li>
<li>Come back to this tab, paste it below and send it to your handheld.</li></ol>
<a class="go" href="%LOGIN%" target="_blank" rel="noopener noreferrer">Open Amazon sign-in &#8599;</a>
<form method="post"><textarea name="key" autocomplete="off" autocapitalize="off" spellcheck="false"
placeholder="https://www.amazon.com/?openid.oa2.authorization_code=..." required></textarea>
<button type="submit">Send to handheld</button></form>
<p>If the Amazon Shopping app opens instead, long-press the button and pick <b>Open in browser</b>.</p>%ERR%"""


class Handoff(LanPage):
    def __init__(self, on_key, login_url):
        """on_key(text) -> (ok, message), called from the server thread.
        login_url() -> the Amazon sign-in address for this device."""
        super().__init__("amazon-library", "Amazon Library",
                         lambda err: FORM.replace("%LOGIN%", html.escape(login_url(), quote=True)).replace("%ERR%", err),
                         lambda form: on_key((form.get("key") or [""])[0].strip()), ttl=900, max_body=16384)
