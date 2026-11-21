# Third-party code and references

Bundled into `dist/index.js`:

- **qrcode-generator** 1.5.2 by Kazuhiko Arase, MIT License (https://github.com/kazuhikoarase/qrcode-generator).
  Draws the sign-in and claim QR codes.
- **react-icons** (MIT) and **tslib** (0BSD), as in the other Decky-Library plugins.

Protocol reference (no code copied):

- **Nile** by imLinguin (https://github.com/imLinguin/nile, GPL-3.0), the open-source Amazon Games client Heroic uses.
  Its source documents the Amazon Games endpoints, request bodies and manifest format this plugin talks to.
  The backend here is an independent implementation using only the Python standard library, so nothing from
  Nile is bundled and the plugin stays BSD-3-Clause like the rest of the repository.
- Amazon's manifest-signing public key is included as data so downloads can be verified.
