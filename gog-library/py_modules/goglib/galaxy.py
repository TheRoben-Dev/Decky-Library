"""Galaxy content-system downloads (the file-by-file format GOG Galaxy and Heroic install from).

Generation 2 builds: each file is a list of zlib-compressed chunks addressed by their md5.
Generation 1 builds: each file is a byte range of one big main.bin.
A plan (what the build contains) is turned into files on disk in place: files already there with
the right contents are kept, so updates only fetch what changed and an interrupted install picks up
where it stopped. Saves and settings a game writes into its folder are never touched, because only
paths listed by the previous build are ever removed.
"""
import concurrent.futures
import hashlib
import os
import stat
import threading
import time
import zlib

from . import api

WORKERS = 4
WINDOW = 8              # chunks in flight at most (each is at most ~10 MB unpacked)
PART = ".gogpart"


class Cancelled(Exception):
    pass


class DownloadError(Exception):
    pass


def _rel(p: str) -> str:
    parts = [x for x in str(p).replace("\\", "/").split("/") if x not in ("", ".")]
    if not parts or any(x == ".." for x in parts):
        return ""
    return os.path.join(*parts)


def _lang_ok(langs: list, lang: str, neutral: tuple) -> bool:
    short = lang.split("-")[0].lower()
    for l in langs or []:
        l2 = str(l).lower()
        if l2 in neutral or l2 == lang.lower() or l2 == short or l2.split("-")[0] == short:
            return True
        if short == "en" and l2 == "english":
            return True
    return False


# ------------------------------------------------------------------ plans

def plan(game_id: int, build: dict, token: str, lang: str, owned: set) -> dict:
    gen = int(build.get("generation") or 2)
    meta = api.get_zjson(build["link"], token)
    if gen == 2 and int(meta.get("version") or 2) == 2:
        return _plan_v2(game_id, build, meta, token, lang, owned)
    return _plan_v1(game_id, build, meta, token, lang, owned)


def _plan_v2(game_id, build, meta, token, lang, owned) -> dict:
    gid = str(game_id)
    products = {str(p.get("productId")) for p in meta.get("products") or []}
    want = {gid} | {p for p in products if p != gid and p.isdigit() and int(p) in owned}
    depots = []
    for d in meta.get("depots") or []:
        pid = str(d.get("productId"))
        bits = [str(b) for b in d.get("osBitness") or []]
        if pid in want and _lang_ok(d.get("languages") or [], lang, ("*",)) and (not bits or "64" in bits):
            depots.append(d)
    if not depots:   # no depot in that language: fall back to the game's English/neutral ones
        depots = [d for d in meta.get("depots") or [] if str(d.get("productId")) in want
                  and _lang_ok(d.get("languages") or [], "en-US", ("*",))]
    files, dirs, links = [], [], []
    for d in depots:
        man = api.get_zjson(f"{api.CDN}/content-system/v2/meta/{api.galaxy_path(d['manifest'])}", token)
        for it in (man.get("depot") or {}).get("items") or []:
            t = it.get("type")
            rel = _rel(it.get("path", ""))
            if not rel:
                continue
            if t == "DepotFile":
                flags = it.get("flags") or []
                if "support" in flags:
                    continue   # installer support files, not part of the game
                chunks = [{"md5": c["md5"], "zmd5": c["compressedMd5"], "size": int(c["size"]),
                           "zsize": int(c.get("compressedSize") or c["size"])} for c in it.get("chunks") or []]
                sig = it.get("md5") or it.get("sha256") or (
                    hashlib.md5("".join(c["md5"] for c in chunks).encode()).hexdigest() if chunks else "empty")
                files.append({"path": rel, "product": str(d.get("productId")), "chunks": chunks,
                              "size": sum(c["size"] for c in chunks), "sig": sig, "exe": "executable" in flags})
            elif t == "DepotLink":
                links.append({"path": rel, "target": str(it.get("target", "")).replace("\\", "/")})
            else:
                dirs.append(rel)
    return {"generation": 2, "build_id": str(build.get("build_id") or ""), "version": str(build.get("version_name") or ""),
            "install_dir": str(meta.get("installDirectory") or ""), "files": _dedupe(files), "dirs": dirs, "links": links,
            "products": sorted(want), "timestamp": ""}


