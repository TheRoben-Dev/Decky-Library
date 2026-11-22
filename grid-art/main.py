"""Grid Art - Decky backend.

Runs as the normal user (no "root" flag) and does nothing until the artwork browser asks:
- talks to the SteamGridDB API with the user's own API key (kept here, never sent to the UI);
- downloads the chosen picture and hands it to the frontend, which gives it to Steam through
  SteamClient.Apps.SetCustomArtworkForApp (Steam stores it in userdata/<id>/config/grid itself);
- for non-Steam shortcuts, saves icons under the plugin's data folder for SetShortcutIcon.
"""
import asyncio
import base64
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "py_modules"))

import decky  # noqa: E402

from gridart import sgdb  # noqa: E402
from gridart.store import Store  # noqa: E402

_store = None


def store() -> Store:
    global _store
    if _store is None:
        _store = Store(os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json"))
    return _store


def _public(s: Store) -> dict:
    return {**s.public(), "home": decky.DECKY_USER_HOME}


def _err(e: Exception) -> dict:
    status = getattr(e, "status", 0)
    if not isinstance(e, sgdb.ApiError):
        decky.logger.error(f"unexpected error: {e!r}")
    return {"ok": False, "error": str(e) or e.__class__.__name__, "status": status}


KEY_FILE = "key.txt"


def _import_key_file(s: Store) -> None:
    """Typing 32 characters on the Steam keyboard is miserable, so a key pasted into
    ~/homebrew/settings/Grid Art/key.txt (e.g. from Desktop Mode) is picked up once and the
    file removed."""
    path = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, KEY_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            key = re.sub(r"\s+", "", f.read(256))
    except OSError:
        return
    if re.fullmatch(r"[A-Za-z0-9]{16,64}", key):
        s.data["key"] = key
        s.save()
        sgdb.clear_cache()
        decky.logger.info("imported the API key from key.txt")
    try:
        os.unlink(path)
    except OSError:
        pass


def _read_local(path: str) -> dict:
    path = os.path.realpath(path or "")
    if not os.path.isfile(path):
        raise sgdb.ApiError("That file doesn't exist")
    if os.path.getsize(path) > sgdb.MAX_IMAGE:
        raise sgdb.ApiError("That file is larger than 25 MB")
    with open(path, "rb") as f:
        raw = f.read(sgdb.MAX_IMAGE + 1)
    ext = sgdb.image_type(raw)
    if not ext:
        raise sgdb.ApiError("Steam only takes PNG or JPEG artwork")
    return {"raw": raw, "ext": ext}


def _keep_icon(appid: int, ext: str, raw: bytes) -> str:
    """One icon file per shortcut under the plugin's data folder (Steam stores only the path)."""
    folder = os.path.join(decky.DECKY_PLUGIN_RUNTIME_DIR, "icons")
    os.makedirs(folder, exist_ok=True)
    for old in os.listdir(folder):
        if old.startswith(f"{int(appid)}."):
            os.unlink(os.path.join(folder, old))
    path = os.path.join(folder, f"{int(appid)}.{ext}")
    with open(path, "wb") as f:
        f.write(raw)
    return path


class Plugin:
    async def settings(self):
        s = store()
        await asyncio.to_thread(_import_key_file, s)
        return _public(s)

    async def set_key(self, key: str):
        key = re.sub(r"\s+", "", key or "")
        if not re.fullmatch(r"[A-Za-z0-9]{16,64}", key):
            return {"ok": False, "error": "That doesn't look like a SteamGridDB API key (32 letters and digits)."}
        checked = True
        try:
            await asyncio.to_thread(sgdb.api_get, "/search/autocomplete/portal", key, False)
        except sgdb.ApiError as e:
            if e.status in (401, 403):
                return {"ok": False, "error": "SteamGridDB rejected that key."}
            checked = False   # offline etc: keep it, the browser will say so if it's wrong
        s = store()
        s.data["key"] = key
        s.save()
        sgdb.clear_cache()
        return {"ok": True, "checked": checked, "settings": _public(s)}

    async def clear_key(self):
        s = store()
        s.data["key"] = ""
        s.save()
        sgdb.clear_cache()
        return _public(s)

    async def set_options(self, opts: dict):
        s = store()
        for k in ("nsfw", "humor", "epilepsy", "animated"):
            if k in opts:
                s.data[k] = bool(opts[k])
        if isinstance(opts.get("styles"), dict):
            for kind, allowed in sgdb.STYLES.items():
                v = opts["styles"].get(kind)
                if isinstance(v, list):
                    s.data["styles"][kind] = [x for x in v if x in allowed]
        s.save()
        return _public(s)

    async def assets(self, kind: str, appid: int, game_ids, shape: str, page: int):
        """Art for the Steam app id (game_ids empty/0), one SteamGridDB game, or the top games of a
        typed search term (up to MAX_TERM_GAMES, merged so every game gets a turn near the top)."""
        s = store()
        try:
            ids = game_ids if isinstance(game_ids, list) else [game_ids]
            ids = list(dict.fromkeys(int(x) for x in ids if int(x or 0) > 0))[:sgdb.MAX_TERM_GAMES]
            q = sgdb.build_query(
                kind, styles=s.data["styles"].get(kind, []), dimensions=sgdb.DIMENSIONS.get(shape, ""),
                animated=s.data["animated"] and kind != "icons", nsfw=s.data["nsfw"], humor=s.data["humor"],
                epilepsy=s.data["epilepsy"], page=page)
            if not ids:
                items = await asyncio.to_thread(sgdb.assets, kind, s.data["key"], appid=appid, query=q)
                return {"ok": True, "items": items, "page": page, "more": len(items) >= 50}
            lists, errors = [], []
            for gid in ids:
                try:
                    got = await asyncio.to_thread(sgdb.assets, kind, s.data["key"], game_id=gid, query=q)
                    lists.append([{**x, "game": gid} for x in got])
                except sgdb.ApiError as e:
                    if e.status in (401, 403) or len(ids) == 1:
                        raise
                    errors.append(e)   # one missing game shouldn't hide the others
            if errors and not lists:
                raise errors[0]
            return {"ok": True, "items": sgdb.interleave(lists), "page": page, "more": any(len(x) >= 50 for x in lists)}
        except Exception as e:
            return _err(e)

    async def search(self, term: str):
        try:
            return {"ok": True, "games": await asyncio.to_thread(sgdb.search, term, store().data["key"])}
        except Exception as e:
            return _err(e)

    async def image(self, url: str):
        try:
            d = await asyncio.to_thread(sgdb.download, url)
            d.pop("raw", None)
            return {"ok": True, **d}
        except Exception as e:
            return _err(e)

    async def save_icon(self, appid: int, url: str):
        """Non-Steam shortcuts take an icon by file path; keep one file per shortcut."""
        try:
            d = await asyncio.to_thread(sgdb.download, url)
            return {"ok": True, "path": await asyncio.to_thread(_keep_icon, appid, d["ext"], d["raw"])}
        except Exception as e:
            return _err(e)

    async def read_local(self, appid: int, slot: str, path: str):
        """A PNG/JPEG the user picked with Decky's file browser. Icons are copied next to the
        downloaded ones (Steam keeps the path), everything else goes to Steam as base64."""
        try:
            d = await asyncio.to_thread(_read_local, path)
            if slot == "icon":
                return {"ok": True, "path": await asyncio.to_thread(_keep_icon, appid, d["ext"], d["raw"])}
            return {"ok": True, "data": base64.b64encode(d["raw"]).decode("ascii"), "ext": d["ext"]}
        except Exception as e:
            return _err(e)

    async def applied(self, appid: int):
        return dict(store().data["applied"].get(str(int(appid)), {}))

    async def mark_applied(self, appid: int, kind: str, asset_id):
        s = store()
        cur = s.data["applied"].setdefault(str(int(appid)), {})
        if asset_id is None:
            cur.pop(kind, None)
        else:
            cur[kind] = asset_id
        if not cur:
            s.data["applied"].pop(str(int(appid)), None)
        s.save()
        return dict(cur)

    async def match(self, appid: int):
        """The SteamGridDB game the user picked for this app with the custom search, or None."""
        return store().data["matches"].get(str(int(appid)))

    async def set_match(self, appid: int, game):
        """Remember (game = {id, name}) or forget (game = None) a custom search pick."""
        s = store()
        k = str(int(appid))
        ids = []
        if isinstance(game, dict):
            raw = game.get("ids") if isinstance(game.get("ids"), list) else [game.get("id")]
            ids = list(dict.fromkeys(int(x) for x in raw if int(x or 0) > 0))[:sgdb.MAX_TERM_GAMES]
        if ids:
            names = game.get("names") if isinstance(game.get("names"), list) else []
            s.data["matches"][k] = {"id": ids[0], "ids": ids, "names": [str(x)[:200] for x in names[:len(ids)]],
                                    "name": str(game.get("name") or "")[:200], "term": bool(game.get("term"))}
        else:
            s.data["matches"].pop(k, None)
        s.save()
        return s.data["matches"].get(k)

    async def _main(self):
        decky.logger.info("Grid Art ready (idle until the artwork browser is opened)")

    async def _unload(self):
        pass
