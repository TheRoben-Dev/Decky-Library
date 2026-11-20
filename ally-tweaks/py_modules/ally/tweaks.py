"""System tweaks popular with Ally owners, each persistent and reversible.

Only two are offered because Bazzite already ships the rest (checked against
ublue-os/bazzite main, Nov 2026):
  split-lock mitigation off      usr/lib/sysctl.d/60-kernel.conf
  zram (zstd) + swappiness 180   etc/systemd/zram-generator.conf, sysctl.d/65-memory.conf
  Bluetooth low-latency LE       etc/bluetooth/main.conf (7-9 ms intervals)
  audio pop fix                  wireplumber 51-disable-suspension.conf (sinks never suspend)
  PCIe port power                `ujust manage-pcie-power`
  Wi-Fi power save off           etc/NetworkManager/conf.d/99-valve-wifi-backend.conf
                                 (wifi.powersave=2) -- BUT the tuned
                                 "powersave-bazzite" profile (Power Saver mode)
                                 turns it back on with `iw`, which is what the
                                 Wi-Fi toggle here guards against.

1) Wi-Fi power saving off
   * /etc/NetworkManager/conf.d/99-zz-ally-tweaks-wifi.conf: wifi.powersave=2
     (sorted after Valve's file so it wins if that ever changes)
   * live: `iw dev <if> set power_save off` on every wireless interface
   * the restore unit re-runs it at boot/resume; the plugin loop re-applies it
     within seconds if a power profile switches it back on
   Turning it off removes the drop-in and reloads NetworkManager's config.

2) USB autosuspend off (external controllers / docks dropping out)
   * /sys/module/usbcore/parameters/autosuspend = -1 (new devices)
   * power/control = on for connected USB devices
   * re-applied at boot by the restore unit
   Turning it off sets the delay back to the kernel default (2 s); devices
   already connected keep "on" until replugged or rebooted.
"""
import os
import shutil
import subprocess

import decky

NM_DROPIN = "/etc/NetworkManager/conf.d/99-zz-ally-tweaks-wifi.conf"
NM_BODY = "# Written by the Ally Tweaks Decky plugin. Delete to undo.\n[connection]\nwifi.powersave=2\n"
USB_PARAM = "/sys/module/usbcore/parameters/autosuspend"
USB_DEFAULT = "2"


def _env():
    env = dict(os.environ)
    env.pop("LD_LIBRARY_PATH", None)
    return env


def _run(*args):
    try:
        return subprocess.run(list(args), capture_output=True, text=True, timeout=10, env=_env())
    except Exception as e:
        decky.logger.error(f"{args[0]} failed: {e}")
        return None


def _iw():
    return shutil.which("iw", path="/usr/sbin:/usr/bin:/sbin:/bin")


def wifi_ifaces():
    try:
        return sorted(n for n in os.listdir("/sys/class/net") if os.path.isdir(f"/sys/class/net/{n}/wireless"))
    except Exception:
        return []


def _wifi_ps(iface):
    iw = _iw()
    if not iw:
        return None
    r = _run(iw, "dev", iface, "get", "power_save")
    if not r or r.returncode != 0:
        return None
    return "on" in r.stdout.lower().split(":")[-1]


def wifi_status() -> dict:
    ifaces = wifi_ifaces()
    states = {i: _wifi_ps(i) for i in ifaces}
    return {
        "supported": bool(ifaces) and _iw() is not None,
        "ifaces": ifaces,
        "powerSaveOn": any(v for v in states.values()),
        "dropin": os.path.exists(NM_DROPIN),
    }


def wifi_enforce():
    """Switch power save off on any interface that has it on. Cheap no-op otherwise."""
    iw = _iw()
    if not iw:
        return False
    changed = False
    for i in wifi_ifaces():
        if _wifi_ps(i):
            r = _run(iw, "dev", i, "set", "power_save", "off")
            changed = changed or (r is not None and r.returncode == 0)
    if changed:
        decky.logger.info("Wi-Fi power save switched back off")
    return changed


