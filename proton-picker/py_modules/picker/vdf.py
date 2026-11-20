"""Minimal reader for Valve's text KeyValues (VDF) format.

Only what we need: compatibilitytool.vdf / toolmanifest.vdf / config.vdf.
Keys are kept as-is; lookups in callers are case-insensitive via `get_ci`.
"""


def _tokens(text: str):
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c == "/" and text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j + 1
        elif c in "{}":
            yield c
            i += 1
        elif c == '"':
            i += 1
            buf = []
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    nxt = text[i + 1]
                    buf.append({"n": "\n", "t": "\t", "\\": "\\", '"': '"'}.get(nxt, nxt))
                    i += 2
                    continue
                buf.append(text[i])
                i += 1
            i += 1
            yield ("s", "".join(buf))
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '{}"':
                j += 1
            yield ("s", text[i:j])
            i = j


def loads(text: str) -> dict:
    root: dict = {}
    stack = [root]
    key = None
    for tok in _tokens(text):
        if tok == "{":
            child: dict = {}
            stack[-1][key if key is not None else ""] = child
            stack.append(child)
            key = None
        elif tok == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
        else:
            s = tok[1]
            if key is None:
                key = s
            else:
                stack[-1][key] = s
                key = None
    return root


def get_ci(d: dict, *path: str):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return None
        lower = p.lower()
        cur = next((v for k, v in cur.items() if k.lower() == lower), None)
    return cur
