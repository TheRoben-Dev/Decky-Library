"""Decrypts a passphrase-encrypted age file (a Nightgrid profile export).

Nightgrid writes its profile with the Rust `age` crate and an scrypt recipient
(core/src/backup.rs). Decky's Python has no age library, so this is a small,
self-contained reader of the age v1 format for exactly that case: one scrypt
stanza, header MAC check, STREAM payload with ChaCha20-Poly1305.

The `cryptography` package is used for ChaCha20-Poly1305 when it is importable;
otherwise a pure-Python RFC 8439 implementation runs (a profile is a few hundred
KB, so that takes a second or two, once, at import time).
"""
import base64
import hashlib
import hmac
import struct

MAGIC = b"age-encryption.org/v1"
SCRYPT_LABEL = b"age-encryption.org/v1/scrypt"
CHUNK = 64 * 1024
TAG = 16
MAX_LOG_N = 22  # age's own decrypt limit is similar; refuse files that ask for more work
MAX_BYTES = 32 * 1024 * 1024  # Nightgrid refuses bigger backups too


class AgeError(Exception):
    pass


class WrongPassphrase(AgeError):
    pass


# ---------------------------------------------------------------- ChaCha20-Poly1305 (RFC 8439)

_M32 = 0xFFFFFFFF


def _rotl(v, c):
    return ((v << c) & _M32) | (v >> (32 - c))


def _block(key_words, counter, nonce_words):
    s = [0x61707865, 0x3320646E, 0x79622D32, 0x6B206574, *key_words, counter & _M32, *nonce_words]
    x = list(s)
    for _ in range(10):
        for a, b, c, d in ((0, 4, 8, 12), (1, 5, 9, 13), (2, 6, 10, 14), (3, 7, 11, 15),
                           (0, 5, 10, 15), (1, 6, 11, 12), (2, 7, 8, 13), (3, 4, 9, 14)):
            x[a] = (x[a] + x[b]) & _M32; x[d] = _rotl(x[d] ^ x[a], 16)
            x[c] = (x[c] + x[d]) & _M32; x[b] = _rotl(x[b] ^ x[c], 12)
            x[a] = (x[a] + x[b]) & _M32; x[d] = _rotl(x[d] ^ x[a], 8)
            x[c] = (x[c] + x[d]) & _M32; x[b] = _rotl(x[b] ^ x[c], 7)
    return struct.pack("<16I", *((x[i] + s[i]) & _M32 for i in range(16)))


