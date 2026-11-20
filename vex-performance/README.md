# Vex Performance (Decky Loader plugin)

One plugin for per-game "smart profiles" on a ROG Ally (or any handheld) running
Bazzite / SteamOS. Pick settings once per game; they apply automatically every
time the game launches. **No manual launch options needed.**

| Feature | How it's applied | When it takes effect |
|---|---|---|
| FSR 1 upscaling + sharpness | Steam's own per-game performance profile (`SteamClient.System.Perf.UpdateSettings`, "Sharp" scaling filter). gamescope gets it from Steam. | Immediately |
| Render resolution (80–90%) | `SteamClient.Apps.SetAppResolutionOverride` (the "Game resolution" in Properties) | Next game launch |
| Frame cap + matched refresh | Same Steam perf profile (`fps_limit`, `display_refresh_manual_hz`). "Match" picks the lowest whole multiple inside the panel's range, e.g. 40 fps → 80 Hz, 45 → 90 Hz. | Immediately |
| TDP | Auto-picks a path that doesn't fight anything: **Steam's own TDP slider** (on Bazzite 44+ Steam routes it through steamos-manager / PowerStation) → **PowerStation** D-Bus (`org.shadowblip.GPU.Card.TDP`) when Steam's slider is hidden → direct asus-armoury sysfs. Stays **off** if SimpleDeckyTDP / PowerTools / PowerControl are installed, or if the retired Handheld Daemon is still running. HHD is only used if you pick "Handheld Daemon (legacy)" by hand. | Immediately |
| GPU clock | PowerStation (`ManualClock`, `ClockValueMhzMin/Max`), else amdgpu `pp_od_clk_voltage`. Steam no longer has a per-game GPU clock setting. Back to Auto when no game runs. | Immediately |
| lsfg-vk frame gen (per game, off by default) | **Bundled:** the official lsfg-vk 2.0.0 build ships inside the zip and is installed into `~/.local` automatically the first time you enable frame gen (skipped if the Decky LSFG-VK plugin or a distro package already provides it). Enabling FG for a game adds a `[[profile]]` with `active_in = ["<appid>"]` to `~/.config/lsfg-vk/conf.toml`; lsfg-vk matches it via Steam's `SteamAppId`. The optional `ENABLE_GAMESCOPE_WSI=0` workaround is added to / removed from the game's launch options by the plugin; your own options are kept. | Next game launch |

Presets: Battery (40/80 Hz, 12 W, 720p→FSR), Balanced (45/90, 17 W, 900p), Performance (60/120, 25 W, 972p), Heavy AAA (40/80 + 2x FG, 30 W, 864p).

## Install (Game Mode)
1. Copy `Vex-Performance.zip` to the Ally (e.g. `~/Downloads`).
2. Decky (QAM) → gear icon → General → enable **Developer mode**.
3. Developer tab → **Install Plugin from Zip** → pick the zip.
4. Open the plugin, launch a game, tap **Create profile for this game**, tune, done.

Frame gen needs no extra plugin. The only outside requirement is **Lossless Scaling**
(paid Steam app): its `lsfg-vk.dll` is proprietary and can't be bundled. Vex finds it in
your Steam library automatically; if it's missing, the plugin shows a button to its Store
page, and if it's on the wrong branch, a button to open it so you can pick the `lsfg-vk`
beta. If you also have the Decky LSFG-VK plugin, Vex uses its install, shares `conf.toml`,
and only deletes profiles/files it created itself.

## Build from source
```
pnpm install
pnpm build          # -> dist/index.js
./package.sh        # -> out/Vex-Performance.zip (downloads + verifies lsfg-vk)
```

## Bazzite 44 note
Bazzite 44 (Aug 2026) retired Handheld Daemon in favor of InputPlumber, steamos-manager and PowerStation, and moved TDP into Steam's Quick Access menu. Vex follows that: Steam first, PowerStation second, HHD only as an opt-in legacy path for older images. If Steam's TDP slider is hidden on your device, Vex uses PowerStation directly. Note that OpenGamepadUI's overlay also writes TDP through PowerStation, so a change there lasts until the next game launch or profile edit.

## Releases
Bumping `version` in `package.json` on `main` publishes a GitHub release `vex-performance-v<version>` with the zip attached (see `.github/workflows/release-vex-performance.yml`).

## Known limits
- Steam's perf APIs are internal; a Steam client update can rename them. Vex
  shows a warning instead of failing if they're missing.
- Render-resolution override only works for games that honor Steam's game
  resolution; otherwise lower the resolution in the game's own menu (FSR still upscales it).
- Frame gen and per-game launch-option handling cover Steam games only, not
  non-Steam shortcuts.
- No live base-FPS readout; the <40 fps latency warning is based on your frame cap.
- Engine-based auto-suggestions are not implemented; use the presets as a start.

See [THIRD_PARTY.md](THIRD_PARTY.md) for lsfg-vk licensing (CC BY-NC-ND 4.0, shipped unmodified).
