import { callable } from "@decky/api";
import type { LinkStatus } from "./phone";

export interface Settings {
  signedIn: boolean;
  user: { id?: string; name?: string };
  root: string; home: string;
  tool: string;
}

export interface Game {
  id: string; entitlement: string; sku: string; title: string;
  icon: string; cover: string; background: string; logo: string;
  short: string; developer: string; publisher: string; genres: string[]; released: string; screenshot: string; added: string;
  description?: string; screenshots?: string[]; modes?: string[]; rating?: string; website?: string;
}

/** A free game with Prime (Prime Gaming / Luna). `direct` ones land in the Amazon library once claimed. */
export interface Offer {
  id: string; title: string; ends: string; direct: boolean; image: string; publisher: string; short: string;
  claimed: boolean; can_claim: boolean; prime: boolean; link_needed: boolean;
  description?: string; screenshots?: string[]; developer?: string; genres?: string[]; modes?: string[]; released?: string;
  rating?: string; website?: string; logo?: string; background?: string;
}

export interface Installed {
  game_id: string; entitlement: string; sku: string; title: string; icon: string; cover: string; background: string; logo: string;
  version: string; root: string; dir: string; exe: string; args: string; cwd: string; picked: boolean;
  post_install: number; fuel: boolean; appid: number; installed_at: number; size: number;
  present: boolean; update: boolean; launch: string;
}

export interface Job {
  game_id: string; title: string; action: "install" | "update" | "repair";
  phase: "queued" | "preparing" | "downloading" | "finishing" | "done" | "error" | "cancelled";
  done: number; total: number; speed: number; error: string;
}

export interface Exe { path: string; score: number; size: number; fuel?: boolean }
export interface Root { path: string; label: string; free: number }
export interface Img { data: string; ext: string }
type Fail = { ok: false; error: string; status?: number };

export const getSettings = callable<[], Settings>("settings_get");
export const setCode = callable<[text: string], { ok: boolean; message: string; settings: Settings }>("set_code");
export const signOut = callable<[], Settings>("sign_out");
export const handoffStart = callable<[], LinkStatus>("handoff_start");
export const handoffStatus = callable<[], LinkStatus>("handoff_status");
export const handoffStop = callable<[], boolean>("handoff_stop");
export const setOptions = callable<[opts: Partial<Settings>], { ok: true; settings: Settings } | Fail>("set_options");
export const getRoots = callable<[], Root[]>("roots");

export const getLibrary = callable<[refresh: boolean],
  { ok: true; games: Game[]; at: number; installed: Record<string, Installed>; jobs: Job[]; updatesDue: boolean } | Fail>("library");
export const getGame = callable<[gameId: string], { ok: true; game: Game; installed: Installed | null } | Fail>("game");
export const getOffers = callable<[refresh: boolean], ({ ok: true; items: Offer[]; claims: string }) | (Fail & { claims: string })>("offers");
export const getArt = callable<[gameId: string],
  { ok: true; cover: Img; background: Img | null; logo: Img | null; title: string } | Fail>("art");
export const saveIcon = callable<[gameId: string, png: string], { ok: true; path: string } | Fail>("save_icon");

export const getQueue = callable<[], Job[]>("queue");
export const install = callable<[gameId: string, repair: boolean], { ok: true; jobs: Job[] } | Fail>("install");
export const cancel = callable<[gameId: string], Job[]>("cancel");

export const setShortcut = callable<[gameId: string, appid: number], Installed | null>("set_shortcut");
export const getExecutables = callable<[gameId: string], Exe[]>("executables");
export const setExe = callable<[gameId: string, path: string], { ok: true; installed: Installed } | Fail>("set_exe");
export const uninstall = callable<[gameId: string, deletePrefix: boolean], { ok: true; appid: number } | Fail>("uninstall");
export const checkUpdates = callable<[], { ok: true; updates: number; checked: number; installed: Record<string, Installed> } | Fail>("check_updates");
export const getInstalled = callable<[], Record<string, Installed>>("installed_list");
