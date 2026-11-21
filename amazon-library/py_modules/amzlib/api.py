"""Amazon Games client: sign-in, library, downloads, free games.

Talks to the same services the official Amazon Games app uses. The protocol (endpoints, headers,
request bodies) follows what the open-source Nile client documents
(https://github.com/imLinguin/nile); this is an independent implementation using only the
Python standard library. Nothing here runs unless the plugin asks: there is no background polling.
Certificate checks are never disabled, and tokens only ever go to amazon.com hosts.
"""
import base64
import hashlib
import json
import os
import secrets
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

AMAZON_API = "https://api.amazon.com"
DISTRIBUTION = "https://gaming.amazon.com/api/distribution/v2/public"
ENTITLEMENTS = "https://gaming.amazon.com/api/distribution/entitlements"
GRAPHQL = "https://gaming.amazon.com/graphql"
SDK_CHANNEL = DISTRIBUTION + "/download/channel/87d38116-4cbf-4af0-a371-a5b498975346"
MARKETPLACE = "ATVPDKIKX0DER"
DEVICE_TYPE = "A2UMVHOX7UP4V7"
APP_NAME = "AGSLauncher for Windows"
APP_VERSION = "1.0.0"
UA = "AGSLauncher/1.0.0"
LAUNCHER_UA = "com.amazon.agslauncher.win/3.0.9202.1"
KEY_ID = "d5dc8b8b-86c8-4fc4-ae93-18c0def5314d"
CLAIMS_URL = "https://luna.amazon.com/claims/home"
MAX_JSON = 32_000_000
MAX_IMAGE = 10 * 1024 * 1024
REFRESH_MARGIN = 300            # refresh the access token this many seconds before it expires

_CA_FILES = ("/etc/pki/tls/certs/ca-bundle.crt", "/etc/ssl/certs/ca-certificates.crt", "/etc/ssl/cert.pem")
_ctx = None


class ApiError(Exception):
    def __init__(self, msg: str, status: int = 0):
        super().__init__(msg)
        self.status = status


def context() -> ssl.SSLContext:
    global _ctx
    if _ctx:
        return _ctx
    for f in _CA_FILES:
        if os.path.exists(f):
            _ctx = ssl.create_default_context(cafile=f)
            return _ctx
    _ctx = ssl.create_default_context()
    return _ctx


def _opener():
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=context()))


def https(url: str) -> bool:
    u = urllib.parse.urlparse(url or "")
    return u.scheme == "https" and bool(u.hostname)


def _message(body: bytes, status: int, what: str) -> str:
    try:
        d = json.loads(body.decode("utf-8", "replace"))
        if isinstance(d, dict):
            err = d.get("response", {}).get("error") if isinstance(d.get("response"), dict) else None
            msg = (err or {}).get("message") if isinstance(err, dict) else None
            msg = msg or d.get("message") or d.get("error_description") or d.get("Message")
            if isinstance(msg, str) and msg:
                return f"{what}: {msg[:200]}"
    except Exception:
        pass
    if status in (401, 403):
        return "Amazon signed this device out. Sign in again."
    if status == 429:
        return "Amazon asked us to slow down; try again in a minute"
    return f"{what} answered HTTP {status}"


def request(url: str, body=None, headers: dict | None = None, timeout: float = 30, what: str = "Amazon",
            raw: bool = False, limit: int = MAX_JSON):
    """POSTs JSON when body is given (or sends a prepared str/bytes body), GETs otherwise."""
    h = {"User-Agent": UA, **(headers or {})}
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body)).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=h, method="POST" if data is not None else "GET")
    try:
        with _opener().open(req, timeout=timeout) as r:
            out = r.read(limit + 1)
    except urllib.error.HTTPError as e:
        raise ApiError(_message(e.read(4096), e.code, what), e.code) from None
    except urllib.error.URLError as e:
        raise ApiError(f"Can't reach {what} ({getattr(e, 'reason', e)})") from None
    except TimeoutError:
        raise ApiError(f"{what} didn't answer in time") from None
    if len(out) > limit:
        raise ApiError(f"{what} sent an unexpectedly large answer")
    if raw:
        return out
    try:
        return json.loads(out.decode("utf-8"))
    except ValueError:
        raise ApiError(f"{what} sent something that isn't JSON") from None


