"""Keeps the ring colour and charge limit when Decky / the plugin isn't running.

Without Handheld Daemon nothing re-applies the rings after a reboot (the
kernel driver starts at its default, and InputPlumber doesn't store a colour)
and asus-wmi forgets the charge limit on reboot. So the plugin installs one
small root oneshot unit:

  /etc/ally-tweaks/restore.env   last applied values (plain integers only)
  /etc/ally-tweaks/restore.sh    writes them back: ring LED, charge limit,
                                 Wi-Fi power save off (iw), USB autosuspend off,
                                 CPU boost / SMT / EPP, HDA codec power save
  /etc/systemd/system/ally-tweaks-restore.service
                                 runs at boot and after every resume

It only ever writes the values below, to the LED class and power_supply
files. Uninstalling the plugin disables and deletes all three.
"""
import os
import re
import subprocess
import tempfile

import decky

DIR = "/etc/ally-tweaks"
ENV = f"{DIR}/restore.env"
SCRIPT = f"{DIR}/restore.sh"
UNIT_NAME = "ally-tweaks-restore.service"
UNIT = f"/etc/systemd/system/{UNIT_NAME}"
SLEEP_TARGETS = "suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target"

SCRIPT_BODY = r"""#!/bin/sh
# Ally Tweaks (Decky plugin): restore ring lighting and charge limit.
# Reads plain values from restore.env; never executes it.
CONF=/etc/ally-tweaks/restore.env
[ -r "$CONF" ] || exit 0
get() { sed -n "s/^$1=\([0-9 ]*\)$/\1/p" "$CONF" | head -n1; }
INTENSITY=$(get RGB_INTENSITY); BRIGHT=$(get RGB_BRIGHTNESS); KBD=$(get KBD_LEVEL); LIMIT=$(get CHARGE_LIMIT)
WIFI_PS_OFF=$(get WIFI_PS_OFF); USB_AS_OFF=$(get USB_AS_OFF)
AMPS_AWAKE=$(get AMPS_AWAKE); BOOST_OFF=$(get BOOST_OFF); SMT_OFF=$(get SMT_OFF); EPP_IDX=$(get EPP_IDX); AUDIO_PS_OFF=$(get AUDIO_PS_OFF)

if [ "$BOOST_OFF" = "1" ]; then
  for f in /sys/devices/system/cpu/cpufreq/boost /sys/devices/system/cpu/cpufreq/policy*/boost; do
    [ -w "$f" ] && echo 0 > "$f"
  done
fi
[ "$SMT_OFF" = "1" ] && [ -w /sys/devices/system/cpu/smt/control ] && echo off > /sys/devices/system/cpu/smt/control
if [ -n "$EPP_IDX" ]; then
  case "$EPP_IDX" in
    0) EPP=performance ;; 1) EPP=balance_performance ;; 2) EPP=balance_power ;; 3) EPP=power ;; *) EPP="" ;;
  esac
  if [ -n "$EPP" ]; then
    for f in /sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference; do
      [ -w "$f" ] && echo "$EPP" > "$f" 2>/dev/null
    done
  fi
fi
if [ "$AMPS_AWAKE" = "1" ]; then
  for c in /sys/bus/i2c/drivers/cs35l41-hda/*/power/control /sys/bus/spi/drivers/cs35l41-hda/*/power/control \
           /sys/bus/i2c/drivers/tas2781-hda/*/power/control; do
    [ -w "$c" ] && echo on > "$c"
  done
fi
[ "$AUDIO_PS_OFF" = "1" ] && [ -w /sys/module/snd_hda_intel/parameters/power_save ] && echo 0 > /sys/module/snd_hda_intel/parameters/power_save

if [ "$USB_AS_OFF" = "1" ] && [ -w /sys/module/usbcore/parameters/autosuspend ]; then
  echo -1 > /sys/module/usbcore/parameters/autosuspend
  for c in /sys/bus/usb/devices/*/power/control; do echo on > "$c" 2>/dev/null; done
fi
if [ "$WIFI_PS_OFF" = "1" ]; then
  IW=$(command -v iw || echo /usr/sbin/iw)
  if [ -x "$IW" ]; then
    i=0
    while [ $i -lt 20 ]; do
      found=0
      for n in /sys/class/net/*; do
        [ -d "$n/wireless" ] || continue
        found=1; "$IW" dev "$(basename "$n")" set power_save off 2>/dev/null
      done
      [ $found = 1 ] && break
      sleep 1; i=$((i+1))
    done
  fi
fi

if [ -n "$BRIGHT" ]; then
  LED=""; i=0
  while [ -z "$LED" ] && [ $i -lt 30 ]; do
    for d in /sys/class/leds/*:rgb:joystick_rings; do [ -e "$d/multi_intensity" ] && LED="$d"; done
    [ -z "$LED" ] && { sleep 1; i=$((i+1)); }
  done
  if [ -n "$LED" ]; then
    K=/sys/class/leds/asus::kbd_backlight/brightness
    [ -n "$KBD" ] && [ -w "$K" ] && echo "$KBD" > "$K"
    [ -n "$INTENSITY" ] && echo "$INTENSITY" > "$LED/multi_intensity"
    echo "$BRIGHT" > "$LED/brightness"
  fi
fi
if [ -n "$LIMIT" ]; then
  for b in /sys/class/power_supply/BAT*/charge_control_end_threshold; do
    [ -w "$b" ] && echo "$LIMIT" > "$b"
  done
fi
exit 0
"""

