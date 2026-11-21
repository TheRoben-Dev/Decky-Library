"""Talks to Nightgrid hosts the way Nightgrid does: plain SSH, nothing installed on them.

Uses the system OpenSSH client with a shared connection per host (ControlMaster) so the
refreshes while the panel is open reuse one login, and the connection closes by itself
90 s after the last one. Host keys: Nightgrid's own known_hosts (when Nightgrid is on
this device), ~/.ssh/known_hosts, then this plugin's file; a host seen for the first time
is trusted and remembered, a host whose key changed is refused.
"""
import asyncio
import ipaddress
import os
import re
import shlex
import socket
import time

SSH = "/usr/bin/ssh"
KEYGEN = "/usr/bin/ssh-keygen"
DEVICE_KEY = "nightgrid_control_ed25519"

# One POSIX script, busybox-friendly, read-only. Two /proc/stat samples half a second
# apart give the CPU load; the fullest real filesystem is reported like Nightgrid does.
STATUS_SH = r"""
LC_ALL=C; export LC_ALL
read u _ < /proc/uptime 2>/dev/null && echo "up=$u"
echo "c1=$(head -n1 /proc/stat 2>/dev/null)"
sleep 0.5 2>/dev/null || sleep 1
echo "c2=$(head -n1 /proc/stat 2>/dev/null)"
awk '/^MemTotal:/{t=$2}/^MemAvailable:/{a=$2}END{if(t>0)print "mem="t" "a}' /proc/meminfo 2>/dev/null
df -P 2>/dev/null | awk 'NR>1 && $1 !~ /^(tmpfs|devtmpfs|overlay|shm|udev|none|efivarfs|run|cgroup.*)$/ && $6 !~ /^\/(proc|sys|dev|run|snap|boot)(\/|$)/ {p=$5; sub("%","",p); if (p+0>=m) {m=p+0; d=$6}} END{if (d!="") print "disk="m" "d}'
t=0; for f in /sys/class/thermal/thermal_zone*/temp /sys/class/hwmon/hwmon*/temp*_input; do
  [ -r "$f" ] || continue; read v < "$f" 2>/dev/null || continue
  case "$v" in ''|*[!0-9]*) continue;; esac
  [ "$v" -gt "$t" ] && [ "$v" -lt 150000 ] && t=$v
done; [ "$t" -gt 0 ] && echo "temp=$t"
read l1 _ < /proc/loadavg 2>/dev/null && echo "load=$l1"
"""

STATUS_PS = (
    "$ErrorActionPreference='SilentlyContinue';"
    "$o=Get-CimInstance Win32_OperatingSystem;"
    "'up='+[int]((Get-Date)-$o.LastBootUpTime).TotalSeconds;"
    "'mem='+$o.TotalVisibleMemorySize+' '+$o.FreePhysicalMemory;"
    "'cpu='+[int](Get-CimInstance Win32_Processor|Measure-Object LoadPercentage -Average).Average;"
    "$d=Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3'|Sort-Object {1-$_.FreeSpace/$_.Size}|Select-Object -First 1;"
    "if($d){'disk='+[int](100-100*$d.FreeSpace/$d.Size)+' '+$d.DeviceID}"
)

POWER_SH = {
    "reboot": "systemctl reboot 2>/dev/null || shutdown -r now",
    "shutdown": "systemctl poweroff 2>/dev/null || shutdown -h now",
}
POWER_PS = {
    "reboot": "shutdown.exe /r /t 3 /d p:0:0 /c 'Restarted from Nightgrid Control'",
    "shutdown": "shutdown.exe /s /t 3 /d p:0:0 /c 'Shut down from Nightgrid Control'",
}

ASKPASS = """#!/bin/sh
case "$1" in
  *assphrase*) printf '%s\\n' "$NGC_KEYPASS" ;;
  *) printf '%s\\n' "$NGC_PASS" ;;
esac
"""


