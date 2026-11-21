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
export async function ensureShortcut(rec: Installed, settings: Settings | null, art = true): Promise<number> {
  let appid = shortcutExists(rec.appid) ? rec.appid : 0;
  const fresh = !appid;
  if (!appid) {
    appid = Number(await SteamClient.Apps.AddShortcut(rec.title, rec.exe, rec.workdir || dirname(rec.exe), rec.args ?? ""));
    if (!appid) throw new Error("Steam didn't create the shortcut");
    // The overview shows up a moment after AddShortcut resolves.
    for (let i = 0; i < 30 && !overview(appid); i++) await sleep(100);
  }
  SteamClient.Apps.SetShortcutName(appid, rec.title);
  SteamClient.Apps.SetShortcutExe(appid, quote(rec.exe));
  SteamClient.Apps.SetShortcutStartDir(appid, quote(rec.workdir || dirname(rec.exe)));
  SteamClient.Apps.SetAppLaunchOptions(appid, rec.args ?? "");
  try {
    if (rec.kind === "windows") SteamClient.Apps.SpecifyCompatTool(appid, settings?.tool || await defaultTool());
    else SteamClient.Apps.SpecifyCompatTool(appid, "");
  } catch (e) { console.warn("[GOG Library] compat tool", e); }
  if (appid !== rec.appid) await setShortcut(rec.game_id, appid);
  if (art && fresh) await applyArt(rec.game_id, appid, rec.title, settings?.art).catch((e) => console.warn("[GOG Library] art", e));
  return appid;
}

export async function removeShortcut(appid: number) {
  if (shortcutExists(appid)) {
    try { SteamClient.Apps.RemoveShortcut(appid); } catch (e) { console.warn("[GOG Library] remove shortcut", e); }
  }
}

type Art = Awaited<ReturnType<typeof composeArt>>;

/** Steam artwork: GOG's own vertical cover, hero, logo and icon by default; anything GOG doesn't
 * have (or everything, with the Nightgrid style) is drawn from the game's cover in the Nightgrid look. */
export async function applyArt(gameId: number, appid: number, title?: string, style: string = "gog") {
  const name = title ?? overview(appid)?.display_name ?? "";
  let drawn: Promise<Art> | null = null;
  const draw = () => drawn ??= (async () => {
    let c = await getArt(gameId, "cover");
    if (!c.ok) c = await getArt(gameId, "capsule");
    if (!c.ok) throw new Error(c.error);
    return composeArt(c.data, c.ext, name);
  })();
  const official = style !== "nightgrid";
  for (const [kind, asset] of [["capsule", 0], ["wide", 3], ["hero", 1], ["logo", 2]] as [keyof Art, number][]) {
    let data = "", ext = "png";
    if (official) {
      const r = await getArt(gameId, kind);
      if (r.ok && (r.ext === "png" || r.ext === "jpeg")) { data = r.data; ext = r.ext === "jpeg" ? "jpg" : "png"; }
    }
    if (!data) {
      try { data = (await draw())[kind]; ext = "png"; } catch (e) { console.warn("[GOG Library] art", kind, e); continue; }
    }
    try { await SteamClient.Apps.ClearCustomArtworkForApp(appid, asset); } catch { /* nothing to clear */ }
    await SteamClient.Apps.SetCustomArtworkForApp(appid, data, ext, asset);
  }
  let icon = "";
  if (official) {
    const r = await getArt(gameId, "icon");
    if (r.ok && r.ext === "png") icon = r.data;
  }
  if (!icon) { try { icon = (await draw()).icon; } catch { /* no icon */ } }
  if (icon) {
    const saved = await saveIcon(gameId, icon);
    if (saved.ok) SteamClient.Apps.SetShortcutIcon(appid, saved.path);
  }
}

export function openInSteam(appid: number) {
  Navigation.CloseSideMenus();
  Navigation.Navigate(`/library/app/${appid}`);
}

export function toast(body: string, title = "GOG Library") {
  toaster.toast({ title, body });
}
