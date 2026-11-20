# Ally Tweaks (Decky Loader plugin)

Hardware tweaks made for the **ROG Ally 2023** (RC71L, Z1 / Z1 Extreme) on
Bazzite. Everything is set from the Quick Access menu, with no launch options,
terminal steps or config files to edit.

Power and TDP stay in [Vex Performance](../vex-performance/) and Proton in
[Proton Picker](../proton-picker/). This plugin doesn't duplicate them.

## Two backends, picked automatically
Bazzite 44 dropped Handheld Daemon (HHD) for **InputPlumber** + steamos-manager.
The plugin detects what's running and uses it:

| | Bazzite 44+ (InputPlumber, no HHD) | Installs that still run HHD |
|---|---|---|
| Ring RGB | Kernel LED class: `/sys/class/leds/ally:rgb:joystick_rings` (`multi_intensity`, `brightness`) + `asus::kbd_backlight` level, from the kernel's `hid-asus-ally` driver | HHD settings API `rgb.handheld.mode.*` |
| Effects | Solid, **Left / right colors** (with swap), **Four zones**, Off, plus the controller's own animations (breathe, rainbow, strobe…) when the driver exposes `effect`/`effect_index`. Never animated from software | Solid, Pulse, Two colors, Rainbow, Spiral, Off |
| Persistence | A small restore unit the plugin installs (see below) | HHD saves and re-sends it itself |
| Charge limit | `charge_control_end_threshold` (asus-wmi) + restore unit at boot | HHD `gamemode.battery.charge_limit` |
| Back buttons | InputPlumber maps M1/M2 to Xbox Elite back paddles, so Steam binds them per game (shown as a hint) | HHD `paddles_as` + A/B swap, global or per game |

InputPlumber has no D-Bus API for LED colour or a simple button remap: its
LED source just forwards DualSense lightbar output from games to the same
kernel LED, and remapping is done through whole InputPlumber profiles. The
Ally's default InputPlumber target is Xbox Elite, which has no lightbar, so
InputPlumber leaves the rings alone and the kernel LED is the right place.

## Features

| Feature | Notes |
|---|---|
| **Ring RGB** | See backends above. Hue, saturation and brightness in fine steps on the kernel path. |
| **Per-game lighting** | Switches when a game starts, back to default when it closes |
| **Reactive color**: battery level (red→green), APU temperature (cyan→red), TDP mode (HHD only) | Backend loop, writes only when the color actually changes (temperature has hysteresis) |
| **Follow screen brightness** | Ring brightness tracks the panel's real backlight (`/sys/class/backlight/amdgpu_bl*/actual_brightness` ÷ `max_brightness`) in 1% steps, scaled by your max brightness; off when the backlight is off. Debounced (~1 s) |
| **Low-battery warning**: red below a threshold (default 15%) on battery | Pulses with HHD, solid red on the kernel path |
| **Lights off on battery** | |
| **Charge limit** 70/80/85/90/95% or off + **Full charge once (travel)** | Travel mode charges to 100% and puts your limit back on unplug |
| **Battery info** | Health % vs design, cycles, live watts, current stop threshold |
| **Panel overdrive**, **Boot sound** | asus-armoury `panel_overdrive` / `boot_sound` (legacy asus-nb-wmi fallback) |

### System tweaks (persistent, reversible)
| Toggle | What it does | Tradeoff |
|---|---|---|
| **Wi-Fi power saving off** | NetworkManager drop-in `/etc/NetworkManager/conf.d/99-zz-ally-tweaks-wifi.conf` (`wifi.powersave=2`) + `iw dev <if> set power_save off` now, at boot and after resume. Bazzite's deck image already ships `wifi.powersave=2`, but its tuned **Power Saver** profile turns power save back on with `iw`; the plugin switches it off again within ~5 s. Turning the toggle off deletes the drop-in and reloads NetworkManager's config. | ~0.2–0.5 W more on battery |
| **USB autosuspend off** | `usbcore` `autosuspend=-1` and `power/control=on` for connected devices; re-applied at boot. Fixes docks/USB controllers dropping out after idling. Turning it off restores the 2 s default for new devices. | Slightly more battery use with USB devices plugged in |