def _chacha20(key, counter, nonce, data):
    kw = struct.unpack("<8I", key)
    nw = struct.unpack("<3I", nonce)
    n = len(data)
    if not n:
        return b""
    stream = b"".join(_block(kw, counter + i, nw) for i in range((n + 63) // 64))[:n]
    return (int.from_bytes(data, "little") ^ int.from_bytes(stream, "little")).to_bytes(n, "little")


def _poly1305(key, msg):
    r = int.from_bytes(key[:16], "little") & 0x0FFFFFFC0FFFFFFC0FFFFFFC0FFFFFFF
    s = int.from_bytes(key[16:32], "little")
    p = (1 << 130) - 5
    acc = 0
    for i in range(0, len(msg), 16):
        blk = msg[i:i + 16]
        acc = ((acc + int.from_bytes(blk + b"\x01", "little")) * r) % p
    return ((acc + s) & ((1 << 128) - 1)).to_bytes(16, "little")


def _pad16(n):
    return b"\x00" * (-n % 16)


def _open_py(key, nonce, ct_tag):
    if len(ct_tag) < TAG:
        raise AgeError("truncated data")
    ct, tag = ct_tag[:-TAG], ct_tag[-TAG:]
    otk = _block(struct.unpack("<8I", key), 0, struct.unpack("<3I", nonce))[:32]
    mac_data = ct + _pad16(len(ct)) + struct.pack("<QQ", 0, len(ct))
    if not hmac.compare_digest(_poly1305(otk, mac_data), tag):
        raise _AuthFail()
    return _chacha20(key, 1, nonce, ct)


class _AuthFail(Exception):
    pass


def _make_open():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305  # type: ignore
        from cryptography.exceptions import InvalidTag  # type: ignore

        def _open_c(key, nonce, ct_tag):
            try:
                return ChaCha20Poly1305(key).decrypt(nonce, ct_tag, None)
            except InvalidTag:
                raise _AuthFail()
        return _open_c
    except Exception:
        return _open_py


aead_open = _make_open()


# ---------------------------------------------------------------- age v1

def _b64(s: bytes) -> bytes:
    # age uses unpadded standard base64 and rejects padding.
    if b"=" in s:
        raise AgeError("malformed header")
    try:
        return base64.b64decode(s + b"=" * (-len(s) % 4), validate=True)
    except Exception:
        raise AgeError("malformed header")


def _hkdf(ikm, salt, info, n=32):
    prk = hmac.new(salt or b"\x00" * 32, ikm, hashlib.sha256).digest()
    out, t, i = b"", b"", 1
    while len(out) < n:
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        out += t
        i += 1
    return out[:n]


def _scrypt(passphrase: bytes, salt: bytes, log_n: int) -> bytes:
    n = 1 << log_n
    maxmem = 128 * 8 * n + 64 * 1024 * 1024
    try:
        return hashlib.scrypt(passphrase, salt=salt, n=n, r=8, p=1, dklen=32, maxmem=maxmem)
    except AttributeError:  # Python built without OpenSSL scrypt: ask the system Python
        import os
        import subprocess
        payload = passphrase + b"\x00" + salt
        code = ("import hashlib,sys;d=sys.stdin.buffer.read();i=d.index(b'\\x00');"
                f"sys.stdout.write(hashlib.scrypt(d[:i],salt=d[i+1:],n={n},r=8,p=1,dklen=32,maxmem={maxmem}).hex())")
        env = {k: v for k, v in os.environ.items() if k != "LD_LIBRARY_PATH"}
        r = subprocess.run(["/usr/bin/python3", "-I", "-c", code], input=payload, capture_output=True,
                           timeout=60, env=env)
        if r.returncode != 0:
            raise AgeError("this system can't run scrypt")
        return bytes.fromhex(r.stdout.decode())


def parse_header(data: bytes):
    """Returns (stanzas, mac, header_bytes_for_mac, payload_offset)."""
    if not data.startswith(MAGIC + b"\n"):
        raise AgeError("not an age file")
    pos = len(MAGIC) + 1
    stanzas = []
    while True:
        nl = data.find(b"\n", pos)
        if nl < 0:
            raise AgeError("truncated header")
        line = data[pos:nl]
        if line.startswith(b"--- "):
            mac = _b64(line[4:])
            mac_input = data[:pos + 3]
            return stanzas, mac, mac_input, nl + 1
        if not line.startswith(b"-> "):
            raise AgeError("malformed header")
        args = line[3:].split(b" ")
        pos = nl + 1
        body = b""
        while True:
            nl = data.find(b"\n", pos)
            if nl < 0:
                raise AgeError("truncated header")
            bl = data[pos:nl]
            pos = nl + 1
            if len(bl) > 64:
                raise AgeError("malformed header")
            body += bl
            if len(bl) < 64:
                break
        stanzas.append((args, _b64(body) if body else b""))


def is_passphrase_file(head: bytes) -> bool:
    """Cheap check on the first bytes of a file: an age file with an scrypt stanza."""
    return head.startswith(MAGIC + b"\n-> scrypt ")


def decrypt(data: bytes, passphrase: str) -> bytes:
    if len(data) > MAX_BYTES:
        raise AgeError("file is too big to be a Nightgrid profile")
    stanzas, mac, mac_input, off = parse_header(data)
    scrypt_st = [s for s in stanzas if s[0] and s[0][0] == b"scrypt"]
    if not scrypt_st:
        raise AgeError("this file isn't passphrase-encrypted")
    if len(stanzas) != 1:
        raise AgeError("malformed header (scrypt must be the only recipient)")
    args, body = scrypt_st[0]
    if len(args) != 3 or not args[2].isdigit() or args[2].startswith(b"0"):
        raise AgeError("malformed scrypt stanza")
    salt, log_n = _b64(args[1]), int(args[2])
    if len(salt) != 16 or len(body) != 32:
        raise AgeError("malformed scrypt stanza")
    if log_n > MAX_LOG_N:
        raise AgeError("the file asks for too much work to decrypt")
    wrap = _scrypt(passphrase.encode("utf-8"), SCRYPT_LABEL + salt, log_n)
    try:
        file_key = aead_open(wrap, b"\x00" * 12, body)
    except _AuthFail:
        raise WrongPassphrase("wrong passphrase")
    hk = _hkdf(file_key, b"", b"header")
    if not hmac.compare_digest(hmac.new(hk, mac_input, hashlib.sha256).digest(), mac):
        raise AgeError("header check failed (file damaged?)")
    if len(data) < off + 16:
        raise AgeError("truncated file")
    nonce = data[off:off + 16]
    key = _hkdf(file_key, nonce, b"payload")
    payload = data[off + 16:]
    out = []
    i, counter = 0, 0
    full = CHUNK + TAG
    while True:
        chunk = payload[i:i + full]
        last = i + full >= len(payload)
        if not chunk and counter > 0:
            raise AgeError("truncated file")
        n = counter.to_bytes(11, "big") + (b"\x01" if last else b"\x00")
        try:
            pt = aead_open(key, n, chunk)
        except _AuthFail:
            raise AgeError("file is damaged")
        if last and not pt and counter > 0:
            raise AgeError("malformed payload")
        out.append(pt)
        if last:
            break
        i += full
        counter += 1
    return b"".join(out)
