# Nightgrid Control

Your [Nightgrid](https://github.com/TheRoben-Dev/nightgrid) hosts in Quick Access: which are online, CPU, memory,
fullest disk and temperature, plus **Wake**, **Reboot** and **Shut down**. Everything is done with the controller.

## Your existing Nightgrid setup, as it is

No new config format. Hosts come from one of these, in this order:

1. **An imported profile**: the file from Nightgrid's *Export profile…* (Settings → Data → Export). In the plugin, open
   **Import Nightgrid profile…**, pick the `.age` file from the list and enter its passphrase once (Steam's on-screen
   keyboard). The plugin looks in your home folder, Downloads, Documents, Desktop, `~/Nightgrid`, synced folders
   (Sync, Syncthing, Dropbox, Nextcloud, OneDrive) and SD cards / USB sticks. Hosts, groups, ports, users, jump hosts,
   tailnet addresses, MAC addresses, wake relays, sleep windows and client/server roles are all used as Nightgrid has
   them. Tick *Include saved passwords and tokens* when exporting if your hosts need a password for login or sudo.
2. **Nightgrid installed on this device**: its database is read directly (read-only). Nothing to set up, and hosts you
   add in Nightgrid appear here. Nightgrid's trusted host keys are used too.

The passphrase is never stored. The imported hosts and any saved passwords are kept in
`~/homebrew/settings/Nightgrid Control/profile.json` (mode 600). **Profile → Forget imported profile** removes them.

## How it reaches hosts

Like Nightgrid: plain SSH, nothing installed on the servers. One read-only shell script per check (`/proc`, `df`,
`/sys` temperatures). Windows hosts are read with PowerShell.

- **Light**: hosts are only contacted while the panel is open (every 15 s by default, adjustable), with one shared SSH
  connection per host that closes 90 s after the panel does. Nothing runs in the background.
- **Logins**: your SSH agent and keys in `~/.ssh` (a key path from another computer is matched by file name in
  `~/.ssh`), saved passwords from the profile, and an optional key for this device (**Profile → This device's key**).
  With saved passwords, the plugin can add that key to those hosts itself. Otherwise add the `.pub` file it saves next to
  your profile in Nightgrid (Settings → Connections → SSH keys → **+**).
- **Addresses**: the host's address, then its tailnet address if the first one doesn't answer (remembered per host).
  An `ssh_alias` from Nightgrid is used when this device's `~/.ssh/config` has it.
- **Host keys**: a host seen for the first time is trusted and remembered. A host whose key changed is refused and shows
  **Key changed**.

## Buttons

| Button | When | What it does |
|---|---|---|
| **Wake** | host offline, has a MAC address | Wake-on-LAN magic packet from this device (broadcast, UDP 9 and 7), plus from the wake relay host set in Nightgrid. |
| **Reboot** | host online | Asks first, then `systemctl reboot` through sudo (Windows: `shutdown.exe /r`). |
| **Shut down** | host online | Asks first, then `systemctl poweroff` through sudo (Windows: `shutdown.exe /s`). |
| **Check** | always | Checks that one host now. |

Sudo uses the profile's saved sudo or login password, or none if the host allows it (`NOPASSWD`). Without either,
reboot and shut down say so instead of trying.

States follow Nightgrid: **Online**, **Offline**, **Asleep** (inside the host's sleep window), **Away** (client devices),
**Login refused**, **Key changed**. Values from 80 % show in amber and from 90 % in red.

## Build

```
pnpm install && pnpm build && ./package.sh   # out/Nightgrid-Control.zip
python3 -m unittest discover -s tests -v
```

The profile reader is a small pure-Python age decryptor (scrypt + ChaCha20-Poly1305), tested against a file made by the
real `age` CLI.
