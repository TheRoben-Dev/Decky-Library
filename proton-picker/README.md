# Proton Picker

Decky Loader plugin that picks a Proton build for each game, installs the builds it needs, applies the choice automatically and rolls back if a game breaks. Built for the ROG Ally on Bazzite; works on any SteamOS-style Steam setup.

## What it does
- **Per-game pick, no launch options.** Sets the game's compatibility tool through Steam's own `SteamClient.Apps.SpecifyCompatTool`, the same thing as Properties → Compatibility → "Force the use of a specific tool".
- **Auto mode for the whole library.** Runs a check about 8 s after Steam starts and every 6 h after that:
  - native Linux build → left alone
  - ProtonDB **Platinum**, or Steam Deck **Verified** → left on Steam's default Proton
  - Gold / Silver / Bronze / Borked / no reports → newest **GE-Proton** (or **Proton-CachyOS** if you prefer it), then the other custom build, then Proton Experimental
  - ProtonDB's trending tier is used once a game has 5+ reports, so recent breakage or fixes count.
- **Never overrides you.** A version you set in Steam's Properties is left alone, and so is any game you pin or set to "Hands off" in the plugin.
- **Installs builds.** Downloads the latest GE-Proton (`GloriousEggroll/proton-ge-custom`) or Proton-CachyOS (`CachyOS/proton-cachyos`, the plain `x86_64` build as its release notes recommend) into `~/.local/share/Steam/compatibilitytools.d`, the same folder ProtonPlus / ProtonUp-Qt use. Checks SHA-512 when the release publishes a checksum, unpacks into a temp folder and only moves a complete tool into place. It only downloads while no game is running.
- **Rollback.** One tap returns a game to its previous build (10 steps of history). If a game closes within 45 s on a build it hasn't run on before, it rolls back on its own and tells you. After 2 minutes of play the build counts as working for that game.
- **Cleanup.** "Remove unused old builds" deletes only builds this plugin installed, that aren't the newest of their family, and that no game uses or keeps for rollback.

## Bazzite notes
- Bazzite recommends ProtonPlus for custom Proton. Both install into the same folder, so builds from either tool are listed and used, and neither gets in the other's way. System-wide builds in `/usr/share/steam/compatibilitytools.d` are used but never removed.
- Steam only scans for new compatibility tools when it starts. After an install, the plugin shows "Restart Steam now". If you skip it, games switch over the next time Steam starts.

## Limits
- ProtonDB only publishes per-game summaries (tier, trending tier, report count) at `/api/v1/reports/summaries/<appid>.json`. It doesn't publish which Proton version each report used, so the pick follows the rules above. It doesn't vote on versions.
- Non-Steam shortcuts aren't auto-managed.
- If ProtonDB can't be reached, Auto skips games it has no rating for and tries again on the next check.

## Build
```
pnpm install
pnpm build
./package.sh   # out/Proton-Picker.zip
```
Install the zip from Decky → Developer → Install Plugin from Zip. The backend runs as your user (no root flag).