# ------------------------------------------------------------------ sign-in

def new_login() -> dict:
    """A fresh PKCE login: the URL to open, plus what's needed to finish it (kept on the device)."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    serial = uuid.uuid4().hex.upper()
    client_id = f"{serial}#{DEVICE_TYPE}".encode("ascii").hex()
    args = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.mode": "checkid_setup",
        "openid.oa2.scope": "device_auth_access",
        "openid.ns.oa2": "http://www.amazon.com/ap/ext/oauth/2",
        "openid.oa2.response_type": "code",
        "openid.oa2.code_challenge_method": "S256",
        "openid.oa2.client_id": f"device:{client_id}",
        "language": "en_US",
        "marketPlaceId": MARKETPLACE,
        "openid.return_to": "https://www.amazon.com",
        "openid.pape.max_auth_age": 0,
        "openid.assoc_handle": "amzn_sonic_games_launcher",
        "pageId": "amzn_sonic_games_launcher",
        "openid.oa2.code_challenge": challenge,
    }
    return {"url": "https://amazon.com/ap/signin?" + urllib.parse.urlencode(args), "verifier": verifier,
            "serial": serial, "client_id": client_id, "at": time.time()}


def code_from(text: str) -> str:
    """The authorization code from the amazon.com address you land on after signing in
    (or the bare code itself)."""
    text = (text or "").strip()
    if "authorization_code" in text:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(text).query)
        vals = q.get("openid.oa2.authorization_code") or []
        if vals:
            return vals[0].strip()
        # Some phones mangle the URL; take the value by hand.
        part = text.split("openid.oa2.authorization_code=", 1)[-1]
        return urllib.parse.unquote(part.split("&", 1)[0]).strip()
    return text if text and len(text) < 200 and " " not in text and "/" not in text else ""


def register(code: str, login: dict) -> dict:
    """Trades the sign-in code for device tokens. Returns the stored auth record."""
    body = {
        "auth_data": {
            "authorization_code": code, "client_domain": "DeviceLegacy", "client_id": login["client_id"],
            "code_algorithm": "SHA-256", "code_verifier": login["verifier"], "use_global_authentication": False,
        },
        "registration_data": {
            "app_name": APP_NAME, "app_version": APP_VERSION, "device_model": "Windows", "device_name": None,
            "device_serial": login["serial"], "device_type": DEVICE_TYPE, "domain": "Device",
            "os_version": "10.0.19044.0",
        },
        "requested_extensions": ["customer_info", "device_info"],
        "requested_token_type": ["bearer", "mac_dms"],
        "user_context_map": {},
    }
    d = request(f"{AMAZON_API}/auth/register", body, what="Amazon sign-in")
    ok = (d.get("response") or {}).get("success") if isinstance(d, dict) else None
    if not isinstance(ok, dict):
        raise ApiError("Amazon didn't accept that sign-in. Start again and paste the address right after signing in.")
    bearer = ok.get("tokens", {}).get("bearer", {})
    cust = ok.get("extensions", {}).get("customer_info", {})
    dev = ok.get("extensions", {}).get("device_info", {})
    if not bearer.get("access_token") or not bearer.get("refresh_token"):
        raise ApiError("Amazon sign-in returned no tokens")
    return {
        "access_token": bearer["access_token"], "refresh_token": bearer["refresh_token"],
        "expires": time.time() + int(bearer.get("expires_in") or 3600),
        "serial": dev.get("device_serial_number") or login["serial"],
        "user": {"id": str(cust.get("user_id", "")), "name": str(cust.get("given_name") or cust.get("name") or "")},
    }


def refresh(auth: dict) -> dict:
    body = {"source_token": auth["refresh_token"], "source_token_type": "refresh_token",
            "requested_token_type": "access_token", "app_name": APP_NAME, "app_version": APP_VERSION}
    d = request(f"{AMAZON_API}/auth/token", body, what="Amazon sign-in")
    if not isinstance(d, dict) or not d.get("access_token"):
        raise ApiError("Amazon signed this device out. Sign in again.", 401)
    return {**auth, "access_token": d["access_token"], "expires": time.time() + int(d.get("expires_in") or 3600)}


def needs_refresh(auth: dict) -> bool:
    return time.time() > float(auth.get("expires") or 0) - REFRESH_MARGIN


def deregister(auth: dict) -> None:
    try:
        request(f"{AMAZON_API}/auth/deregister", {"request_metadata": {"app_name": APP_NAME, "app_version": APP_VERSION}},
                headers={"Authorization": f"bearer {auth['access_token']}"}, timeout=10, what="Amazon")
    except ApiError:
        pass   # signing out locally works regardless


# ------------------------------------------------------------------ library

def _distribution(target: str, token: str, body: dict, url: str = DISTRIBUTION) -> dict:
    headers = {"X-Amz-Target": target, "x-amzn-token": token, "UserAgent": LAUNCHER_UA,
               "Content-Type": "application/json", "Content-Encoding": "amz-1.0"}
    d = request(url, body, headers=headers, what="Amazon Games")
    if not isinstance(d, dict):
        raise ApiError("Amazon Games sent an unexpected answer")
    return d


def _detail(e: dict) -> dict:
    p = e.get("product") or {}
    pd = p.get("productDetail") or {}
    det = pd.get("details") or {}
    title = str(p.get("title") or det.get("title") or "").strip()
    shots = det.get("screenshots") if isinstance(det.get("screenshots"), list) else []
    return {
        "id": str(p.get("id") or ""),
        "entitlement": str(e.get("id") or ""),
        "sku": str(p.get("sku") or ""),
        "title": title or "Untitled game",
        "icon": str(pd.get("iconUrl") or ""),
        "cover": str(det.get("backgroundUrl2") or pd.get("iconUrl") or ""),
        "background": str(det.get("backgroundUrl1") or det.get("backgroundUrl2") or ""),
        "logo": str(det.get("logoUrl") or ""),
        "short": str(det.get("shortDescription") or "")[:300],
        "developer": str(det.get("developer") or ""),
        "publisher": str(det.get("publisher") or ""),
        "genres": [str(g) for g in (det.get("genres") or [])][:4] if isinstance(det.get("genres"), list) else [],
        "released": str(det.get("releaseDate") or "")[:10],
        "screenshot": str(shots[0]) if shots else "",
        "added": str(e.get("grantTime") or e.get("createdDate") or ""),
        # Store-page details (all from the same entitlement answer, no extra requests).
        "description": _text(det.get("shortDescription"))[:4000],
        "screenshots": _urls(shots),
        "modes": _strs(det.get("gameModes")),
        "rating": " · ".join(x for x in (_rating("ESRB", det.get("esrbRating") or det.get("esrbRatins")),
                                         _rating("PEGI", det.get("pegiRating"))) if x),
        "website": _site(det.get("websites")),
    }


def _text(v) -> str:
    """Plain text from a description that may carry HTML (<br>, <p>, entities)."""
    import html as _html
    import re as _re
    t = str(v or "")
    t = _re.sub(r"(?i)<br\s*/?>|</p>|</li>", "\n", t)
    t = _re.sub(r"<[^>]+>", "", t)
    t = _re.sub(r"\n{3,}", "\n\n", _html.unescape(t))
    return t.strip()


def _shots(oa) -> list:
    if isinstance(oa, list):
        oa = oa[0] if oa and isinstance(oa[0], dict) else {}
    v = oa.get("screenshots") if isinstance(oa, dict) else None
    return v if isinstance(v, list) else []


def _urls(v, n: int = 12) -> list:
    return [str(u) for u in (v if isinstance(v, list) else []) if isinstance(u, str) and https(u)][:n]


def _strs(v, n: int = 6) -> list:
    return [str(x).replace("_", " ").title() if str(x).isupper() else str(x) for x in (v if isinstance(v, list) else [])
            if isinstance(x, (str, int))][:n]


def _rating(org: str, v) -> str:
    v = str(v or "").strip()
    return f"{org} {v.replace('_', ' ').title() if v.isupper() else v}" if v and v.lower() not in ("none", "null", "rp") else ""


def _site(w) -> str:
    if isinstance(w, dict):
        for k in ("official", "support"):
            if isinstance(w.get(k), str) and https(w[k]):
                return w[k]
    return w if isinstance(w, str) and https(w) else ""


def entitlements(token: str, serial: str) -> list:
    """Every game on the account, newest grant first where Amazon says when."""
    out, seen, next_token = [], set(), None
    for _ in range(200):          # 10 000 games
        body = {"Operation": "GetEntitlements", "clientId": "Sonic", "syncPoint": None, "nextToken": next_token,
                "maxResults": 50, "productIdFilter": None, "keyId": KEY_ID,
                "hardwareHash": hashlib.sha256(serial.encode()).hexdigest().upper()}
        d = _distribution("com.amazon.animusdistributionservice.entitlement.AnimusEntitlementsService.GetEntitlements",
                          token, body, ENTITLEMENTS)
        for e in d.get("entitlements") or []:
            if not isinstance(e, dict):
                continue
            g = _detail(e)
            if g["id"] and g["id"] not in seen:
                seen.add(g["id"])
                out.append(g)
        next_token = d.get("nextToken")
        if not next_token:
            break
    out.sort(key=lambda g: g["added"], reverse=True)
    return out


def game_download(token: str, entitlement_id: str) -> dict:
    """{downloadUrl, versionId} for the current build."""
    d = _distribution("com.amazon.animusdistributionservice.external.AnimusDistributionService.GetGameDownload",
                      token, {"entitlementId": entitlement_id, "Operation": "GetGameDownload"})
    if not https(d.get("downloadUrl", "")):
        raise ApiError("Amazon didn't offer a download for this game")
    return {"url": d["downloadUrl"], "version": str(d.get("versionId") or "")}


def live_versions(token: str, product_ids: list) -> dict:
    d = _distribution("com.amazon.animusdistributionservice.external.AnimusDistributionService.GetLiveVersionIds",
                      token, {"adgProductIds": product_ids, "Operation": "GetLiveVersions"})
    m = d.get("adgProductIdToVersionIdMap")
    return {str(k): str(v) for k, v in m.items()} if isinstance(m, dict) else {}


def sub_url(base: str, *parts: str) -> str:
    u = urllib.parse.urlparse(base)
    return urllib.parse.urlunparse(u._replace(path=u.path.rstrip("/") + "/" + "/".join(parts)))


def sdk_channel() -> dict:
    """The Amazon Games app's own download channel (public). Some games load its Fuel/Games SDK DLLs."""
    d = request(SDK_CHANNEL, what="Amazon Games")
    if not isinstance(d, dict) or not https(d.get("downloadUrl", "")):
        raise ApiError("Amazon didn't offer the Amazon Games SDK")
    return {"url": d["downloadUrl"], "version": str(d.get("versionId") or "")}


