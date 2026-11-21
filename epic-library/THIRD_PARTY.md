# Third-party code

Bundled into `dist/index.js`:

- **qrcode-generator** 1.5.2 by Kazuhiko Arase, MIT License (https://github.com/kazuhikoarase/qrcode-generator).
  Draws the sign-in and store QR codes.
- **react-icons** (MIT) and **tslib** (0BSD), as in the other Decky-Library plugins.

Bundled unmodified in `runtime/site/` (exact versions and SHA-256 hashes in `requirements-runtime.txt`), run as a
separate program and never linked into the plugin:

- **Legendary** 0.21.1 by Rodney and contributors, GNU GPL v3.0 or later. Source: https://github.com/derrod/legendary
  (also the `legendary-gl` sdist on PyPI). The license text ships in `runtime/site/legendary_gl-0.21.1.dist-info/licenses/LICENSE`.
- **requests** (Apache-2.0), **urllib3** (MIT), **idna** (BSD-3-Clause), **charset-normalizer** (MIT),
  **certifi** (MPL-2.0), **filelock** (MIT/Unlicense), **pycryptodomex** (BSD-2-Clause / public domain parts).
  Each package's license file is in its `*.dist-info` folder.

`runtime/lgd.py` (starts Legendary) and `runtime/launch.sh` (the Steam launch wrapper) are this plugin's own files,
BSD-3-Clause like the rest of it.