def clean_env() -> dict:
    # Decky's bundled Python sets LD_LIBRARY_PATH; system binaries must not inherit it.
    env = {k: v for k, v in os.environ.items() if k not in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH")}
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    return env


def ssh_quote(path: str) -> str:
    return '"' + path.replace('"', '') + '"'


class Ctx:
    """Paths and per-session state shared by every call."""

    def __init__(self, home: str, settings_dir: str, nightgrid_dir: str):
        self.home = home
        self.settings_dir = settings_dir
        self.known_hosts = os.path.join(settings_dir, "known_hosts")
        self.nightgrid_kh = os.path.join(nightgrid_dir, "known_hosts")
        self.run_dir = f"/tmp/ngc-{os.getuid()}"
        self.askpass = os.path.join(self.run_dir, "askpass")
        self.via = {}  # host id -> "tailnet" when only the tailnet address answered last time
        self._prepared = False

    def prepare(self):
        if self._prepared and os.path.isdir(self.run_dir):
            return
        os.makedirs(self.run_dir, mode=0o700, exist_ok=True)
        st = os.lstat(self.run_dir)
        if st.st_uid != os.getuid() or not os.path.isdir(self.run_dir) or os.path.islink(self.run_dir):
            raise RuntimeError(f"{self.run_dir} isn't ours")
        os.chmod(self.run_dir, 0o700)
        with open(self.askpass, "w") as f:
            f.write(ASKPASS)
        os.chmod(self.askpass, 0o700)
        os.makedirs(self.settings_dir, exist_ok=True)
        self._prepared = True

    def device_key(self) -> str:
        return os.path.join(self.home, ".ssh", DEVICE_KEY)


def _user_ssh_config_has(home: str, alias: str) -> bool:
    try:
        with open(os.path.join(home, ".ssh", "config")) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0].lower() == "host" and alias in parts[1:]:
                    return True
    except OSError:
        pass
    return False


def resolve_jump(value: str, hosts: list) -> str:
    """Nightgrid's ProxyJump may name other saved hosts; turn those into user@host:port."""
    out = []
    for part in [p.strip() for p in value.split(",") if p.strip()]:
        m = next((h for h in hosts if part in (h["name"], h.get("alias"))), None)
        if m and m["hostname"]:
            target = (f"{m['username']}@" if m.get("username") else "") + m["hostname"]
            if m["port"] != 22:
                target += f":{m['port']}"
            out.append(target)
        else:
            out.append(part)
    return ",".join(out)


def _identity(ctx: Ctx, host: dict):
    """Nightgrid's key path is usually from another computer: use the same file name in ~/.ssh."""
    keys = []
    idf = host.get("identity")
    if idf:
        idf = os.path.expanduser(idf) if idf.startswith("~") else idf
        base = re.split(r"[\\/]", idf)[-1]
        for cand in (idf, os.path.join(ctx.home, ".ssh", base)):
            if cand.startswith("/") and os.path.isfile(cand):
                keys.append(cand)
                break
    if os.path.isfile(ctx.device_key()):
        keys.append(ctx.device_key())
    return keys


def build(ctx: Ctx, host: dict, hosts: list, secrets: dict, remote_cmd: str, use_tailnet=False, batch_only=False):
    """argv + env for one ssh run. `secrets` are this host's saved secrets (may be empty).
    POSIX commands go through `sh -c`, so a login shell like fish or zsh doesn't matter."""
    ctx.prepare()
    if host.get("os") != "windows":
        remote_cmd = "exec sh -c " + shlex.quote(remote_cmd)
    kh = [ctx.known_hosts]
    if os.path.isfile(ctx.nightgrid_kh):
        kh.append(ctx.nightgrid_kh)
    kh.append(os.path.join(ctx.home, ".ssh", "known_hosts"))
    pw = secrets.get("host-password")
    kp = secrets.get("key-passphrase")
    interactive = bool(pw or kp) and not batch_only
    opts = [
        "-T", "-o", "ConnectTimeout=5", "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=" + " ".join(ssh_quote(p) for p in kh),
        "-o", "ControlMaster=auto", "-o", f"ControlPath={ctx.run_dir}/cm-%C", "-o", "ControlPersist=90",
        "-o", "LogLevel=ERROR", "-o", "NumberOfPasswordPrompts=1",
        "-o", "BatchMode=" + ("no" if interactive else "yes"),
    ]
    if interactive:
        opts += ["-o", "PreferredAuthentications=publickey,keyboard-interactive,password"]
    for k in _identity(ctx, host):
        opts += ["-i", k]
    if host.get("proxyJump"):
        opts += ["-J", resolve_jump(host["proxyJump"], hosts)]
    alias = host.get("alias")
    if alias and not use_tailnet and _user_ssh_config_has(ctx.home, alias):
        dest = alias
    else:
        dest = (host.get("tailnet") if use_tailnet else host["hostname"]) or host["hostname"]
        if host.get("username"):
            opts += ["-l", host["username"]]
        if host["port"] != 22:
            opts += ["-p", str(host["port"])]
    if not dest or dest.startswith("-"):
        raise ValueError("host has no address")
    env = clean_env()
    if interactive:
        env.update({"SSH_ASKPASS": ctx.askpass, "SSH_ASKPASS_REQUIRE": "force", "DISPLAY": env.get("DISPLAY", ":0"),
                    "NGC_PASS": pw or "", "NGC_KEYPASS": kp or pw or ""})
    return [SSH, *opts, "--", dest, remote_cmd], env


