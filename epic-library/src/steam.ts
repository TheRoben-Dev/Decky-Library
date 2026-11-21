/*
 * Steam client glue: non-Steam shortcuts, Proton, artwork. Everything runs on demand (after an
 * install, or a button); nothing subscribes to Steam events or polls.
 *
 *   SteamClient.Apps.AddShortcut / SetShortcutName / SetShortcutExe / SetShortcutStartDir /
 *     SetAppLaunchOptions / RemoveShortcut  - what "Add a Non-Steam Game" does.
 *   SteamClient.Apps.SpecifyCompatTool(appid, tool)  - Properties > Compatibility.
 *   SteamClient.Apps.SetCustomArtworkForApp / SetShortcutIcon  - Steam owns the files.
 * Launch options are `"<plugin data>/runtime/launch.sh" <app name> %command%`: Steam expands
 * %command% to its Proton command line and the wrapper adds Epic's launch token to it.
 */
import { Navigation } from "@decky/ui";
import { toaster } from "@decky/api";
import { composeArt } from "./art";
import { Game, getImage, Installed, saveIcon, setShortcut, Settings } from "./backend";
import { sized } from "./state";

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

/** Steam's loaded Proton builds, newest-looking first. */
export async function protonTools(): Promise<{ name: string; display: string }[]> {
  try {
    const list = await SteamClient.Settings.GetGlobalCompatTools();
    return (list ?? [])
      .map((t: any) => ({ name: String(t.strToolName), display: String(t.strDisplayName || t.strToolName) }))
      .filter((t: any) => /proton/i.test(t.name) || /proton/i.test(t.display));
  } catch { return []; }
}

async function defaultTool(): Promise<string> {
  const tools = await protonTools();
  const names = tools.map((t) => t.name);
  if (names.includes("proton_experimental")) return "proton_experimental";
  const ver = (n: string) => (n.match(/\d+/g) ?? []).map(Number);
  const sorted = [...names].sort((a, b) => {
    const x = ver(a), y = ver(b);
    for (let i = 0; i < Math.max(x.length, y.length); i++) if ((x[i] ?? 0) !== (y[i] ?? 0)) return (y[i] ?? 0) - (x[i] ?? 0);
    return 0;
  });
  return sorted[0] ?? "proton_experimental";
}

/** Creates (or refreshes) the game's Steam shortcut. Returns its appid. */
export async function ensureShortcut(rec: Installed, options: string, game: Game | null, settings: Settings | null, art = true): Promise<number> {
  if (!rec.exe) throw new Error("Legendary didn't record the game's executable");
  let appid = shortcutExists(rec.appid) ? rec.appid : 0;
  const fresh = !appid;
  if (!appid) {
    appid = Number(await SteamClient.Apps.AddShortcut(rec.title, rec.exe, dirname(rec.exe), options));
    if (!appid) throw new Error("Steam didn't create the shortcut");
    // The overview shows up a moment after AddShortcut resolves.
    for (let i = 0; i < 30 && !overview(appid); i++) await sleep(100);
  }
  SteamClient.Apps.SetShortcutName(appid, rec.title);
  SteamClient.Apps.SetShortcutExe(appid, quote(rec.exe));
  SteamClient.Apps.SetShortcutStartDir(appid, quote(dirname(rec.exe)));
  SteamClient.Apps.SetAppLaunchOptions(appid, options);
  try {
    SteamClient.Apps.SpecifyCompatTool(appid, settings?.tool || await defaultTool());
  } catch (e) { console.warn("[Epic Library] compat tool", e); }
  if (appid !== rec.appid) await setShortcut(rec.app, appid);
  if (art && fresh && game) await applyArt(game, appid).catch((e) => console.warn("[Epic Library] art", e));
  return appid;
}

export async function removeShortcut(appid: number) {
  if (shortcutExists(appid)) {
    try { SteamClient.Apps.RemoveShortcut(appid); } catch (e) { console.warn("[Epic Library] remove shortcut", e); }
  }
}

async function fetchImg(url: string, w: number, h: number) {
  if (!url) return undefined;
  const r = await getImage(sized(url, w, h));
  return r.ok ? { data: r.data, ext: r.ext } : undefined;
}

/** Capsule, wide, hero, logo and icon from the game's Epic images, in the Nightgrid look. */
export async function applyArt(game: Game, appid: number) {
  const [tall, wide, logo] = await Promise.all([
    fetchImg(game.tall, 600, 900), fetchImg(game.wide, 1920, 1080), game.logo ? fetchImg(game.logo, 1280, 400) : Promise.resolve(undefined),
  ]);
  const art = await composeArt({ tall, wide, logo }, game.title);
  for (const [asset, png] of [[0, art.capsule], [3, art.wide], [1, art.hero], [2, art.logo]] as [number, string][]) {
    try { await SteamClient.Apps.ClearCustomArtworkForApp(appid, asset); } catch { /* nothing to clear */ }
    await SteamClient.Apps.SetCustomArtworkForApp(appid, png, "png", asset);
  }
  const icon = await saveIcon(game.app, art.icon);
  if (icon.ok) SteamClient.Apps.SetShortcutIcon(appid, icon.path);
}

export function openInSteam(appid: number) {
  Navigation.CloseSideMenus();
  Navigation.Navigate(`/library/app/${appid}`);
}

export function toast(body: string, title = "Epic Library") {
  toaster.toast({ title, body });
}
