/*
 * Steam client glue. Everything is read on demand (when Quick Access or the browser opens);
 * nothing here subscribes to Steam events or polls.
 *
 * Artwork goes through SteamClient.Apps.SetCustomArtworkForApp / ClearCustomArtworkForApp,
 * the same calls Steam's own "Set custom artwork" uses, so Steam owns the files
 * (userdata/<id>/config/grid) and the change survives without this plugin.
 */
import { Router } from "@decky/ui";

export const SHORTCUT = 0x40000000; // app_type of non-Steam shortcuts

export interface Slot {
  id: "capsule" | "wide" | "hero" | "logo" | "icon";
  title: string;
  kind: "grids" | "heroes" | "logos" | "icons";
  shape: string;           // SteamGridDB dimension preset (grids only)
  asset: number;           // ELibraryAssetType
  ratio: string;           // tile aspect ratio
  min: number;             // tile min width (px)
}

export const SLOTS: Slot[] = [
  { id: "capsule", title: "Capsule", kind: "grids", shape: "capsule", asset: 0, ratio: "2 / 3", min: 118 },
  { id: "wide", title: "Wide", kind: "grids", shape: "wide", asset: 3, ratio: "460 / 215", min: 200 },
  { id: "hero", title: "Hero", kind: "heroes", shape: "", asset: 1, ratio: "96 / 31", min: 270 },
  { id: "logo", title: "Logo", kind: "logos", shape: "", asset: 2, ratio: "16 / 9", min: 180 },
  { id: "icon", title: "Icon", kind: "icons", shape: "", asset: 4, ratio: "1 / 1", min: 92 },
];

export interface App { appid: number; name: string; shortcut: boolean }

function overview(appid: number): any {
  try { return (window as any).appStore?.GetAppOverviewByAppID(appid) ?? null; } catch { return null; }
}

export function appInfo(appid: number): App | null {
  const o = overview(appid);
  if (!o) return null;
  return { appid, name: o.display_name ?? `App ${appid}`, shortcut: o.app_type === SHORTCUT };
}

/** The game whose page is open in the library, if any. */
export function focusedApp(): number | null {
  const w: any = (Router as any).WindowStore?.GamepadUIMainWindowInstance;
  const paths: string[] = [];
  try { paths.push(w?.m_history?.location?.pathname ?? ""); } catch { /* not there on this build */ }
  try { paths.push(w?.BrowserWindow?.location?.pathname ?? ""); } catch { /* idem */ }
  for (const p of paths) {
    const m = /\/library\/app\/(\d+)/.exec(p);
    if (m) return Number(m[1]);
  }
  return null;
}

export function runningApp(): number | null {
  const a: any = Router.MainRunningApp;
  return a?.appid ? Number(a.appid) : null;
}

/** Games and shortcuts in the library, most recently played first. */
export function libraryApps(limit = 60): App[] {
  const cs = (window as any).collectionStore;
  let list: any[] = [];
  try { list = cs?.allAppsCollection?.allApps ?? cs?.allGamesCollection?.allApps ?? []; } catch { list = []; }
  return list
    .filter((a: any) => a && (a.app_type === 1 || a.app_type === SHORTCUT))
    .sort((x: any, y: any) => (y.rt_last_time_played ?? 0) - (x.rt_last_time_played ?? 0))
    .slice(0, limit)
    .map((a: any) => ({ appid: Number(a.appid), name: a.display_name ?? `App ${a.appid}`, shortcut: a.app_type === SHORTCUT }));
}

export async function setArt(appid: number, base64: string, ext: "png" | "jpg", asset: number) {
  // Steam keeps one custom file per slot; clearing first avoids a stale .jpg beside a new .png.
  try { await SteamClient.Apps.ClearCustomArtworkForApp(appid, asset); } catch { /* nothing to clear */ }
  await SteamClient.Apps.SetCustomArtworkForApp(appid, base64, ext, asset);
}

export async function clearArt(appid: number, asset: number) {
  await SteamClient.Apps.ClearCustomArtworkForApp(appid, asset);
}

export function setShortcutIcon(appid: number, path: string) {
  SteamClient.Apps.SetShortcutIcon(appid, path);
}