def classify(code: int, err: str) -> str:
    e = err.lower()
    if "remote host identification has changed" in e or "host key verification failed" in e:
        return "hostkey"
    if "permission denied" in e or "too many authentication failures" in e or "no supported authentication" in e:
        return "auth"
    if code == 255:
        return "offline"
    return "error"


async def run(argv, env, timeout=12.0, stdin: bytes = None):
    p = await asyncio.create_subprocess_exec(
        *argv, env=env, stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, start_new_session=True)
    try:
        out, err = await asyncio.wait_for(p.communicate(stdin), timeout)
    except asyncio.TimeoutError:
        try:
            p.kill()
        except ProcessLookupError:
            pass
        await p.wait()
        return 255, "", "timed out"
    return p.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def _cpu(l1: str, l2: str):
    try:
        a = [int(x) for x in l1.split()[1:]]
        b = [int(x) for x in l2.split()[1:]]
        idle = lambda v: v[3] + (v[4] if len(v) > 4 else 0)  # noqa: E731
        dt = sum(b) - sum(a)
        if dt <= 0:
            return None
        return round(max(0.0, min(100.0, 100.0 * (1 - (idle(b) - idle(a)) / dt))), 1)
    except (ValueError, IndexError):
        return None


def parse_status(out: str) -> dict:
    kv = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()
    m = {"cpu": None, "mem": None, "disk": None, "mount": None, "temp": None, "uptime": None, "load": None}
    try:
        m["uptime"] = float(kv["up"])
    except (KeyError, ValueError):
        pass
    if "c1" in kv and "c2" in kv:
        m["cpu"] = _cpu(kv["c1"], kv["c2"])
    elif "cpu" in kv:
        try:
            m["cpu"] = float(kv["cpu"])
        except ValueError:
            pass
    try:
        t, a = (float(x) for x in kv["mem"].split()[:2])
        if t > 0:
            m["mem"] = round(100.0 * (1 - a / t), 1)
    except (KeyError, ValueError):
        pass
    try:
        p, mount = kv["disk"].split(" ", 1)
        m["disk"], m["mount"] = float(p), mount
    except (KeyError, ValueError):
        pass
    try:
        m["temp"] = round(int(kv["temp"]) / 1000.0, 1)
    except (KeyError, ValueError):
        pass
    try:
        m["load"] = float(kv["load"])
    except (KeyError, ValueError):
        pass
    return m


def in_window(window: str, now=None) -> bool:
    """Nightgrid's sleep window, local hours like "23:00-07:00"."""
    try:
        a, b = window.split("-")
        ah, am = (int(x) for x in a.strip().split(":"))
        bh, bm = (int(x) for x in b.strip().split(":"))
    except (ValueError, AttributeError):
        return False
    t = time.localtime(now)
    cur, start, end = t.tm_hour * 60 + t.tm_min, ah * 60 + am, bh * 60 + bm
    return start <= cur < end if start <= end else (cur >= start or cur < end)


