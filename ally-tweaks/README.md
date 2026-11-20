# Ally Tweaks (Decky Loader plugin)

Hardware tweaks made for the **ROG Ally 2023** (RC71L, Z1 / Z1 Extreme) on
Bazzite. Everything is set from the Quick Access menu, with no launch options,
terminal steps or config files to edit.

Power and TDP stay in [Vex Performance](../vex-performance/) and Proton in
[Proton Picker](../proton-picker/). This plugin doesn't duplicate them.

## Features

| Feature | How it's applied | Works without the plugin loaded? |
|---|---|---|
| **Ring RGB**: Solid, Pulse, Two colors, Rainbow, Spiral, Off; hue/saturation/brightness/speed/direction | Handheld Daemon's settings API (`rgb.handheld.mode.*` over `/run/hhd/api`). HHD saves it and re-sends it after boot and suspend. | **Yes** |
| **Lights during boot / while charging asleep** | HHD's own `controllers.rog_ally.rgb_boot` / `rgb_charging` options, which tell the controller MCU to keep the rings lit before HHD starts | **Yes** |
| **Per-game lighting** | Switches when a game starts, back to default when it closes | Last color stays; switching needs the plugin |
| **Reactive color**: battery level (red→green), APU temperature (cyan→red), TDP mode (HHD's colors: Silent blue, Performance white, Turbo red, Custom purple) | Backend loop every 5 s, writes to HHD only when the color actually changes (temperature has hysteresis) | Last color stays |
| **Follow screen brightness**: ring brightness tracks the panel's real backlight level (`/sys/class/backlight/amdgpu_bl*/actual_brightness` ÷ `max_brightness`) in 1% steps, scaled by your max brightness; rings go off when the backlight is off | Backlight polled every 0.5 s, a new level must hold for ~1 s before it's sent to HHD, so dragging the slider doesn't spam it. Rainbow/Spiral only have 3 hardware levels | Last level stays |
| **Low-battery pulse**: pulses red below a threshold (default 15%) on battery | Same loop, top priority | No |
| **Lights off on battery** | Same loop | No |
| **Charge limit** 70/80/85/90/95% or off | HHD's `gamemode.battery.charge_limit` when HHD exposes it (HHD re-applies it each boot). Otherwise the kernel's `charge_control_end_threshold` (asus-wmi), re-applied when Decky starts | **Yes** with HHD |
| **Full charge once (travel)**: charges to 100% now, puts your limit back when you unplug | Plugin watches AC state | Restores on next load if you unplugged while it was off |
| **Battery info**: health % vs design, cycle count, live watts, current stop threshold | Read-only `power_supply` | n/a |
| **Back buttons (M1/M2)** for all games or per game: Steam Input paddles, Keyboard/HHD overlay, Touchpad clicks, Disabled. Optional per-game **A/B + X/Y swap** | HHD `controllers.rog_ally.controller_mode.<mode>.paddles_as` and `nintendo_mode`. Per-game layouts apply at launch and restore your own on exit | Global: **yes**. Per-game: needs plugin |
| **Panel overdrive** (LCD response-time boost) | asus-armoury `panel_overdrive` (or legacy asus-nb-wmi `panel_od`) | Firmware setting; also re-applied on load |
| **Boot sound** (ROG chime) | asus-armoury `boot_sound` | Firmware setting |

With **Steam Input** selected, M1/M2 appear as back paddles (L4/R4) in each
game's Steam controller layout, which is where per-game macros, key binds and
action-layer shifts belong. Steam already stores those per game.

## Hardware safety
Following the "nothing that could hurt the hardware" rule:
- **No** TDP, clocks, voltages, undervolting, fan curves, thermal policy (`ppt_*`, `throttle_thermal_policy`, `pwm*`).
- **No** raw MCU/EC commands and **no** firmware flashing. Lighting and button changes go through Handheld Daemon, which owns the controller.
- Direct writes only to documented kernel attributes: `charge_control_end_threshold`, `panel_overdrive`/`panel_od`, `boot_sound`.
- On uninstall the plugin sets the charge limit back to 100% and restores your own button layout.

### Deliberately left out
| Idea | Why |
|---|---|
| Separate left/right ring colors | HHD's Ally driver exposes one color for all four zones. Per-zone needs raw HID packets sent behind HHD's back, which would conflict with it and isn't documented. |
| MCU powersave / "Extreme standby" | HHD hides it unless `HHD_ALLY_POWERSAVE` is set, because it can leave the controller unresponsive after sleep. |
| Saving an effect straight into the MCU | Same reason (undocumented command). The HHD boot/charging options above cover the "lit before HHD starts" case safely. |
| VRR toggle | Steam's own Performance menu handles it under gamescope, and Vex Performance owns that Steam profile, so a second writer would fight it. |
| Fan curves, TDP presets | Excluded by the hardware-safety rule. TDP already lives in Vex Performance. |

## Install (Game Mode)
1. Copy `Ally-Tweaks.zip` to the Ally.
2. Decky → gear → General → enable **Developer mode**.
3. Developer → **Install Plugin from Zip** → pick the zip.

Needs Handheld Daemon (default on Bazzite) for lighting and buttons. Battery
and panel options also work without it.

## Notes
- Changing back-button settings makes HHD restart its virtual controller, which takes about a second. Per-game layouts change at game launch, before most games look for a controller.
- If HHD's Dualsense **LED Support** is on, games control the rings and the plugin shows a warning.
- **Untested on real hardware.** HHD keys and sysfs paths were checked against HHD `master` (Nov 2026) and Linux `master` (asus-armoury, sysfs-platform-asus-wmi), not on a device.

## Build from source
```
pnpm install
pnpm build
./package.sh   # out/Ally-Tweaks.zip
```
