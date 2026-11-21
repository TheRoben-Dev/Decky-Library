# Third-party code

Bundled into `dist/index.js`:

- **qrcode-generator** 1.5.2 by Kazuhiko Arase, MIT License (https://github.com/kazuhikoarase/qrcode-generator).
  Draws the sign-in and buy-on-phone QR codes.
- **react-icons** (MIT; the GOG logo icon comes from Simple Icons, CC0) and **tslib** (0BSD), as in the other
  Decky-Library plugins.

The Python backend uses only the standard library. Its GOG endpoints and file formats (sign-in, Galaxy content-system
builds, depot manifests and chunks, Linux installers) follow what is publicly documented by the open-source GOG
launchers (Heroic's gogdl, Lutris, Minigalaxy); none of their code is included.