def set_wifi_powersave_off(on: bool):
    if on:
        cur = None
        try:
            with open(NM_DROPIN) as f:
                cur = f.read()
        except Exception:
            pass
        if cur != NM_BODY:
            os.makedirs(os.path.dirname(NM_DROPIN), exist_ok=True)
            with open(NM_DROPIN, "w") as f:
                f.write(NM_BODY)
            _run("nmcli", "general", "reload", "conf")
        wifi_enforce()
    else:
        if os.path.exists(NM_DROPIN):
            os.remove(NM_DROPIN)
            _run("nmcli", "general", "reload", "conf")


def usb_status() -> dict:
    try:
        with open(USB_PARAM) as f:
            v = f.read().strip()
    except Exception:
        return {"supported": False}
    return {"supported": True, "delay": v, "disabled": v.startswith("-")}


def set_usb_autosuspend_off(on: bool):
    if not os.path.exists(USB_PARAM):
        return False
    with open(USB_PARAM, "w") as f:
        f.write("-1" if on else USB_DEFAULT)
    if on:
        base = "/sys/bus/usb/devices"
        try:
            devs = os.listdir(base)
        except Exception:
            devs = []
        for d in devs:
            p = f"{base}/{d}/power/control"
            try:
                with open(p) as f:
                    if f.read().strip() == "on":
                        continue
                with open(p, "w") as f:
                    f.write("on")
            except Exception:
                pass
    return True


# ======================================================================
# Bazzite defaults / terminal-only tweaks, exposed for Game Mode
# ======================================================================
CPU = "/sys/devices/system/cpu"
SPLITLOCK_SYSCTL = "/proc/sys/kernel/split_lock_mitigate"
SPLITLOCK_DROPIN = "/etc/sysctl.d/99-ally-tweaks-splitlock.conf"
HDA_PS = "/sys/module/snd_hda_intel/parameters/power_save"
EPP_VALUES = ["performance", "balance_performance", "balance_power", "power"]
PCIE_KARG = "pcie_port_pm=off"


def _r(p):
    try:
        with open(p) as f:
            return f.read().strip()
    except Exception:
        return None


def _w(p, v):
    try:
        if _r(p) == str(v):
            return True
        with open(p, "w") as f:
            f.write(str(v))
        return True
    except Exception as e:
        decky.logger.error(f"write {p} failed: {e}")
        return False


def _glob(pattern_dir, sub):
    """All <pattern_dir>/<entry>/<sub> that exist (no glob module needed)."""
    out = []
    try:
        for n in sorted(os.listdir(pattern_dir)):
            p = f"{pattern_dir}/{n}/{sub}"
            if os.path.exists(p):
                out.append(p)
    except Exception:
        pass
    return out


# ---- CPU boost (amd-pstate) ----
def _boost_files():
    files = [f"{CPU}/cpufreq/boost"] if os.path.exists(f"{CPU}/cpufreq/boost") else []
    return files + [p for p in _glob(f"{CPU}/cpufreq", "boost")]


def boost_status():
    files = _boost_files()
    if not files:
        return None
    return any(_r(f) == "1" for f in files)


def set_boost(on: bool):
    ok = False
    for f in _boost_files():
        ok = _w(f, "1" if on else "0") or ok
    return ok


# ---- SMT ----
def smt_status():
    v = _r(f"{CPU}/smt/control")
    if v in (None, "notsupported", "notimplemented", "forceoff"):
        return None
    return v == "on"


def set_smt(on: bool):
    return _w(f"{CPU}/smt/control", "on" if on else "off")


# ---- EPP (amd-pstate-epp energy_performance_preference) ----
def _epp_files():
    return _glob(CPU, "cpufreq/energy_performance_preference")


def epp_status():
    files = _epp_files()
    if not files:
        return None
    avail = (_r(f"{os.path.dirname(files[0])}/energy_performance_available_preferences") or "").split()
    return {"current": _r(files[0]), "available": [v for v in EPP_VALUES if v in avail]}


def set_epp(value: str):
    if value not in EPP_VALUES:
        return False
    ok = True
    for f in _epp_files():
        # Fails (EBUSY) while the "performance" governor is active; harmless.
        ok = _w(f, value) and ok
    return ok


# ---- split-lock mitigation (Bazzite ships it OFF via sysctl) ----
def splitlock_status():
    v = _r(SPLITLOCK_SYSCTL)
    return None if v is None else v == "1"