def _plan_v1(game_id, build, meta, token, lang, owned) -> dict:
    prod = meta.get("product") or {}
    gid = str(game_id)
    ts = str(prod.get("timestamp") or "")
    files, dirs = [], []
    used = set()
    for d in prod.get("depots") or []:
        if d.get("redist") or not d.get("manifest"):
            continue
        ids = [str(x) for x in d.get("gameIDs") or []]
        if not any(i == gid or (i.isdigit() and int(i) in owned) for i in ids):
            continue
        if not _lang_ok(d.get("languages") or [], lang, ("neutral", "*")):
            continue
        pid = ids[0]
        used.add(pid)
        man = api.get_json(f"{api.CDN}/content-system/v1/manifests/{pid}/windows/{ts}/{d['manifest']}", token)
        for rec in (man.get("depot") or {}).get("files") or []:
            rel = _rel(rec.get("path", ""))
            if not rel:
                continue
            if rec.get("directory"):
                dirs.append(rel)
                continue
            if rec.get("support") or rec.get("offset") is None:
                continue
            files.append({"path": rel, "product": pid, "offset": int(rec["offset"]), "size": int(rec.get("size") or 0),
                          "sig": str(rec.get("hash") or ""), "v1": True, "exe": bool(rec.get("executable"))})
    return {"generation": 1, "build_id": str(build.get("legacy_build_id") or build.get("build_id") or ""),
            "version": str(build.get("version_name") or ""), "install_dir": str(prod.get("installDirectory") or ""),
            "files": _dedupe(files), "dirs": dirs, "links": [], "products": sorted(used), "timestamp": ts}


def _dedupe(files: list) -> list:
    """Later depots (DLC, language) win over earlier ones for the same path, case-insensitively."""
    seen = {}
    for f in files:
        seen[f["path"].lower()] = f
    return list(seen.values())


def sizes(p: dict) -> tuple:
    """(download bytes, disk bytes) of a whole plan."""
    disk = sum(f["size"] for f in p["files"])
    dl = sum(sum(c["zsize"] for c in f["chunks"]) if not f.get("v1") else f["size"] for f in p["files"])
    return dl, disk


# ------------------------------------------------------------------ executing a plan

class _Paths:
    """Windows games mix the case of folder names; keep one folder per name like Windows does."""

    def __init__(self, root: str):
        self.root = os.path.realpath(root)
        self.known = {}

    def resolve(self, rel: str) -> str:
        parts = rel.split(os.sep)
        cur = self.root
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            key = (cur, part.lower())
            hit = self.known.get(key)
            if hit is None:
                hit = part
                try:
                    for n in os.listdir(cur):
                        if n.lower() == part.lower():
                            hit = n
                            break
                except OSError:
                    pass
                if not last:
                    self.known[key] = hit
            cur = os.path.join(cur, hit)
        return cur


def _inside(root: str, path: str) -> bool:
    root = os.path.realpath(root)
    p = os.path.realpath(path)
    return p == root or p.startswith(root + os.sep)


