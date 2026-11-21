/*
 * Steam client glue: non-Steam shortcuts, Proton, artwork. Everything runs on demand (after an
 * install, or a button); nothing subscribes to Steam events or polls.
 *
 *   SteamClient.Apps.AddShortcut / SetShortcutName / SetShortcutExe / SetShortcutStartDir /
 *     SetAppLaunchOptions / RemoveShortcut  - what "Add a Non-Steam Game" does.
 *   SteamClient.Apps.SpecifyCompatTool(appid, tool)  - Properties > Compatibility.
 *   SteamClient.Apps.SetCustomArtworkForApp / SetShortcutIcon  - Steam owns the files.
 */
import { Navigation } from "@decky/ui";
import { toaster } from "@decky/api";
import { composeArt } from "./art";
import { getArt, Installed, saveIcon, setShortcut, Settings } from "./backend";

declare const SteamClient: any;

const SHORTCUT = 0x40000000;

function overview(appid: number): any {
  try { return (window as any).appStore?.GetAppOverviewByAppID(appid) ?? null; } catch { return null; }
}

export function shortcutExists(appid: number): boolean {
  const o = appid ? overview(appid) : null;
  return !!o && o.app_type === SHORTCUT;
}

const quote = (s: string) => `"${s.replace(/"/g, "")}"`;
const dirname = (p: string) => p.replace(/\/[^/]*$/, "") || "/";
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Steam's loaded Proton builds. */
export async function protonTools(): Promise<{ name: string; display: string }[]> {
  try {
    const list = await SteamClient.Settings.GetGlobalCompatTools();
    return (list ?? [])
      .map((t: any) => ({ name: String(t.strToolName), display: String(t.strDisplayName || t.strToolName) }))
      .filter((t: any) => /proton/i.test(t.name) || /proton/i.test(t.display));
  } catch { return []; }
}

async function defaultTool(): Promise<string> {
  const names = (await protonTools()).map((t) => t.name);
  if (names.includes("proton_experimental")) return "proton_experimental";
  const ver = (n: string) => (n.match(/\d+/g) ?? []).map(Number);
  const sorted = [...names].sort((a, b) => {
    const x = ver(a), y = ver(b);
    for (let i = 0; i < Math.max(x.length, y.length); i++) if ((x[i] ?? 0) !== (y[i] ?? 0)) return (y[i] ?? 0) - (x[i] ?? 0);
    return 0;
  });
  return sorted[0] ?? "proton_experimental";
}

/** Creates (or refreshes) the game's Steam shortcut, set to run with Proton. Returns its appid. */
export async function ensureShortcut(rec: Installed, settings: Settings | null, art = true): Promise<number> {
  let appid = shortcutExists(rec.appid) ? rec.appid : 0;
  const fresh = !appid;
  const start = rec.cwd || dirname(rec.exe);
  if (!appid) {
    appid = Number(await SteamClient.Apps.AddShortcut(rec.title, rec.exe, start, rec.launch ?? ""));
    if (!appid) throw new Error("Steam didn't create the shortcut");
    // The overview shows up a moment after AddShortcut resolves.
    for (let i = 0; i < 30 && !overview(appid); i++) await sleep(100);
  }
  SteamClient.Apps.SetShortcutName(appid, rec.title);
  SteamClient.Apps.SetShortcutExe(appid, quote(rec.exe));
  SteamClient.Apps.SetShortcutStartDir(appid, quote(start));
  SteamClient.Apps.SetAppLaunchOptions(appid, rec.launch ?? "");
  try {
    SteamClient.Apps.SpecifyCompatTool(appid, settings?.tool || await defaultTool());
  } catch (e) { console.warn("[Amazon Library] compat tool", e); }
  if (appid !== rec.appid) await setShortcut(rec.game_id, appid);
  if (art && fresh) await applyArt(rec.game_id, appid, rec.title).catch((e) => console.warn("[Amazon Library] art", e));
  return appid;
}

export async function removeShortcut(appid: number) {
  if (shortcutExists(appid)) {
    try { SteamClient.Apps.RemoveShortcut(appid); } catch (e) { console.warn("[Amazon Library] remove shortcut", e); }
  }
}

/** Capsule, wide, hero, logo and icon from Amazon's artwork, in the Nightgrid look. */
export async function applyArt(gameId: string, appid: number, title?: string) {
  const a = await getArt(gameId);
  if (!a.ok) throw new Error(a.error);
  const art = await composeArt(a.cover, a.background, a.logo, title ?? a.title);
  for (const [asset, png] of [[0, art.capsule], [3, art.wide], [1, art.hero], [2, art.logo]] as [number, string][]) {
    try { await SteamClient.Apps.ClearCustomArtworkForApp(appid, asset); } catch { /* nothing to clear */ }
    await SteamClient.Apps.SetCustomArtworkForApp(appid, png, "png", asset);
  }
  const icon = await saveIcon(gameId, art.icon);
  if (icon.ok) SteamClient.Apps.SetShortcutIcon(appid, icon.path);
}

export function openInSteam(appid: number) {
  Navigation.CloseSideMenus();
  Navigation.Navigate(`/library/app/${appid}`);
}

export function toast(body: string, title = "Amazon Library") {
  toaster.toast({ title, body });
}
