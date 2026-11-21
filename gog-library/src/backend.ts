import { callable } from "@decky/api";
import type { LinkStatus } from "./phone";

export type Platform = "linux" | "windows" | "mac";

export interface Settings {
  signedIn: boolean;
  user: { id?: string; username?: string };
  root: string; home: string;
  prefer: "linux" | "windows";
  tool: string;
  language: string;
  languages: string[];
  art: "gog" | "nightgrid";
  keep_downloads: boolean;
}

/** An owned game (library) or a store game opened from Browse. */
export interface Game {
  id: number; title: string; url: string; cover: string; image?: string; vertical?: string;
  platforms: Platform[]; category?: string; short?: string; background?: string; preorder?: boolean;
  price?: string; free?: boolean; sale?: string; developer?: string;
}

/** A Browse/Search result from the GOG catalog. */
export interface StoreItem {
  id: number; title: string; slug: string; url: string; cover: string; vertical: string; price: string; free: boolean;
  amount: number | null; sale: string; platforms: Platform[]; controller: boolean; type: string; developer: string; state: string;
  publisher: string; features: string[]; genres: string[]; tags: string[]; rating: number | null; reviews: number; released: string;
}

/** Store-page details for any GOG game (owned or not). */
export interface Details {
  id: number; description: string[]; screenshots: { full: string; thumb: string }[]; videos: { url: string; thumb: string; name: string }[];
  genres: string[]; themes: string[]; modes: string[]; developers: string[]; publishers: string[]; released: string;
  rating: number | null; languages: number;
}
export interface BrowseOpts { sort: string; price: string; genre: string; controller: string; platform: string; query: string; page: number }

export interface Option { kind: "linux" | "windows"; version: string; size: number; language: string }

export interface Installed {
  game_id: number; title: string; cover: string; url: string; method: "linux" | "galaxy" | "installer";
  kind: "linux" | "windows"; version: string; build_id: string; root: string; dir: string; exe: string; args: string;
  workdir: string; installer: boolean; appid: number; installed_at: number; size: number; present: boolean;
  update: boolean; update_name: string;
}

export interface Job {
  game_id: number; title: string; action: "install" | "update";
  phase: "queued" | "preparing" | "downloading" | "unpacking" | "merging" | "finishing" | "done" | "error" | "cancelled";
  done: number; total: number; speed: number; error: string;
}

export interface Exe { path: string; kind: "linux" | "windows"; score: number; size: number; args: string }
export interface Root { path: string; label: string; free: number }
type Fail = { ok: false; error: string; status?: number };

export const getSettings = callable<[], Settings>("settings_get");
export const signIn = callable<[pasted: string], { ok: boolean; message: string; settings: Settings }>("sign_in");
export const loginUrl = callable<[], string>("login_url");
export const signOut = callable<[], Settings>("sign_out");
export const handoffStart = callable<[], LinkStatus>("handoff_start");
export const handoffStatus = callable<[], LinkStatus>("handoff_status");
export const handoffStop = callable<[], boolean>("handoff_stop");
export const setOptions = callable<[opts: Partial<Settings>], { ok: true; settings: Settings } | Fail>("set_options");
export const getRoots = callable<[], Root[]>("roots");

export const getLibrary = callable<[refresh: boolean],
  { ok: true; games: Game[]; at: number; installed: Record<string, Installed>; jobs: Job[]; updatesDue: boolean } | Fail>("library");
export const getGame = callable<[gameId: number, hint: Partial<Game> | null],
  ({ ok: true; game: Game; owned: boolean; options: Option[]; dlcs: { id: number; title: string }[]; installed: Installed | null }) |
  (Fail & { game?: Game; owned?: boolean; installed?: Installed | null; options?: Option[] })>("game");
export const browse = callable<[opts: BrowseOpts], { ok: true; items: StoreItem[]; page: number; more: boolean; total: number } | Fail>("browse");
export const getDetails = callable<[gameId: number], ({ ok: true } & Details) | Fail>("details");
export const getArt = callable<[gameId: number, kind: string], { ok: true; data: string; ext: string } | Fail>("art");
export const saveIcon = callable<[gameId: number, png: string], { ok: true; path: string } | Fail>("save_icon");

export const getQueue = callable<[], Job[]>("queue");
export const install = callable<[gameId: number, kind: string], { ok: true; jobs: Job[] } | Fail>("install");
export const cancel = callable<[gameId: number], Job[]>("cancel");

export const setShortcut = callable<[gameId: number, appid: number], Installed | null>("set_shortcut");
export const getExecutables = callable<[gameId: number], Exe[]>("executables");
export const setExe = callable<[gameId: number, path: string], { ok: true; installed: Installed } | Fail>("set_exe");
export const uninstall = callable<[gameId: number, deletePrefix: boolean], { ok: true; appid: number } | Fail>("uninstall");
export const checkUpdates = callable<[], { ok: true; updates: number; checked: number; installed: Record<string, Installed> } | Fail>("check_updates");
export const getInstalled = callable<[], Record<string, Installed>>("installed_list");