class Executor:
    def __init__(self, game_id: int, p: dict, dest: str, token_fn, progress, cancel: threading.Event):
        self.gid = game_id
        self.p = p
        self.dest = dest
        self.token_fn = token_fn
        self.progress = progress        # progress(done_bytes, total_bytes)
        self.cancel = cancel
        self.links = {}
        self.link_lock = threading.Lock()
        self.done = 0
        self.total = 0
        self.dlock = threading.Lock()
        self.last = 0.0

    # -- secure links (per product, refreshed when they expire)
    def _endpoints(self, product: str, fresh: bool = False) -> list:
        with self.link_lock:
            if fresh or product not in self.links:
                gen = self.p["generation"]
                path = "/" if gen == 2 else f"/windows/{self.p['timestamp']}/"
                urls = api.secure_link(product, self.token_fn(), gen, path)
                urls.sort(key=lambda u: -int(u.get("priority") or 0) if isinstance(u, dict) else 0)
                self.links[product] = urls
            return self.links[product]

    def _tick(self, n: int):
        with self.dlock:
            self.done += n
            now = time.monotonic()
            if now - self.last >= 0.25:
                self.last = now
                self.progress(self.done, self.total)

    def _chunk(self, product: str, c: dict) -> bytes:
        err = None
        fresh = False
        for attempt in range(6):
            if self.cancel.is_set():
                raise Cancelled()
            eps = self._endpoints(product, fresh)
            fresh = False
            ep = eps[min(attempt // 2, len(eps) - 1)]
            url = api.endpoint_url(ep, "/" + api.galaxy_path(c["zmd5"]))
            try:
                with api.open_url(url, timeout=30) as r:
                    data = r.read(c["zsize"] + 1024)
                if hashlib.md5(data).hexdigest() != c["zmd5"]:
                    raise DownloadError("A downloaded piece was damaged")
                out = zlib.decompress(data)
                if len(out) != c["size"]:
                    raise DownloadError("A downloaded piece has the wrong size")
                self._tick(len(data))
                return out
            except api.ApiError as e:
                err = e
                if e.status in (401, 403):
                    fresh = True
            except (DownloadError, zlib.error, OSError) as e:
                err = e
            time.sleep(min(8, 1 + attempt * 2))
        raise DownloadError(f"Couldn't download part of the game ({err})")

    def _write_v2(self, f: dict, target: str, pool):
        part = target + PART
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(part, "wb") as out:
            chunks = f["chunks"]
            futs = []
            i = 0
            while i < len(chunks) or futs:
                while i < len(chunks) and len(futs) < WINDOW:
                    futs.append(pool.submit(self._chunk, f["product"], chunks[i]))
                    i += 1
                try:
                    out.write(futs.pop(0).result())
                except BaseException:
                    for x in futs:
                        x.cancel()
                    raise
        os.replace(part, target)

    def _write_v1(self, f: dict, target: str):
        part = target + PART
        os.makedirs(os.path.dirname(target), exist_ok=True)
        err = None
        fresh = False
        for attempt in range(4):
            if self.cancel.is_set():
                raise Cancelled()
            eps = self._endpoints(f["product"], fresh)
            fresh = False
            url = api.endpoint_url(eps[min(attempt, len(eps) - 1)], "/main.bin")
            got = 0
            md5 = hashlib.md5()
            try:
                if f["size"] == 0:
                    open(part, "wb").close()
                else:
                    end = f["offset"] + f["size"] - 1
                    with api.open_url(url, headers={"Range": f"bytes={f['offset']}-{end}"}, timeout=30) as r, open(part, "wb") as out:
                        while got < f["size"]:
                            if self.cancel.is_set():
                                raise Cancelled()
                            buf = r.read(min(1 << 20, f["size"] - got))
                            if not buf:
                                break
                            out.write(buf)
                            md5.update(buf)
                            got += len(buf)
                            self._tick(len(buf))
                    if got != f["size"] or (f["sig"] and md5.hexdigest() != f["sig"]):
                        self._tick(-got)
                        raise DownloadError("A downloaded file was damaged")
                os.replace(part, target)
                return
            except api.ApiError as e:
                err = e
                if e.status in (401, 403):
                    fresh = True
            except (DownloadError, OSError) as e:
                err = e
            time.sleep(1 + attempt * 2)
        raise DownloadError(f"Couldn't download {os.path.basename(target)} ({err})")

    def run(self, old: dict | None, free_bytes) -> dict:
        """old = receipt of the installed build ({path: sig}) or None for a fresh install."""
        os.makedirs(self.dest, exist_ok=True)
        paths = _Paths(self.dest)
        todo = []
        receipt = {}
        old_l = {k.lower(): v for k, v in old.items()} if old else None
        for f in self.p["files"]:
            target = paths.resolve(f["path"])
            if not _inside(self.dest, os.path.dirname(target)):
                continue
            receipt[f["path"]] = f["sig"]
            try:
                same = os.path.getsize(target) == f["size"] and not os.path.islink(target)
            except OSError:
                same = False
            if same and (old_l is None or old_l.get(f["path"].lower()) == f["sig"]):
                continue
            todo.append((f, target))
        self.total = sum(sum(c["zsize"] for c in f["chunks"]) if not f.get("v1") else f["size"] for f, _ in todo)
        need = sum(f["size"] for f, _ in todo)
        if need and free_bytes(self.dest) < need + 256 * 1024 * 1024:
            raise DownloadError(f"Not enough free space (about {need // (1024 * 1024)} MB needed)")
        self.progress(0, self.total)
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for f, target in todo:
                if self.cancel.is_set():
                    raise Cancelled()
                try:
                    if os.path.islink(target):
                        os.unlink(target)
                    if f.get("v1"):
                        self._write_v1(f, target)
                    else:
                        self._write_v2(f, target, pool)
                except BaseException:
                    try:
                        os.unlink(target + PART)
                    except OSError:
                        pass
                    raise
                if f.get("exe"):
                    try:
                        os.chmod(target, os.stat(target).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                    except OSError:
                        pass
        self.progress(self.total, self.total)
        for d in self.p["dirs"]:
            t = paths.resolve(d)
            if _inside(self.dest, t):
                os.makedirs(t, exist_ok=True)
        for l in self.p["links"]:
            t = paths.resolve(l["path"])
            if os.path.lexists(t) or not _inside(self.dest, os.path.dirname(t)):
                continue
            if _inside(self.dest, os.path.join(os.path.dirname(t), l["target"])):
                os.makedirs(os.path.dirname(t), exist_ok=True)
                os.symlink(l["target"], t)
        # Files the previous build had and this one doesn't (never anything the game made itself).
        if old:
            keep = {k.lower() for k in receipt}
            for rel in old:
                if rel.lower() not in keep:
                    t = paths.resolve(rel)
                    if _inside(self.dest, t) and os.path.isfile(t) and not os.path.islink(t):
                        try:
                            os.unlink(t)
                        except OSError:
                            pass
        return receipt