| **Audio codec power saving off** | `snd_hda_intel` `power_save=0`, re-applied at boot. Bazzite already keeps PipeWire outputs awake; this also keeps the codec itself up (no pop / clipped first sound) | ~0.1–0.3 W |
| **Keep speaker amps awake** (one speaker going silent) | Experimental workaround for the known "one speaker drops out" reports: sets runtime PM `power/control=on` for the `cs35l41-hda` (or `tas2781-hda`) amp devices so they never power down between sounds. Re-applied after resume and at boot. Not a confirmed fix: no upstream fix was found for the RC71L. If a side stays silent, a reboot brings it back; check `journalctl -k -b \| grep -i cs35l41` | A little more idle power |
| **Split-lock mitigation** | Bazzite ships it **off** (`kernel.split_lock_mitigate=0`). The toggle can turn it back on via `/etc/sysctl.d/99-ally-tweaks-splitlock.conf` | On = some games slow down badly |
| **PCIe power management off** | The same kernel argument `ujust manage-pcie-power` sets (`pcie_port_pm=off` via `rpm-ostree kargs`), from Game Mode. Shows "reboot to apply" | Less micro-stutter / SSD latency, more battery and sleep drain |
| **Touchscreen**: On / Off while a game runs / Off | Input `inhibited` attribute on the touchscreen; re-checked after resume | None |
| **CPU boost** | amd-pstate `cpufreq/boost`; kept off across power-profile switches, sleep and reboot | Cooler/longer battery, slower in CPU-heavy games |
| **SMT** | `/sys/devices/system/cpu/smt/control` | 8 threads instead of 16 |
| **CPU energy preference (EPP)** | `energy_performance_preference` on every core, or "follow power profile" | Within stock range; re-applied when tuned changes it |
| **GPU memory (VRAM)** | asus-armoury `apu_mem` (Armoury Crate's "Memory assigned to GPU": Auto, 2, 3, 4, 6, 8 GB) | Taken from system RAM; needs a reboot |

Shown as "already set by Bazzite" (nothing to toggle): zram zstd + swappiness 180,
low-latency Bluetooth LE intervals, PipeWire outputs never suspending.

### RGB reliability
The plugin reads the LED back every few seconds and re-applies the colour if
the driver reset it (after resume or a re-probe) or something else wrote it,
and forces a full re-apply when it detects the device just woke up. If
something keeps overwriting the rings (3 times in 2 minutes) it stops
fighting and says so. The usual culprit: when InputPlumber emulates a
DualSense, Steam's light-bar colour (blue by default) is copied onto the
rings; the plugin detects that target over D-Bus and explains how to change it.

### What stays when the plugin isn't loaded
- **Kernel path:** the plugin installs `ally-tweaks-restore.service`, a root
  oneshot that runs at boot and after every resume. It reads
  `/etc/ally-tweaks/restore.env` (plain numbers only, parsed with `sed`, never
  executed) and writes them back to the ring LED and `charge_control_end_threshold`,
  and re-applies the Wi-Fi power save and USB autosuspend toggles.
  So the last lighting and the charge limit survive reboots and sleep with
  Decky off. Uninstalling the plugin removes the unit, its files and the NetworkManager drop-in, and resets USB autosuspend.
- **HHD path:** HHD keeps the settings itself; no unit is installed.
- Changing parts (reactive colors, low-battery warning, per-game switching,
  follow-screen) need the plugin running. Otherwise the last value stays.

## Hardware safety
- **No** TDP, clocks, voltages, undervolting, fan curves or thermal policy.
- **No** MCU/EC settings and **no** firmware writes. The kernel driver (or HHD) talks to the MCU, with one
  exception, approved by the owner: on Linux 7.2+ kernels that clamp `multi_intensity` to 255 (which turns
  every ring colour blue), the plugin sends the ring-colour report itself (`0x5A 0xD1 0x08 0x0C` + 4×RGB),
  byte-for-byte what `hid-asus-ally` and HHD send. It's only used when that clamp is detected, and the
  restore unit re-sends it at boot and after sleep. No other HID command is ever sent.
- Writes only to documented kernel attributes: LED class `multi_intensity`/`brightness`,
  `charge_control_end_threshold`, `panel_overdrive`/`panel_od`, `boot_sound`.
- No software-animated effects on the kernel path (that would be a constant stream of controller writes). Animations only when the controller runs them itself.
- CPU boost/SMT/EPP only *reduce* or pick within stock behaviour; GPU memory is a stock BIOS option.

### Deliberately left out
| Idea | Why |
|---|---|
| Software pulse / rainbow on the kernel path | Faking them means writing to the controller many times a second. Hardware effects are used when the driver offers them. |
| MCU powersave / "Extreme standby" | Known to leave the controller unresponsive after sleep (HHD hides it for that reason). |
| Saving colors into MCU flash | Undocumented command. The restore unit covers reboots safely. |
| InputPlumber button remaps / profiles | Steam Input already binds the paddles per game; swapping whole InputPlumber profiles from a plugin would fight Bazzite's own InputPlumber/OpenGamepadUI setup. |
| VRR toggle, fan curves, TDP | Steam/Vex handle VRR and TDP; fans are excluded by the safety rule. |

## Install (Game Mode)
1. Copy `Ally-Tweaks.zip` to the Ally.
2. Decky → gear → General → enable **Developer mode**.
3. Developer → **Install Plugin from Zip** → pick the zip.

## Notes
- **Untested on real hardware.** Checked against InputPlumber `main` (2026-11-20, `50-rog_ally.yaml`, `ally_type1.yaml`, LED source), the `hid-asus-ally` driver, Bazzite's build scripts, HHD `master` and Linux `master`.
- **Left / right colors:** the driver has 4 zones; the plugin gives the first two one color and the last two the other. If that turns out to be top/bottom halves instead of left/right rings, it's a one-line swap.
- If Steam's own **Battery charge limit** setting is active, use one or the other, not both.
- With HHD: changing back-button settings makes HHD restart its virtual controller (about a second).

## Build from source
```
pnpm install
pnpm build
./package.sh   # out/Ally-Tweaks.zip
```