async def status(ctx: Ctx, host: dict, hosts: list, secrets: dict) -> dict:
    win = host.get("os") == "windows"
    cmd = "powershell -NoProfile -NonInteractive -Command " + shlex.quote(STATUS_PS) if win else STATUS_SH
    routes = [False, True] if host.get("tailnet") else [False]
    if ctx.via.get(host["id"]) == "tailnet" and len(routes) == 2:
        routes.reverse()
    state, err = "offline", ""
    for tail in routes:
        try:
            argv, env = build(ctx, host, hosts, secrets, cmd, use_tailnet=tail)
        except ValueError as e:
            return {"id": host["id"], "state": "error", "error": str(e), "at": time.time()}
        code, out, err = await run(argv, env)
        if code == 0 or (code != 255 and "up=" in out):
            ctx.via[host["id"]] = "tailnet" if tail else "lan"
            return {"id": host["id"], "state": "ok", "via": "tailnet" if tail else None,
                    **parse_status(out), "at": time.time()}
        state = classify(code, err)
        if state != "offline":
            break
    if state == "offline":
        if host.get("sleepWindow") and in_window(host["sleepWindow"]):
            state = "sleep"
        elif host.get("role") == "client":
            state = "away"
    msg = err.strip().splitlines()[-1][:160] if err.strip() else ""
    return {"id": host["id"], "state": state, "error": msg, "at": time.time()}


def sudo_wrap(inner: str, have_password: bool) -> str:
    q = shlex.quote(inner)
    sudo = f"sudo -S -k -p '' -- sh -c {q}" if have_password else f"sudo -n -- sh -c {q}"
    return f'if [ "$(id -u)" = 0 ]; then sh -c {q}; else {sudo}; fi'


async def power(ctx: Ctx, host: dict, hosts: list, secrets: dict, action: str) -> dict:
    if action not in POWER_SH:
        return {"ok": False, "error": "unknown action"}
    if host.get("os") == "windows":
        cmd = "powershell -NoProfile -NonInteractive -Command " + shlex.quote(POWER_PS[action])
        stdin = None
    else:
        # Detach so the reply gets back before the host goes down.
        inner = f"nohup sh -c {shlex.quote('sleep 2; ' + POWER_SH[action])} >/dev/null 2>&1 & echo queued"
        sudo_pw = secrets.get("sudo-password") or secrets.get("host-password")
        cmd = sudo_wrap(inner, bool(sudo_pw))
        stdin = (sudo_pw + "\n").encode() if sudo_pw else None
    tail = ctx.via.get(host["id"]) == "tailnet"
    argv, env = build(ctx, host, hosts, secrets, cmd, use_tailnet=tail)
    code, out, err = await run(argv, env, timeout=20, stdin=stdin)
    if code == 0 or "queued" in out:
        return {"ok": True}
    e = err.lower()
    if "a password is required" in e or "a terminal is required" in e:
        return {"ok": False, "error": "sudo needs a password. Export the profile with saved passwords, "
                                      "or allow this command without one on the host."}
    if "incorrect password" in e or "sorry, try again" in e:
        return {"ok": False, "error": "sudo refused the saved password"}
    if "not in the sudoers" in e or "not allowed" in e:
        return {"ok": False, "error": "this account can't use sudo on the host"}
    st = classify(code, err)
    return {"ok": False, "error": {"offline": "host didn't answer", "auth": "login refused",
                                   "hostkey": "host key changed: check it in Nightgrid"}.get(st, err.strip()[:160] or "failed")}


# ---------------------------------------------------------------- Wake-on-LAN

def parse_mac(mac: str) -> bytes:
    h = re.sub(r"[^0-9a-fA-F]", "", mac or "")
    if len(h) != 12:
        raise ValueError("bad MAC address")
    return bytes.fromhex(h)


def magic_packet(mac: bytes) -> bytes:
    return b"\xff" * 6 + mac * 16


def _directed_broadcast(hostname: str):
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return None
    if ip.version == 4 and ip.is_private:
        return str(ipaddress.ip_network(f"{ip}/24", strict=False).broadcast_address)
    return None


def wake_local(mac: bytes, hostname: str) -> int:
    pkt = magic_packet(mac)
    targets = ["255.255.255.255"]
    b = _directed_broadcast(hostname)
    if b:
        targets.append(b)
    sent = 0
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for t in targets:
            for port in (9, 7):
                try:
                    s.sendto(pkt, (t, port))
                    sent += 1
                except OSError:
                    pass
    return sent


