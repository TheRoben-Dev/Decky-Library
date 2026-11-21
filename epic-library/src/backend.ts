import { callable } from "@decky/api";
import type { LinkStatus } from "./phone";

export interface Settings {
  signedIn: boolean;
  user: { id?: string; name?: string };
  root: string; home: string;
  tool: string;
  dlcs: boolean;
  show_all: boolean;
  problem: string;          // why Legendary can't run here ("" when fine)
}

/** A game the account owns (trimmed from Legendary's list). */
export interface Game {
  app: string; title: string; ns: string; catalog: string;
  tall: string; wide: string; logo: string;
  developer: string; description: string; version: string;
  installable: boolean; third_party: string; dlcs: number; cloud_saves: boolean;
}

/** A Browse/Search result from the Epic store. */
export interface StoreItem {
  id: string; ns: string; title: string; seller: string; description: string;
  tall: string; wide: string; url: string; checkout: string;
  free: boolean | null; price: string; original: string; sale: number;
  controller: boolean; released: string; until?: string;
}
export interface BrowseOpts { query: string; sort: string; price: string; genre: string; controller: boolean; country: string; page: number }
export interface BrowseResult {
  ok: true; items: StoreItem[]; page: number; more: boolean; total: number; note: string;
  genres: [string, string][]; controllerTag: boolean;
}

export interface Installed {
  app: string; title: string; dir: string; exe: string; version: string; latest: string; update: boolean;
  size: number; offline: boolean; verify: boolean; present: boolean; appid: number;
}

export interface Job {
  app: string; title: string; action: "install" | "update" | "repair";
  phase: "queued" | "preparing" | "downloading" | "finishing" | "done" | "error" | "cancelled";
  done: number; total: number; speed: number; error: string;
}

export interface Root { path: string; label: string; free: number }
type Fail = { ok: false; error: string; status?: number };

export const getSettings = callable<[], Settings>("settings_get");
export const signIn = callable<[text: string], { ok: boolean; message: string; settings: Settings }>("sign_in");
export const signOut = callable<[], Settings>("sign_out");
export const handoffStart = callable<[], LinkStatus>("handoff_start");
export const handoffStatus = callable<[], LinkStatus>("handoff_status");
export const handoffStop = callable<[], boolean>("handoff_stop");
export interface DeviceStatus {
  ok: boolean; state: "idle" | "waiting" | "finishing" | "done" | "error" | "expired";
  code: string; url: string; expires: number; error: string; message: string;
}
export const deviceStart = callable<[], DeviceStatus>("device_start");
export const deviceStatus = callable<[], DeviceStatus>("device_status");
export const deviceStop = callable<[], boolean>("device_stop");
export const setOptions = callable<[opts: Partial<Settings>], { ok: true; settings: Settings } | Fail>("set_options");
export const getRoots = callable<[], Root[]>("roots");

export const getLibrary = callable<[refresh: boolean],
  { ok: true; games: Game[]; at: number; installed: Record<string, Installed>; jobs: Job[]; updatesDue: boolean } | Fail>("library");
export const getGame = callable<[app: string],
  { ok: true; game: Game; installed: Installed | null; resume: boolean; partial: string } | Fail>("game");
export const installInfo = callable<[app: string], { ok: true; disk: number; download: number } | Fail>("install_info");
export const browse = callable<[opts: BrowseOpts], BrowseResult | Fail>("browse");
export const freeNow = callable<[country: string], { ok: true; items: StoreItem[] } | Fail>("free_now");
export const getImage = callable<[url: string], { ok: true; data: string; ext: string } | Fail>("image");
export const saveIcon = callable<[app: string, png: string], { ok: true; path: string } | Fail>("save_icon");

export const getQueue = callable<[], Job[]>("queue");
export const install = callable<[app: string, repair: boolean], { ok: true; jobs: Job[] } | Fail>("install");
export const cancel = callable<[app: string], Job[]>("cancel");
export const discard = callable<[app: string], { ok: true } | Fail>("discard");

export const setShortcut = callable<[app: string, appid: number], Installed | null>("set_shortcut");
export const shortcutInfo = callable<[app: string], { ok: true; installed: Installed; options: string } | Fail>("shortcut_info");
export const uninstall = callable<[app: string, deletePrefix: boolean], { ok: true; appid: number } | Fail>("uninstall");
export const checkUpdates = callable<[], { ok: true; updates: number; checked: number; installed: Record<string, Installed> } | Fail>("check_updates");
export const getInstalled = callable<[], Record<string, Installed>>("installed_list");
export const syncSaves = callable<[app: string, direction: "download" | "upload"], { ok: true; message: string } | Fail>("saves");
