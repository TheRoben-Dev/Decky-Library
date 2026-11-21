# Amazon Library

Your Amazon Games library (Prime Gaming / Luna claims and Amazon purchases) in Steam Game Mode, Nightgrid-styled.
Unofficial: this handheld signs in as an Amazon Games device, the same way the Windows app and Heroic do.

## What it does

- **Sign in from your phone, no typing.** Open the library and scan the QR code. The page on your phone has an
  *Open Amazon sign-in* button; sign in there, then copy the amazon.com address you land on and paste it back
  into the first tab. The handheld finishes the sign-in. Your password never touches the handheld, and you can
  remove it any time under Amazon → Your account → Your devices.
- **Full-screen library** (Open library in Quick Access): tabs for **Free games**, **All**, **Installed**,
  **Updates** and **Downloads**. L1/R1 switch tabs, A opens a game, X installs or plays it from the grid.
- **Installs through Proton.** Every Amazon game is a Windows game. Files come straight from Amazon's servers,
  four at a time, and each one is checked against Amazon's signed manifest before it's used.
- **Steam shortcuts with artwork.** After an install the game is added to Steam (set to Proton) with capsule,
  wide, hero, logo and icon art drawn from Amazon's own box art, background and logo in the Nightgrid look.
  Launch options carry what Amazon's Fuel SDK expects, and the plugin fetches the small Amazon Games SDK once
  for the games that load it.
- **Updates** only download the files that changed and delete the ones the new version dropped. Anything else
  in the game folder (saves, configs) is left alone. Updates are checked when you open the library (at most
  every 6 hours) or with *Check for updates*.
- **Verify files** re-checks every file and re-downloads only damaged or missing ones.
- **Uninstall** removes the game folder and its Steam shortcut. Most games keep saves in their Proton prefix, so
  that's kept unless you pick *Uninstall + delete saves*.
- **SD card support:** pick Internal or any mounted SD card / USB drive under Settings → Install to. Games go
  to `<drive>/Games/amazon/<Title>-<id>`.
- **Resumes** an interrupted install: files already downloaded are kept (after a hash check). Cancelling a first
  install removes its folder.
- Nothing runs in the background. The library list is cached for 30 minutes; there's no polling.

## What Amazon doesn't allow (honest limits)

- **No store to browse or buy from.** Amazon has no public storefront API for its PC games. The **Free games**
  tab shows this month's free games with Prime instead, marking the ones that are codes for other stores
  (GOG, Epic, ...). Claiming happens on Amazon's site: scan the QR (or open it in Steam's browser), claim, then
  press *I claimed it* and the game shows up under All. Amazon moved these claims to Luna in late 2025; if the
  list can't load, the claims page still works.
- **No native Linux builds.** Amazon only ships Windows builds, so everything runs through Proton.
- **Setup steps** some games list (Visual C++/DirectX installers) aren't run, because Proton already ships those
  runtimes. If a game won't start, try another Proton version in Settings or the game's Steam properties.
- **Games with third-party launchers or anti-cheat** behave as they do anywhere else under Proton.

## Phone sign-in won't open?

The QR page is served by the handheld itself on port 47615 (up to 47619), so your phone has to be on the same Wi-Fi
(not mobile data or a guest network, which keeps devices apart). Fedora-based systems such as Bazzite run a firewall;
the plugin can't change it without root, but it reads the firewall's rules and puts the page on a port they already
allow. If none is allowed, the sign-in screen says so and shows the one command that fixes it for every store
plugin, to run once in Desktop Mode (Konsole):

```
sudo firewall-cmd --permanent --add-port=47615-47619/tcp && sudo firewall-cmd --reload
```

Your phone may label the page "Not secure". That's expected for a page on your own network (there are no
certificates for local addresses); nothing on it goes through the internet, and it closes after you sign in.

## Files

- Settings and tokens: `~/homebrew/settings/Amazon Library/settings.json` (mode 600). Installed games: `installed.json`.
- Cache, manifests, icons and the SDK: `~/homebrew/data/Amazon Library/`.

## Build

```
pnpm install && pnpm build && ./package.sh   # -> out/Amazon-Library.zip
python3 -m unittest discover -s tests
```

Untested on hardware as of 0.1.0 (the cloud build can't reach Amazon). See THIRD_PARTY.md for credits.