UNIT_BODY = f"""[Unit]
Description=Ally Tweaks: restore ROG Ally ring lighting and charge limit
After=systemd-udev-settle.service {SLEEP_TARGETS}

[Service]
Type=oneshot
ExecStart=/bin/sh {SCRIPT}
TimeoutSec=60

[Install]
WantedBy=multi-user.target {SLEEP_TARGETS}
"""

_NUM = re.compile(r"^[0-9]+( [0-9]+)*$")


def _atomic(path, text, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp.")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except Exception:
        return None


def _systemctl(*args):
    env = dict(os.environ)
    env.pop("LD_LIBRARY_PATH", None)  # Decky's bundled libs confuse systemctl
    return subprocess.run(["systemctl", *args], capture_output=True, text=True, timeout=20, env=env)


class Persist:
    def __init__(self):
        self.values = {}
        current = _read(ENV) or ""
        for line in current.splitlines():
            k, _, v = line.partition("=")
            if _NUM.match(v.strip()):
                self.values[k.strip()] = v.strip()

    def installed(self) -> bool:
        return os.path.exists(UNIT)

    def _ensure_unit(self):
        changed = False
        if _read(SCRIPT) != SCRIPT_BODY:
            _atomic(SCRIPT, SCRIPT_BODY, 0o755)
            changed = True
        if _read(UNIT) != UNIT_BODY:
            _atomic(UNIT, UNIT_BODY)
            changed = True
        if changed:
            r = _systemctl("daemon-reload")
            if r.returncode == 0:
                r = _systemctl("enable", UNIT_NAME)
            if r.returncode != 0:
                decky.logger.error(f"enabling {UNIT_NAME} failed: {r.stderr.strip()}")

    def update(self, **vals):
        """Set/clear keys (None clears). Writes only when something changed."""
        new = dict(self.values)
        for k, v in vals.items():
            if v is None or v == "":
                new.pop(k, None)
            else:
                v = str(v).strip()
                if not _NUM.match(v):
                    raise ValueError(f"refusing non-numeric value for {k}")
                new[k] = v
        if new == self.values and (not new or self.installed()):
            return
        self.values = new
        if not new:
            if os.path.exists(ENV):
                _atomic(ENV, "")
            return
        _atomic(ENV, "".join(f"{k}={v}\n" for k, v in sorted(new.items())))
        self._ensure_unit()

    def remove(self):
        try:
            if os.path.exists(UNIT):
                _systemctl("disable", UNIT_NAME)
            for p in (UNIT, SCRIPT, ENV):
                if os.path.exists(p):
                    os.remove(p)
            if os.path.isdir(DIR) and not os.listdir(DIR):
                os.rmdir(DIR)
            _systemctl("daemon-reload")
        except Exception as e:
            decky.logger.error(f"persist cleanup failed: {e}")
