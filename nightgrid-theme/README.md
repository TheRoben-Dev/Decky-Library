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
1. Get `Nightgrid.zip` (from the release / project files, or build it with `./package.sh`).
2. On the Ally, extract it so you end up with `~/homebrew/themes/Nightgrid/theme.json`
   (or run `./install.sh` next to the zip). The folder **must be named `Nightgrid`**: the bundled
   font is loaded from `/themes_custom/Nightgrid/fonts/`.
3. Quick Access (…) → CSS Loader → refresh, then enable **Nightgrid**.

## Options (CSS Loader → Nightgrid)
| Option | Values |
|---|---|
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
| Buttons, toggles, sliders, dialogs, context menus, settings rows and sidebar | bigpicture, MainMenu, QuickAccess | `css/controls.css` |
| Uppercase labels, `// ` and `> ` header markers | bigpicture, MainMenu, QuickAccess | `css/labels.css` |
| Canvas + grid, Library, game page panels, placeholders | bigpicture | `css/canvas.css` |
| Top bar, bottom button bar, tab strips, focus ring, covers, Play/Install button | bigpicture | `css/shell.css` |
| STEAM menu (rail) | MainMenu | `css/mainmenu.css` |
| Quick Access menu, friends list | QuickAccess | `css/qam.css` |
| Notification toasts | bigpicture, QuickAccess, toasts | `css/toasts.css` |

Color roles follow the app: **magenta** = what's selected/focused, **cyan** = data and "on" states,
**green** = ready/online/Play, **yellow** = accent, **red** = destructive. Bright fills (focused Play /
Install / primary buttons) use dark text, since white on cyan or green fails contrast.

## Performance
Everything is static: the grid is a background on the page containers (one paint, no fixed overlay),
the only effects are a box-shadow glow on the focused element and the optional static scanlines.
No animations, no `backdrop-filter`, no blend modes. Two of Steam's own focus fade animations are
swapped for equivalent Nightgrid ones (otherwise they'd override the colors).

## How the selectors were chosen
Selectors use CSS Loader's stable names (`module_ClassName`, e.g. `.mainmenu_Menu`), which CSS Loader
rewrites to Steam's hashed classes when injecting, so the theme survives Steam updates as long as the
table is updated. Theme format and tab names were checked against the CSS Loader source
(DeckThemes/SDH-CssLoader 2.1.3: `css_theme.py`, `css_themepatch.py`, `css_themepatchcomponent.py`,
`css_inject.py`). Every stable name used here also appears in recent themes verified on hardware in
Nov 2026 — mainly [Slate](https://github.com/rrambul/slate-steam-deck) (MIT, its `docs/selectors.md`
records each selector as captured over CEF DevTools) and tvOS Deck. Lessons reused from there:
- MainMenu and QuickAccess load Steam's CSS *after* CSS Loader's, so rules carry a `.BasicUI` prefix.
- Class names like `Play`/`Launch` collide with CSS Loader translation names; they're matched with
  partial-word substrings instead.
- `mainmenu_Item` has two hashes in the table; the older one is matched by substring as well.

**Not yet checked on the Ally.** If something looks off, enable CSS Loader's unminify mode (its
settings) and use CEF remote debugging (`<ally-ip>:8081`) to read the element's stable name.

## Build
```
./package.sh   # → out/Nightgrid.zip
```

## Credits / licenses
- Theme: MIT (`LICENSE`).
- JetBrains Mono: SIL OFL 1.1 (`Nightgrid/fonts/JetBrainsMono-OFL.txt`).
- Design tokens from the Nightgrid app by TheRoben-Dev.
