import { callable } from "@decky/api";

export interface Host {
  id: number; name: string; hostname: string; port: number; username: string | null;
  auth: string; proxyJump: string | null; alias: string | null; tailnet: string | null;
  mac: string | null; wakeRelay: number | null; sleepWindow: string | null;
  role: string; os: string; group: string | null; favorite: boolean; hasPassword: boolean;
}

export type HostState = "ok" | "offline" | "auth" | "hostkey" | "sleep" | "away" | "error"
  | "rebooting" | "stopping" | "waking";

export interface Status {
  id: number; state: HostState; at: number; error?: string; via?: string | null;
  cpu?: number | null; mem?: number | null; disk?: number | null; mount?: string | null;
  temp?: number | null; uptime?: number | null; load?: number | null;
}

export interface ProfileMeta {
  source: "file" | "local" | null; file?: string; importedAt?: number; createdAt?: number;
  appVersion?: string; passwords?: number; error?: string;
}

export interface Prefs { interval: number; showClients: boolean }

export interface ProfileFile { path: string; name: string; size: number; mtime: number }

type Fail = { ok: false; error: string };
type Ok<T> = ({ ok: true } & T) | Fail;

export const getState = callable<[], Ok<{ profile: ProfileMeta; hosts: Host[]; status: Status[]; prefs: Prefs; localAvailable: boolean }>>("get_state");
export const refresh = callable<[ids?: number[] | null], Ok<{ status: Status[] }>>("refresh");
export const findProfiles = callable<[], Ok<{ files: ProfileFile[] }>>("find_profiles");
export const importProfile = callable<[path: string, passphrase: string], Ok<{ hosts: number; passwords: number }> & { wrong?: boolean }>("import_profile");
export const forgetProfile = callable<[], Ok<{}>>("forget_profile");
export const setPrefs = callable<[patch: Partial<Prefs>], Ok<{ prefs: Prefs }>>("set_prefs");
export const power = callable<[hostId: number, action: "reboot" | "shutdown"], Ok<{}>>("power");
export const wake = callable<[hostId: number], Ok<{ relay: string | null }>>("wake");
export const deviceKey = callable<[create: boolean], Ok<{ exists: boolean; pub?: string; fingerprint?: string; path?: string; exported?: string | null }>>("device_key");
export const installKey = callable<[], Ok<{ done: { name: string }[]; failed: { name: string; error: string }[] }>>("install_key");