def set_splitlock(mitigate: bool):
    """mitigate=True writes an override that turns the kernel's split-lock
    slowdown back on; False removes it (Bazzite's default: off)."""
    if mitigate:
        os.makedirs(os.path.dirname(SPLITLOCK_DROPIN), exist_ok=True)
        with open(SPLITLOCK_DROPIN, "w") as f:
            f.write("# Written by the Ally Tweaks Decky plugin. Delete to undo.\nkernel.split_lock_mitigate=1\n")
    elif os.path.exists(SPLITLOCK_DROPIN):
        os.remove(SPLITLOCK_DROPIN)
    return _w(SPLITLOCK_SYSCTL, "1" if mitigate else "0")


# ---- HDA codec power saving ----
def audio_ps_status():
    v = _r(HDA_PS)
    return None if v is None else v != "0"


_audio_default = None


def set_audio_ps(on: bool):
    """off -> 0; back on -> whatever the system had before (remembered), or 1."""
    global _audio_default
    if not os.path.exists(HDA_PS):
        return False
    cur = _r(HDA_PS)
    if not on:
        if cur not in (None, "0"):
            _audio_default = cur
        return _w(HDA_PS, "0")
    return _w(HDA_PS, _audio_default or "1")


# ---- PCIe port power management (same karg as `ujust manage-pcie-power`) ----
_pcie_cache = {"pending": None}


def pcie_status():
    try:
        with open("/proc/cmdline") as f:
            active = PCIE_KARG in f.read().split()
    except Exception:
        active = False
    if _pcie_cache["pending"] is None:
        r = _run("rpm-ostree", "kargs")
        _pcie_cache["pending"] = (PCIE_KARG in r.stdout.split()) if r and r.returncode == 0 else None
    pending = _pcie_cache["pending"]
    return {
        "supported": shutil.which("rpm-ostree") is not None,
        "active": active,
        "next": active if pending is None else pending,
        "rebootNeeded": pending is not None and pending != active,
    }


def set_pcie_pm_off(off: bool):
    """Exactly what `ujust manage-pcie-power enable|disable` runs. Takes a
    while (rpm-ostree stages a new boot entry); applies after reboot."""
    args = ["rpm-ostree", "kargs", f"--append-if-missing={PCIE_KARG}"] if off else ["rpm-ostree", "kargs", f"--delete-if-present={PCIE_KARG}"]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=600, env=_env())
    finally:
        _pcie_cache["pending"] = None
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "rpm-ostree failed")
    return True


def status_all():
    return {
        "boost": boost_status(),
        "smt": smt_status(),
        "epp": epp_status(),
        "splitLockMitigation": splitlock_status(),
        "audioPowerSave": audio_ps_status(),
        "pcie": pcie_status(),
        "touch": touch_status(),
    }


# ---- touchscreen on/off (input "inhibited" attribute) ----
# The kernel stops delivering events from an inhibited input device and lets
# the driver power it down; writing 0 brings it straight back. Nothing is
# unbound or unloaded.
INPUT = "/sys/class/input"
INPUT_PROP_DIRECT = 0x2


def touchscreens():
    out = []
    try:
        names = os.listdir(INPUT)
    except Exception:
        return out
    for n in sorted(names):
        if not n.startswith("input"):
            continue
        base = f"{INPUT}/{n}"
        props = _r(f"{base}/properties")
        abs_caps = _r(f"{base}/capabilities/abs")
        name = _r(f"{base}/name") or ""
        try:
            direct = bool(int(props or "0", 16) & INPUT_PROP_DIRECT)
        except ValueError:
            direct = False
        if not os.path.exists(f"{base}/inhibited") or not abs_caps or abs_caps == "0":
            continue
        # Pen/stylus devices are direct too; the Ally has none, skip them anyway.
        if (direct or "touchscreen" in name.lower()) and "pen" not in name.lower():
            out.append(base)
    return out


def touch_status():
    devs = touchscreens()
    if not devs:
        return None
    return {"enabled": not all(_r(f"{d}/inhibited") == "1" for d in devs),
            "names": [_r(f"{d}/name") for d in devs]}


def set_touch(enabled: bool):
    ok = False
    for d in touchscreens():
        ok = _w(f"{d}/inhibited", "0" if enabled else "1") or ok
    return ok
