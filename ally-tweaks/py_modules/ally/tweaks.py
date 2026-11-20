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
