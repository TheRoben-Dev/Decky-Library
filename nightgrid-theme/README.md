# Nightgrid (CSS Loader theme)

A Steam Game Mode theme in the style of the Nightgrid homelab app: near-black canvas with a faint
dot/line grid, cyan for data (sliders, toggles, progress, counts), a magenta outlined selection with a
soft glow, yellow accents, hairline borders, uppercase letter-spaced labels with `// SECTION` markers,
and JetBrains Mono. Colors are Nightgrid's own design tokens (NIGHTGRID palette, plus its ICE and
BLOODLINE palettes as options).

Made for an ASUS ROG Ally (1080p) on Bazzite, works the same on any SteamOS-style Game Mode.

## Requirements
- Decky Loader + **CSS Loader** (DeckThemes) 2.1.x — the theme uses manifest v9.
- CSS Loader needs internet once to fetch its class-name table (it does this on its own); that's what
  maps the readable selectors in this theme to Steam's current hashed classes.

## Install
**Easiest:** install the [Nightgrid Updater](../nightgrid-updater/) plugin (Decky → Developer → Install
Plugin from Zip), open it from Quick Access and press **Install**. It also handles updates later.

**Manual:**
1. Get `Nightgrid.zip` (from the release / project files, or build it with `./package.sh`).
2. On the Ally, extract it so you end up with `~/homebrew/themes/Nightgrid/theme.json`
   (or run `./install.sh` next to the zip). The folder **must be named `Nightgrid`**: the bundled
   font is loaded from `/themes_custom/Nightgrid/fonts/`.
3. Quick Access (…) → CSS Loader → refresh, then enable **Nightgrid**.