# ------------------------------------------------------------------ free games (Prime Gaming / Luna)

OFFERS_BASIC = ('{"query":"query{primeOffers(dateOverride:null,group:null){catalogId,title,startTime,endTime,'
                'deliveryMethod,productList{sku,vendor},content{publisher},assets{location2x},'
                'self{eligibility{canClaim,isClaimed,isPrimeGaming,maxOrdersExceeded,inRestrictedMarketplace,'
                'missingRequiredAccountLink}},game{id,description,developerName,publisher,genres}}}"}')
OFFERS_QUERY = ('{"query":"query{primeOffers(dateOverride:null,group:null){catalogId,title,startTime,endTime,'
                'deliveryMethod,productList{sku,vendor},content{publisher},assets{location2x},'
                'offerAssets{screenshots{location}},'
                'self{eligibility{canClaim,isClaimed,isPrimeGaming,maxOrdersExceeded,inRestrictedMarketplace,'
                'missingRequiredAccountLink}},game{id,description,developerName,publisher,genres,gameModes,'
                'releaseDate,esrb,pegi,website,logoImage{defaultMedia{src1x,src2x}},'
                'background{defaultMedia{src1x,src2x}}}}}"}')


def _offers_request(token: str, query: str) -> list:
    d = request(GRAPHQL, query, headers={
        "User-Agent": "GraphQL.Client/3.2.2.0", "client-id": "AmazonGamesApp", "prime-gaming-language": "en-US",
        "Content-Type": "application/json; charset=utf-8", "x-amz-access-token": token}, what="Prime Gaming")
    offers = ((d or {}).get("data") or {}).get("primeOffers") if isinstance(d, dict) else None
    if not isinstance(offers, list):
        errs = (d or {}).get("errors") if isinstance(d, dict) else None
        raise ApiError("Amazon's free games list isn't available right now" + (f" ({errs[0].get('message', '')[:120]})"
                       if isinstance(errs, list) and errs and isinstance(errs[0], dict) else ""))
    return offers


