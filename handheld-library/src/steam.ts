/*
 * Everything that touches Steam's library internals lives here.
 *
 * Verified against the Steam client's own library code (SteamTracking ClientExtracted/steamui/ui.js,
 * Nov 2026) and TabMaster:
 * - appStore overviews expose getters unpacked from steam_hw_compat_category_packed:
 *   steam_deck_compat_category (0 unknown, 1 unsupported, 2 playable, 3 verified),
 *   steam_os_compat_category (0 unknown, 1 unsupported, 2 compatible) and has_native_linux_binaries.
 * - Controller support is xbox_controller_support (EAppControllerSupportLevel: -1 unknown, 0 none,
 *   1 partial, 2 full). Steam's own "Full/Partial Controller Support" library filters also accept
 *   store categories 28 (full) and 18 (partial); we use exactly the same rules.
 * - collectionStore: GetCollection("type-games" | "hidden"), GetUserCollectionsByName,
 *   NewUnsavedCollection(name, undefined, overviews) + Save(), AddApps/RemoveApps, BIsHidden,
 *   SetAppsAsHidden(appids, hide).
 */
import type { Settings } from "./backend";

const w = window as any;

export interface Game {
  appid: number;
  name: string;
  installed: boolean;
  deck: number;          // 0..3
  steamOS: number;       // 0..2
  native: boolean;
  controller: 0 | 1 | 2; // none/unknown, partial, full
  ov: any;
}

export const DECK_LABEL = ["Unknown", "Unsupported", "Playable", "Verified"];
export const PDB_RANK: Record<string, number> = { borked: 0, bronze: 1, silver: 2, gold: 3, platinum: 4 };

function cs(): any {
  return w.collectionStore;
}

export function storesReady(): boolean {
  const c = cs()?.GetCollection?.("type-games");
  return !!(c && c.allApps && c.allApps.length > 0);
}

function hasCategory(ov: any, n: number): boolean {
  try {
    if (typeof ov.BHasStoreCategory === "function") return !!ov.BHasStoreCategory(n);
    if (ov.m_setStoreCategories?.has) return ov.m_setStoreCategories.has(n);
    return Array.isArray(ov.store_category) && ov.store_category.includes(n);
  } catch {
    return false;
  }
}

function controllerLevel(ov: any): 0 | 1 | 2 {
  const lvl = ov.xbox_controller_support ?? ov.controller_support ?? -1;
  if (lvl === 2 || hasCategory(ov, 28)) return 2;
  if (lvl === 1 || hasCategory(ov, 18)) return 1;
  return 0;
}

function isInstalled(ov: any): boolean {
  if (typeof ov.installed === "boolean") return ov.installed;
  return !!ov.local_per_client_data?.installed || ov.size_on_disk !== undefined;
}

function toGame(ov: any): Game {
  return {
    appid: ov.appid,
    name: ov.display_name ?? String(ov.appid),
    installed: isInstalled(ov),
    deck: Number(ov.steam_deck_compat_category) || 0,
    steamOS: Number(ov.steam_os_compat_category) || 0,
    native: !!ov.has_native_linux_binaries,
    controller: controllerLevel(ov),
    ov,
  };
}

function isShortcutOrMod(ov: any): boolean {
  try {
    if (typeof ov.BIsModOrShortcut === "function") return !!ov.BIsModOrShortcut();
  } catch { /* fall through */ }
  return ov.app_type === 1073741824 || !!ov.third_party_mod;
}

/** Every owned Steam game (not software, tools or non-Steam shortcuts), hidden ones included. */
export function allGames(): Game[] {
  const store = cs();
  let list: any[] = store?.GetCollection?.("type-games")?.allApps ?? [];
  if (!list.length) list = (store?.allAppsCollection?.allApps ?? []).filter((o: any) => o?.app_type === 1);
  return list.filter((o) => o && !isShortcutOrMod(o)).map(toGame);
}

export function controllerOk(g: Game, s: Settings): boolean {
  return s.controller === "full" ? g.controller === 2 : g.controller >= 1;
}

/** Passes on Steam's own data alone (no ProtonDB)? */
function compatBySteam(g: Game, s: Settings): boolean {
  if (s.deckMin === "verified" && g.deck >= 3) return true;
  if (s.deckMin === "playable" && g.deck >= 2) return true;
  if (s.steamOS && g.steamOS >= 2) return true;
  if (s.native && g.native) return true;
  return false;
}

