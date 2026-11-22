# Lowpoly

A [CSS Loader](https://github.com/DeckThemes/SDH-CssLoader) theme for Steam Game Mode, inspired by the low-poly 3D look of late-90s 32-bit consoles. It's an original design, not a copy of any console's interface, logos or trademarks.

![Lowpoly in four accents: Cobalt, Jade, Amber, Violet (mock-up preview)](docs/preview.png)

## Look

- **Backdrop:** a night-sky *gouraud* wash (vertex-colour gradients) with a layer of flat-shaded low-poly facets and a 4×4 ordered (Bayer) **dither** on top, like 15-bit colour output.
- **Controls:** square, **pixel-bevelled** blocks (light top-left edge, dark bottom-right edge) with gouraud fills.
- **Selection:** a bright gouraud accent polygon with dark text, framed by a chunky sprite-style outline.
- **Type:** **Pixelify Sans** (bundled, OFL) on labels, tabs and menus. Body text stays Steam's font so it's easy to read.
- **Headers** get a small gouraud-shaded triangle marker.
- **CRT:** optional static scanlines, or a "Tube" look with an aperture-grille tint and a vignette.

It covers Home, Library, game pages, Settings, the STEAM menu, Quick Access (and Decky panels), Friends & Chat, Store, Downloads, Search, Media, Achievements, the on-screen keyboard and notification toasts.

## Options (Quick Access → CSS Loader → Lowpoly)

| Option | Values | Default |
|---|---|---|
| Accent | Cobalt, Crimson, Jade, Amber, Violet, Teal, Slate, Custom (two color pickers: selection + gradient partner) | Cobalt |
| Dither | Off, Light, Heavy | Light |
| Polygons | on / off | on |
| CRT | Off, Scanlines, Tube | Scanlines |
| Font | Pixel labels, Pixel everywhere, Steam default | Pixel labels |
| Bloom | on / off (glow around focus) | on |
| Animations | Off, Subtle (stepped focus snaps, menu unfold), Full (+ cursor blink, cover wobble, download stripes) | Subtle |

The accent pair tints everything: surfaces, hairlines, backdrop, selection, toggles and bars all come from the two colors.

## Install

1. Download `Lowpoly.zip` from the latest `lowpoly-theme-v*` release.
2. Extract it into `~/homebrew/themes/`, so that you get `~/homebrew/themes/Lowpoly/theme.json`. You can also run `install.sh` next to the zip.
3. Go to Quick Access → CSS Loader → Refresh, then enable **Lowpoly**. Turn off other full themes, such as Nightgrid, first.

The folder must be named `Lowpoly`, because the bundled font is loaded from `/themes_custom/Lowpoly/`.

## Performance

Everything is static except one-shot animations. The backdrop is a background on the page containers: it's painted once, with no fixed overlay. The CRT overlay is one static, non-interactive layer on Home/Library only, and it's never drawn over a running game. Looping animations (Full only) stop while a game runs, and Steam's own Low Performance Mode turns all animation off.

## Building

`./package.sh` creates `out/Lowpoly.zip`. Releases are published automatically by `.github/workflows/lowpoly-release.yml` when the `version` in `Lowpoly/theme.json` changes on `main` or a `claude/*` branch.

## Credits

- Selectors and structure follow this repo's Nightgrid theme. The selectors are CSS Loader stable class names.
- Font: [Pixelify Sans](https://github.com/eifetx/Pixelify-Sans), SIL Open Font License 1.1 (`Lowpoly/fonts/PixelifySans-OFL.txt`).
- License: MIT.
