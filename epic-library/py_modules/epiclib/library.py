"""Turns Legendary's owned-games JSON (megabytes of catalog metadata) into the few fields the UI
needs, and works out what is installed and what has an update."""

IMAGE_TALL = ("DieselGameBoxTall", "OfferImageTall", "DieselStoreFrontTall", "Thumbnail", "CodeRedemption_340x440")
IMAGE_WIDE = ("DieselGameBox", "OfferImageWide", "DieselStoreFrontWide", "featuredMedia")
IMAGE_LOGO = ("DieselGameBoxLogo", "ProductLogo")


def _first(imgs: dict, names: tuple) -> str:
    for n in names:
        if imgs.get(n):
            return imgs[n]
    return ""


def _attr(ca: dict, key: str) -> str:
    v = ca.get(key)
    return str(v.get("value") or "") if isinstance(v, dict) else ""


# Epic catalog category paths of things that aren't games: Unreal Engine / Fab assets, engine
# plugins, the engine itself, software and add-ons. An item is a game if any of its categories is
# "games" (or below it); items without categories are kept, since Legendary only lists apps.
NON_GAME = ("engines", "assets", "plugins", "digitalextras", "applications", "software", "addons", "tools",
            "unrealengine", "fab", "audio", "music", "videos")
NON_GAME_NS = ("ue", "89efe5924d3d467c839449ab6ab52e7f")   # Unreal Engine marketplace / Fab


def is_game(md: dict) -> bool:
    if (md.get("namespace") or "") in NON_GAME_NS:
        return False
    paths = [str(c.get("path") or "").lower() for c in md.get("categories") or [] if isinstance(c, dict)]
    if not paths:
        return True
    if any(p == "games" or p.startswith("games/") for p in paths):
        return True
    return not any(p.split("/")[0] in NON_GAME for p in paths)


def trim(g: dict, versions: dict) -> dict | None:
    if not isinstance(g, dict) or not g.get("app_name"):
        return None
    md = g.get("metadata") if isinstance(g.get("metadata"), dict) else {}
    if "mainGameItem" in md:          # DLC: listed under its game, not on its own
        return None
    if not is_game(md):               # UE/Fab assets, plugins, tools, software
        return None
    imgs = {}
    for i in md.get("keyImages") or []:
        if isinstance(i, dict) and i.get("type") and i.get("url"):
            imgs.setdefault(i["type"], i["url"])
    ca = md.get("customAttributes") if isinstance(md.get("customAttributes"), dict) else {}
    third = _attr(ca, "ThirdPartyManagedApp") or _attr(ca, "ThirdPartyManagedProvider")
    app = str(g["app_name"])
    version = versions.get(app, "")
    dev = md.get("developer") or ""
    if not dev and isinstance(md.get("seller"), dict):
        dev = md["seller"].get("name") or ""
    return {
        "app": app,
        "title": (g.get("app_title") or md.get("title") or app).strip(),
        "ns": md.get("namespace") or "",
        "catalog": md.get("id") or "",
        "tall": _first(imgs, IMAGE_TALL),
        "wide": _first(imgs, IMAGE_WIDE),
        "logo": _first(imgs, IMAGE_LOGO),
        "developer": dev,
        "description": (md.get("description") or "").strip()[:700],
        "version": version,
        "installable": bool(version) and not third,
        "third_party": third,
        "dlcs": len([d for d in g.get("dlcs") or [] if isinstance(d, dict)]),
        "cloud_saves": "CloudSaveFolder" in ca,
    }


def build(raw: list, versions: dict) -> list:
    out = {}
    for g in raw:
        t = trim(g, versions)
        if t and t["app"] not in out:
            out[t["app"]] = t
    return sorted(out.values(), key=lambda x: x["title"].lower())


def installed_view(lgd_installed: dict, meta: dict, versions: dict, exists) -> dict:
    """app -> what the UI shows about an installed game. Merges Legendary's record (path, version,
    executable) with ours (Steam shortcut appid)."""
    out = {}
    for app, rec in lgd_installed.items():
        if not isinstance(rec, dict) or rec.get("is_dlc"):
            continue
        path = rec.get("install_path", "")
        exe = (rec.get("executable") or "").replace("\\", "/").lstrip("/")
        latest = versions.get(app, "")
        m = meta.get(app) or {}
        out[app] = {
            "app": app,
            "title": rec.get("title") or app,
            "dir": path,
            "exe": f"{path}/{exe}" if path and exe else "",
            "version": rec.get("version", ""),
            "latest": latest,
            "update": bool(latest) and latest != rec.get("version", "") and not rec.get("is_preloaded"),
            "size": int(rec.get("install_size") or 0),
            "offline": bool(rec.get("can_run_offline")),
            "verify": bool(rec.get("needs_verification")),
            "present": bool(path) and exists(path),
            "appid": int(m.get("appid") or 0),
        }
    return out