/** Why a game qualifies, for the list badge; null when it doesn't. */
export function reason(g: Game, s: Settings, tiers: Record<string, string>): string | null {
  if (!controllerOk(g, s)) return null;
  if (s.excludeUnsupported && g.deck === 1) return null;
  if (s.deckMin !== "off" && g.deck >= (s.deckMin === "verified" ? 3 : 2)) return `Deck ${DECK_LABEL[g.deck]}`;
  if (s.steamOS && g.steamOS >= 2) return "SteamOS Compatible";
  if (s.native && g.native) return "Native Linux";
  if (s.protonDB !== "off") {
    const t = tiers[String(g.appid)];
    if (t && (PDB_RANK[t] ?? -1) >= PDB_RANK[s.protonDB]) return `ProtonDB ${t[0].toUpperCase()}${t.slice(1)}`;
  }
  return null;
}

/** Games that need a ProtonDB lookup: controller OK, not already in on Steam's data, not excluded. */
export function protonDBCandidates(games: Game[], s: Settings): number[] {
  if (s.protonDB === "off") return [];
  return games
    .filter((g) => controllerOk(g, s) && !(s.excludeUnsupported && g.deck === 1) && !compatBySteam(g, s))
    .map((g) => g.appid);
}

export function isHidden(appid: number): boolean {
  try { return !!cs()?.BIsHidden?.(appid); } catch { return false; }
}

export function hiddenGames(): Game[] {
  const list: any[] = cs()?.GetCollection?.("hidden")?.allApps ?? [];
  return list.filter(Boolean).map(toGame).sort((a, b) => a.name.localeCompare(b.name));
}

export function unhide(appids: number[]): void {
  cs().SetAppsAsHidden(appids, false);
}

export function launch(g: Game): void {
  let gameid: string;
  try { gameid = g.ov.GetGameID?.() ?? g.ov.gameid ?? String(g.appid); } catch { gameid = String(g.appid); }
  // Same call Steam's own Play button makes; for an uninstalled game Steam opens its install dialog.
  w.SteamClient.Apps.RunGame(gameid, "", -1, 100);
}

function appIdsOf(col: any): number[] {
  const apps = col?.apps;
  if (!apps) return [];
  return Array.from(apps.keys ? apps.keys() : apps) as number[];
}

export interface SyncResult { ok: boolean; count: number; added: number; removed: number; collectionId?: string; error?: string }

/**
 * Makes the plugin's (static) collection hold exactly `matches`. Creates it on first run and remembers
 * its id, so a renamed collection is followed and a user's own collection with the same name is never
 * touched. Only saves when something changed.
 */
export async function syncCollection(s: Settings, matches: Game[]): Promise<SyncResult> {
  const store = cs();
  if (!store?.NewUnsavedCollection) return { ok: false, count: 0, added: 0, removed: 0, error: "Steam's collection store isn't available." };
  const name = s.collectionName.trim();
  let col = s.collectionId ? store.GetCollection(s.collectionId) : null;
  if (col && (!col.bIsEditable || col.bIsDynamic)) col = null;

  if (!col) {
    const clash = store.GetUserCollectionsByName(name)?.[0];
    if (clash) {
      return { ok: false, count: 0, added: 0, removed: 0, error: `A collection named "${name}" already exists and wasn't made by this plugin. Pick another name.` };
    }
    col = store.NewUnsavedCollection(name, undefined, matches.map((g) => g.ov));
    await col.Save();
    return { ok: true, count: matches.length, added: matches.length, removed: 0, collectionId: col.id };
  }

  let dirty = false;
  if (col.displayName !== name) {
    const clash = (store.GetUserCollectionsByName(name) ?? []).find((c: any) => c.id !== col.id);
    if (clash) return { ok: false, count: 0, added: 0, removed: 0, error: `Another collection is already named "${name}".` };
    col.displayName = name;
    dirty = true;
  }
  const want = new Set(matches.map((g) => g.appid));
  const have = new Set(appIdsOf(col));
  const add = matches.filter((g) => !have.has(g.appid)).map((g) => g.ov);
  const remove = [...have].filter((id) => !want.has(id))
    .map((id) => w.appStore?.GetAppOverviewByAppID?.(id) ?? { appid: id });
  if (add.length) { col.AddApps(add); dirty = true; }
  if (remove.length) { col.RemoveApps(remove); dirty = true; }
  if (dirty) await col.Save();
  return { ok: true, count: want.size, added: add.length, removed: remove.length, collectionId: col.id };
}

export async function deleteCollection(id: string): Promise<boolean> {
  const col = id ? cs()?.GetCollection?.(id) : null;
  if (!col?.bIsDeletable) return false;
  await col.Delete();
  return true;
}
