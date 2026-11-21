"""Amazon Games download manifests (manifest.proto), without the protobuf library.

Layout: 4-byte big-endian header length, a ManifestHeader message, then the Manifest message
(usually LZMA-compressed). The Manifest is signed with Amazon's RSA key (SHA-256, PKCS#1 v1.5),
which is checked before anything in it is trusted. Field numbers:

  ManifestHeader: 1 compression{1 algorithm: 0 none, 1 lzma}, 2 hash, 3 signature{1 algorithm, 2 value}
  Manifest:       1 packages (repeated)
  Package:        1 name, 2 files (repeated), 3 dirs (repeated)
  File:           1 path, 2 mode, 3 size, 4 created, 5 hash{1 algorithm: 0 sha256, 1 shake128, 2 value}
"""
import hashlib
import struct

# Amazon's public signing key (the one the Amazon Games app ships), as modulus and exponent.
RSA_N = int(
    "e9f4913148b75694edbfd3f8f8abcc01c0083f84986d341f0759eceefc948ec8fc9eb17694636d413b462e7acd98cd84"
    "959d91ed5990b4d891b4f3314e821645a8e29f41f43b2cc6ac703c3fac3de8c8f8ab525e3910b325e54580b3810a5082"
    "32607ee5b2415a725cabfb04330bbd806ca709e89834bb7b64c5692f518eb0d8e5fb22e4ece30c1a9323d495825457e0"
    "604f4bb9dd506499651405a1441a13c1372d0146538a439b154a019be284882b0a21c6b2e163b26ef270c53341525d86"
    "2fc73e8a1ad3da7b4b3e96fd688244fe05d4dc8865e685deff43ff40dd0246eff26d758b886cc862a288a24e277a991d"
    "a3c577816479e4af34d693ae724d016b", 16)
RSA_E = 65537
SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")
HASHES = {0: "sha256", 1: "shake128"}


class ManifestError(Exception):
    pass


def _varint(buf: bytes, i: int) -> tuple:
    shift = result = 0
    while True:
        if i >= len(buf):
            raise ManifestError("Truncated manifest")
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, i
        shift += 7
        if shift > 63:
            raise ManifestError("Bad manifest")


def fields(buf: bytes) -> dict:
    """{field number: [values]} for one message; bytes for length-delimited, int otherwise."""
    out: dict = {}
    i = 0
    while i < len(buf):
        key, i = _varint(buf, i)
        num, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _varint(buf, i)
        elif wt == 1:
            v, i = int.from_bytes(buf[i:i + 8], "little"), i + 8
        elif wt == 2:
            n, i = _varint(buf, i)
            v, i = buf[i:i + n], i + n
            if i > len(buf):
                raise ManifestError("Truncated manifest")
        elif wt == 5:
            v, i = int.from_bytes(buf[i:i + 4], "little"), i + 4
        else:
            raise ManifestError("Bad manifest")
        out.setdefault(num, []).append(v)
    return out


def _one(f: dict, n: int, default=None):
    v = f.get(n)
    return v[0] if v else default


def verify(data: bytes, signature: bytes) -> bool:
    k = (RSA_N.bit_length() + 7) // 8
    if len(signature) != k:
        return False
    m = pow(int.from_bytes(signature, "big"), RSA_E, RSA_N).to_bytes(k, "big")
    digest = SHA256_PREFIX + hashlib.sha256(data).digest()
    expected = b"\x00\x01" + b"\xff" * (k - len(digest) - 3) + b"\x00" + digest
    return m == expected


def _lzma(data: bytes) -> bytes:
    try:
        import lzma
        return lzma.decompress(data)
    except ImportError:
        # Decky's bundled Python may lack lzma; Bazzite always has xz.
        import subprocess
        from .install import clean_env
        r = subprocess.run(["xz", "-dc"], input=data, capture_output=True, env=clean_env(), timeout=120)
        if r.returncode:
            raise ManifestError("Couldn't decompress the manifest")
        return r.stdout


def parse(content: bytes) -> list:
    """Files of the first package: [{path, size, hash (hex), algo}], paths with forward slashes.
    Raises ManifestError if the signature doesn't check out."""
    if len(content) < 4:
        raise ManifestError("Empty manifest")
    hlen = struct.unpack(">I", content[:4])[0]
    header = fields(content[4:4 + hlen])
    body = content[4 + hlen:]
    comp = fields(_one(header, 1, b""))
    sig = fields(_one(header, 3, b""))
    if _one(sig, 1, 0) != 0 or not _one(sig, 2):
        raise ManifestError("Manifest has an unknown signature type")
    algo = _one(comp, 1, 0)
    if algo == 1:
        body = _lzma(body)
    elif algo != 0:
        raise ManifestError("Manifest uses an unknown compression")
    if not verify(body, _one(sig, 2)):
        raise ManifestError("Manifest signature doesn't match Amazon's key")
    packages = fields(body).get(1) or []
    if not packages:
        return []
    out = []
    for raw in fields(packages[0]).get(2) or []:
        f = fields(raw)
        h = fields(_one(f, 5, b""))
        path = _one(f, 1, b"").decode("utf-8", "replace").replace("\\", "/").lstrip("/")
        hv = _one(h, 2, b"")
        if not path or not hv:
            continue
        out.append({"path": path, "size": int(_one(f, 3, 0)), "hash": hv.hex(), "algo": HASHES.get(_one(h, 1, 0), "sha256")})
    return out


def hasher(algo: str):
    return hashlib.shake_128() if algo == "shake128" else hashlib.sha256()


def hexdigest(h, algo: str, want_hex: str) -> str:
    return h.hexdigest(len(want_hex) // 2) if algo == "shake128" else h.hexdigest()


def compare(new: list, old: list | None) -> tuple:
    """(files to fetch, paths to delete) going from old to new."""
    if not old:
        return list(new), []
    before = {f["path"].lower(): f for f in old}
    fetch = []
    for f in new:
        o = before.pop(f["path"].lower(), None)
        if not o or o["hash"] != f["hash"]:
            fetch.append(f)
    return fetch, [f["path"] for f in before.values()]