## Options (CSS Loader → Nightgrid)
| Option | Values |
|---|---|
| Animations | Off · **Subtle** · Full (see below) |
| Palette | **Nightgrid** (default) · Ice · Bloodline |
| Colors | **From palette** · Custom → three color pickers: Selection (magenta), Data (cyan), Accent (yellow) |
| Grid | **Dots + grid** (Nightgrid's backdrop) · Lines · Off |
| Font | **Mono labels** (tabs, menus, headers, numbers) · Mono everywhere · Steam default |
| Glow | **Yes** · No (flat outlines, like Nightgrid's "reduce effects") |
| Scanlines | Yes · **No** (static CRT lines + vignette on Home/Library) |

## What it styles
| Area | Pages (CSS Loader tabs) | File |
|---|---|---|
| Tokens, fonts | all | `css/tokens.css`, `css/fonts.css` |
| Steam color variables (grey/blue/green scales, sliders, progress, presence) | bigpicture, MainMenu, QuickAccess | `css/accents.css` |
| Buttons, toggles, sliders, dialogs, context menus (incl. the power menu), settings + game properties | bigpicture, MainMenu, QuickAccess | `css/controls.css` |
| Uppercase labels, `// ` and `> ` header markers | bigpicture, MainMenu, QuickAccess | `css/labels.css` |
| Home, Library, game page panels, placeholders, grid canvas | bigpicture | `css/canvas.css` |
| Top bar, bottom button bar, tab strips, focus ring, covers, Play/Install button | bigpicture | `css/shell.css` |
| STEAM menu, incl. the in-game version (game column, guides) | MainMenu | `css/mainmenu.css` |
| Quick Access menu (and Decky's panel inside it) | QuickAccess | `css/qam.css` |
| Friends list and chat windows | QuickAccess, bigpicture | `css/chat.css` |
| Downloads, Search, Media, Achievements (page, game tab, in-game menu), on-screen keyboard, volume pop-in | bigpicture, MainMenu, QuickAccess | `css/pages.css` |
| Notification toasts and the notification list | bigpicture, QuickAccess, toasts | `css/toasts.css` |
| Steam Store and Steam Community pages opened in Game Mode | store | `css/store.css` |

The in-game overlay is covered through the STEAM menu and Quick Access windows (that's what Game Mode
shows over a running game), plus toasts and the keyboard.

### What CSS can't reach
- **The game itself and anything a game draws** (its own menus, in-game overlays like MangoHud).
- **The boot/splash video and the gamescope layer** (performance overlay, scaling), which aren't web pages.
- **The lock screen / PIN pad.** Not targeted yet: no verified class names for it. If you use a PIN, send
  me a screenshot over CEF debugging and I can add it.
- **Store fonts.** The store is a different web origin, so the bundled JetBrains Mono can't load there; the
  store gets the colors and shapes, and Steam's fonts.
- **Colors a page sets inline** (sale pages, category art, branded events) are left alone on purpose.
- **Points Shop keyboard themes** keep their own look; only Steam's default keyboard is restyled.

Every control is square (`--ng-radius: 0`), including Steam's focus ring and the row/toggle highlights,
so the focus box always lines up with the control.

Color roles follow the app: **magenta** = what's selected/focused, **cyan** = data and "on" states,
**green** = ready/online/Play, **yellow** = accent, **red** = destructive. Bright fills (focused Play /
Install / primary buttons) use dark text, since white on cyan or green fails contrast.

## Animations
| | Subtle (default) | Full adds |
|---|---|---|
| Focus | focus ring fades in; tabs, buttons, menu rows "lock on" with a tiny scale | soft magenta pulse on the focus ring |
| Tabs | magenta bar grows in on the newly selected tab | |
| Panels | dialogs slide up, context/power menus scale in, settings pages fade, Quick Access title slides in, toasts slide in from the right, keyboard rises | settings and Quick Access rows cascade in |
| Headers | blinking `_` cursor after the big `// TITLE`s; section headers wipe in | typewriter-style reveal |
| Progress | | moving stripes on download bars |

Everything animates only `opacity`/`transform` (the header wipe uses `clip-path` on a few short
labels, once). One-shot effects run when focus moves or a panel opens, so an idle screen does nothing
but blink one cursor. Loops stop while a game is running (detected from Steam's in-game overlay
background and the running-game column in the STEAM menu), `prefers-reduced-motion` turns all of it off,
and so does Steam's own LowPerfMode. CSS can't animate the page change itself (Steam swaps the whole
page), and tabs are separate elements, so the selected-tab bar grows in place rather than sliding over.

## Performance
Without animations everything is static: the grid is a background on the page containers (one paint, no fixed overlay),
the only effects are a box-shadow glow on the focused element and the optional static scanlines.
No animations, no `backdrop-filter`, no blend modes. Two of Steam's own focus fade animations are
swapped for equivalent Nightgrid ones (otherwise they'd override the colors).

## How the selectors were chosen
Selectors use CSS Loader's stable names (`module_ClassName`, e.g. `.mainmenu_Menu`), which CSS Loader
rewrites to Steam's hashed classes when injecting, so the theme survives Steam updates as long as the
table is updated. Theme format and tab names were checked against the CSS Loader source
(DeckThemes/SDH-CssLoader 2.1.3: `css_theme.py`, `css_themepatch.py`, `css_themepatchcomponent.py`,
`css_inject.py`). Every stable name used here also appears in recent themes verified on hardware in
Oct–Nov 2026 — mainly [Slate](https://github.com/rrambul/slate-steam-deck) (MIT, its `docs/selectors.md`
records each selector as captured over CEF DevTools), tvOS Deck and Windows 95 for Deck. Store pages and
a few Steam components have no stable names; those are matched by hash substring (`[class*="…-"]`),
which simply stops matching if Valve renames them. Lessons reused from there:
- MainMenu and QuickAccess load Steam's CSS *after* CSS Loader's, so rules carry a `.BasicUI` prefix.
- Class names like `Play`/`Launch` collide with CSS Loader translation names; they're matched with
  partial-word substrings instead.
- `mainmenu_Item` has two hashes in the table; the older one is matched by substring as well.

**Not yet checked on the Ally.** If something looks off, enable CSS Loader's unminify mode (its
settings) and use CEF remote debugging (`<ally-ip>:8081`) to read the element's stable name.

## Build and release
```
./package.sh   # → out/Nightgrid.zip
```
Releases (what the updater installs) are made by tagging `nightgrid-theme-vX.Y.Z` with the same version
as `theme.json`; see [nightgrid-updater](../nightgrid-updater/README.md#releasing-maintainer).

## Credits / licenses
- Theme: MIT (`LICENSE`).
- JetBrains Mono: SIL OFL 1.1 (`Nightgrid/fonts/JetBrainsMono-OFL.txt`).
- Design tokens from the Nightgrid app by TheRoben-Dev.
