import { callable } from "@decky/api";
import type { LinkStatus } from "./phone";

export type Platform = "linux" | "windows" | "mac" | "android";

export interface Settings {
  signedIn: boolean;
  user: { id?: number; username?: string; name?: string };
  root: string; home: string;
  prefer: "linux" | "windows";
  tool: string;
  show_all: boolean;
  keep_downloads: boolean;
  adult?: boolean;
  imported?: string;
}

export interface Game {
  id: number; title: string; short: string; url: string; cover: string; still: string;
  classification: string; author: string; platforms: Platform[]; key: number; added?: string;
  min_price?: number; can_buy?: boolean;
}

/** A Browse/Search result. Feed items have only a page URL until resolved to an id. */
export interface StoreItem {
  id?: number; title: string; url: string; cover: string; still?: string; price: string; free: boolean | null;
  platforms: Platform[]; author: string; sale: string;
}
export interface BrowseOpts {
  sort: string; price: string; genre: string; controller: string; platform: string; page: number;
  released: string; duration: string; multiplayer: string; accessibility: string; engine: string; tags: string[]; demo: boolean;
}

export interface Upload {
  id: number; filename: string; name: string; size: number; storage: string; type: string; build_id: number;
  version: string; channel: string; updated: string; platforms: Platform[]; demo: boolean; preorder: boolean; usable: boolean;
}

export interface Installed {
  game_id: number; title: string; cover: string; url: string; upload_id: number; upload_name: string; version: string;
  root: string; dir: string; exe: string; kind: "linux" | "windows"; args: string; installer: string; appid: number;
  installed_at: number; size: number; present: boolean; update: boolean; update_name: string;
}

export interface Job {
  game_id: number; title: string; action: "install" | "update";
  phase: "queued" | "preparing" | "downloading" | "unpacking" | "merging" | "finishing" | "done" | "error" | "cancelled";
  done: number; total: number; speed: number; error: string;
}

export interface Exe { path: string; kind: "linux" | "windows"; score: number; size: number; args: string }
export interface Root { path: string; label: string; free: number }
type Fail = { ok: false; error: string; status?: number; retry_after?: number };

export const getSettings = callable<[], Settings>("settings_get");
export const setKey = callable<[key: string], { ok: boolean; message: string; settings: Settings }>("set_key");
export const signOut = callable<[], Settings>("sign_out");
export const handoffStart = callable<[], LinkStatus>("handoff_start");
export const handoffStatus = callable<[], LinkStatus>("handoff_status");
export const handoffStop = callable<[], boolean>("handoff_stop");
export const setOptions = callable<[opts: Partial<Settings>], { ok: true; settings: Settings } | Fail>("set_options");
export const getRoots = callable<[], Root[]>("roots");

export const getLibrary = callable<[refresh: boolean],
  { ok: true; games: Game[]; at: number; installed: Record<string, Installed>; jobs: Job[]; updatesDue: boolean } | Fail>("library");
export const getGame = callable<[gameId: number],
  ({ ok: true; game: Game; owned: boolean; uploads: Upload[]; best: number; usable: number; installed: Installed | null }) |
  (Fail & { game?: Game; owned?: boolean; installed?: Installed | null })>("game");
export const browse = callable<[opts: BrowseOpts], { ok: true; items: StoreItem[]; page: number; more: boolean; notice?: string } | Fail>("browse");
export const search = callable<[query: string, page: number], { ok: true; items: StoreItem[]; page: number; more: boolean } | Fail>("search");
export const resolve = callable<[url: string], { ok: true; id: number } | Fail>("resolve");
export const getCover = callable<[gameId: number], { ok: true; data: string; ext: string } | Fail>("cover");
export const saveIcon = callable<[gameId: number, png: string], { ok: true; path: string } | Fail>("save_icon");

export const getQueue = callable<[], Job[]>("queue");
export const install = callable<[gameId: number, uploadId: number], { ok: true; jobs: Job[] } | Fail>("install");
export const cancel = callable<[gameId: number], Job[]>("cancel");

export const setShortcut = callable<[gameId: number, appid: number], Installed | null>("set_shortcut");
export const getExecutables = callable<[gameId: number], Exe[]>("executables");
export const setExe = callable<[gameId: number, path: string], { ok: true; installed: Installed } | Fail>("set_exe");
export const uninstall = callable<[gameId: number, deletePrefix: boolean], { ok: true; appid: number } | Fail>("uninstall");
export const checkUpdates = callable<[], { ok: true; updates: number; checked: number; installed: Record<string, Installed> } | Fail>("check_updates");
export const getInstalled = callable<[], Record<string, Installed>>("installed_list");

/** Rejects with a readable message if the backend doesn't answer in time (e.g. it failed to start). */
export function within<T>(p: Promise<T>, ms: number, what: string): Promise<T> {
  return new Promise<T>((ok, fail) => {
    const t = setTimeout(() => fail(new Error(`${what} didn't answer in ${Math.round(ms / 1000)} s. Restart Decky (Quick Access → Decky → settings) or reinstall the plugin, then try again.`)), ms);
    p.then((v) => { clearTimeout(t); ok(v); }, (e) => { clearTimeout(t); fail(e); });
  });
}