def prime_offers(token: str) -> list:
    """This month's free games with Prime, with store-page details (description, screenshots,
    modes, ratings). Only "direct entitlement" offers land in the Amazon library; the rest are
    codes for other stores, shown as such. Falls back to the short query if Amazon rejects a field."""
    try:
        offers = _offers_request(token, OFFERS_QUERY)
    except ApiError as e:
        if e.status in (401, 403):
            raise
        offers = _offers_request(token, OFFERS_BASIC)
    out = []
    for o in offers:
        if not isinstance(o, dict):
            continue
        elig = ((o.get("self") or {}).get("eligibility") or {})
        game = o.get("game") or {}
        img = ((o.get("assets") or [{}])[0] or {}).get("location2x", "") if isinstance(o.get("assets"), list) and o["assets"] else ""
        out.append({
            "id": str(o.get("catalogId") or ""), "title": str(o.get("title") or ""),
            "ends": str(o.get("endTime") or "")[:10], "direct": o.get("deliveryMethod") == "DIRECT_ENTITLEMENT",
            "image": str(img or ""), "publisher": str((o.get("content") or {}).get("publisher") or game.get("publisher") or ""),
            "short": _text(game.get("description"))[:300],
            "description": _text(game.get("description"))[:4000],
            "screenshots": _urls([x.get("location") for x in _shots(o.get("offerAssets")) if isinstance(x, dict)]),
            "developer": str(game.get("developerName") or ""),
            "genres": _strs(game.get("genres"), 4), "modes": _strs(game.get("gameModes")),
            "released": str(game.get("releaseDate") or "")[:10],
            "rating": " · ".join(x for x in (_rating("ESRB", game.get("esrb")), _rating("PEGI", game.get("pegi"))) if x),
            "website": _site(game.get("website")),
            "logo": _media(game.get("logoImage")), "background": _media(game.get("background")),
            "claimed": bool(elig.get("isClaimed")), "can_claim": bool(elig.get("canClaim")),
            "prime": bool(elig.get("isPrimeGaming")), "link_needed": bool(elig.get("missingRequiredAccountLink")),
        })
    out = [o for o in out if o["id"] and o["title"]]
    out.sort(key=lambda o: (not o["direct"], o["claimed"], o["title"].lower()))
    return out


def _media(m) -> str:
    d = (m or {}).get("defaultMedia") if isinstance(m, dict) else None
    if isinstance(d, dict):
        for k in ("src2x", "src1x"):
            if isinstance(d.get(k), str) and https(d[k]):
                return d[k]
    return ""


# ------------------------------------------------------------------ images

def image(url: str) -> tuple:
    """(bytes, ext) of an artwork image, for the Steam artwork the frontend composes."""
    if not https(url):
        raise ApiError("No image")
    data = request(url, what="Image server", raw=True, limit=MAX_IMAGE, timeout=20)
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return data, "png"
    if data[:3] == b"\xff\xd8\xff":
        return data, "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return data, "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return data, "gif"
    raise ApiError("Not an image Steam can use")