def relay_command(mac: bytes) -> str:
    m = ":".join(f"{x:02x}" for x in mac)
    hx = mac.hex()
    py = ("import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);"
          "s.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1);"
          f"p=bytes.fromhex('ff'*6+'{hx}'*16);[s.sendto(p,('255.255.255.255',q)) for q in (9,7)];print('sent')")
    return (f"if command -v wakeonlan >/dev/null 2>&1; then wakeonlan {m}; "
            f"elif command -v python3 >/dev/null 2>&1; then python3 -c {shlex.quote(py)}; "
            "else echo 'needs wakeonlan or python3 on the relay host' >&2; exit 3; fi")


def relay_command_windows(mac: bytes) -> str:
    b = ",".join(f"0x{x:02X}" for x in mac)
    ps = (f"$m=[byte[]]({b});$p=[byte[]]((@(0xFF)*6)+($m*16));$u=New-Object Net.Sockets.UdpClient;"
          "$u.EnableBroadcast=$true;foreach($q in 9,7){[void]$u.Send($p,$p.Length,'255.255.255.255',$q)};$u.Close()")
    return "powershell -NoProfile -NonInteractive -Command " + shlex.quote(ps)


async def wake(ctx: Ctx, host: dict, hosts: list, all_secrets: dict) -> dict:
    mac = parse_mac(host.get("mac") or "")
    sent = wake_local(mac, host.get("hostname") or "")
    relay = next((h for h in hosts if h["id"] == host.get("wakeRelay")), None)
    via = None
    if relay and relay["id"] != host["id"]:
        argv, env = build(ctx, relay, hosts, all_secrets.get(str(relay["id"]), {}),
                          relay_command_windows(mac) if relay.get("os") == "windows" else relay_command(mac),
                          use_tailnet=ctx.via.get(relay["id"]) == "tailnet")
        code, _, _ = await run(argv, env, timeout=15)
        if code == 0:
            via = relay["name"]
    if not sent and not via:
        return {"ok": False, "error": "couldn't send the magic packet"}
    return {"ok": True, "relay": via}


# ---------------------------------------------------------------- this device's key

async def device_key(ctx: Ctx, create: bool) -> dict:
    key = ctx.device_key()
    if create and not os.path.isfile(key):
        os.makedirs(os.path.dirname(key), mode=0o700, exist_ok=True)
        code, _, err = await run([KEYGEN, "-q", "-t", "ed25519", "-N", "", "-C",
                                  f"nightgrid-control@{socket.gethostname()}", "-f", key], clean_env(), timeout=20)
        if code != 0:
            return {"ok": False, "error": err.strip()[:160] or "ssh-keygen failed"}
    if not os.path.isfile(key + ".pub"):
        return {"ok": True, "exists": False}
    with open(key + ".pub") as f:
        pub = f.read().strip()
    code, out, _ = await run([KEYGEN, "-lf", key + ".pub"], clean_env(), timeout=10)
    fp = out.split()[1] if code == 0 and len(out.split()) > 1 else ""
    return {"ok": True, "exists": True, "pub": pub, "fingerprint": fp, "path": key + ".pub"}


async def install_key(ctx: Ctx, host: dict, hosts: list, secrets: dict, pub: str) -> dict:
    if host.get("os") == "windows":
        return {"ok": False, "error": "add it from Nightgrid (Settings > SSH keys) for Windows hosts"}
    if not re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/=]+( [^\n']*)?", pub):
        return {"ok": False, "error": "bad public key"}
    q = shlex.quote(pub)
    cmd = (f"umask 077; mkdir -p ~/.ssh && touch ~/.ssh/authorized_keys && "
           f"(grep -qxF {q} ~/.ssh/authorized_keys || printf '%s\\n' {q} >> ~/.ssh/authorized_keys) && echo added")
    argv, env = build(ctx, host, hosts, secrets, cmd, use_tailnet=ctx.via.get(host["id"]) == "tailnet")
    code, out, err = await run(argv, env, timeout=20)
    if code == 0 and "added" in out:
        return {"ok": True}
    return {"ok": False, "error": {"offline": "host didn't answer", "auth": "login refused"}.get(classify(code, err), err.strip()[:160] or "failed")}
