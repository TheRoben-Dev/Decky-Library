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
| Effects | Solid, **Left / right colors** (each ring its own color), Off | Solid, Pulse, Two colors, Rainbow, Spiral, Off |
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

### What stays when the plugin isn't loaded
- **Kernel path:** the plugin installs `ally-tweaks-restore.service`, a root
  oneshot that runs at boot and after every resume. It reads
  `/etc/ally-tweaks/restore.env` (plain numbers only, parsed with `sed`, never
  executed) and writes them back to the ring LED and `charge_control_end_threshold`.
  So the last lighting and the charge limit survive reboots and sleep with
  Decky off. The plugin removes the unit and its files when uninstalled.
- **HHD path:** HHD keeps the settings itself; no unit is installed.
- Changing parts (reactive colors, low-battery warning, per-game switching,
  follow-screen) need the plugin running. Otherwise the last value stays.

## Hardware safety
- **No** TDP, clocks, voltages, undervolting, fan curves or thermal policy.
- **No** raw MCU/EC commands and **no** firmware writes. The kernel driver (or HHD) talks to the MCU.
- Writes only to documented kernel attributes: LED class `multi_intensity`/`brightness`,
  `charge_control_end_threshold`, `panel_overdrive`/`panel_od`, `boot_sound`.
- No software-animated effects on the kernel path (that would be a constant stream of controller writes); only static colors.

### Deliberately left out
| Idea | Why |
|---|---|
| Pulse / rainbow on the kernel path | The stock `hid-asus-ally` LED device has no hardware effects. Faking them means writing to the controller many times a second. |
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
