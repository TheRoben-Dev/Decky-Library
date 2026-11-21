# Storage Sweep

Frees space that uninstalled games leave behind, and resets single shader caches, from Quick Access.

| What | Where | Safe? |
|---|---|---|
| Shader caches of removed games | `<library>/steamapps/shadercache/<appid>` | Always. Rebuilt on reinstall. |
| Workshop files of removed games | `<library>/steamapps/workshop/content/<appid>` | Yes. Steam re-downloads on reinstall. |
| Proton prefixes of removed games | `<library>/steamapps/compatdata/<appid>` | Check first: can hold saves not in Steam Cloud. Confirm dialog lists them. |
| Shader cache of an installed game | `shadercache/<appid>` | Yes. Fixes stutter/glitches after driver or Proton updates; rebuilds while you play. |

## Safety
- Scans every library from `libraryfolders.vdf` (internal, SD card, external). A game counts as installed if any library has its `appmanifest` **or** `libraryfolders.vdf` lists it, so games on an SD card that isn't inserted stay safe.
- If any library is unreachable, Proton prefixes aren't offered at all.
- Non-Steam shortcut prefixes are never touched; shortcut shader caches only when the shortcut is gone from your library.
- The running game is skipped. Every delete is re-checked in the backend: only a canonical `steamapps/{shadercache,compatdata,workshop/content}/<number>` folder, never a symlink.
- If no installed games can be found (Steam files unreadable), nothing is marked as left behind.

## Light on resources
Nothing runs until you press **Scan**; results stay in memory until you scan again. No polling, no startup work. Runs as the normal user.

Tests: `python3 -m unittest discover -s tests`.
