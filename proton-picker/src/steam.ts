// Steam client integration (Steam's own internal APIs, typed in @decky/ui):
//   SteamClient.Apps.SpecifyCompatTool(appId, toolName)  - same call as
//     Properties > Compatibility > "Force the use of a specific tool". ""
//     clears the override (back to Steam's default).
//   SteamClient.Apps.RegisterForAppDetails -> strCompatToolName,
//     nCompatToolPriority, vecPlatforms (what the game uses now).
//   SteamClient.Settings.GetGlobalCompatTools - tools Steam has loaded. Steam
//     only scans compatibilitytools.d at startup, so a fresh install shows up
//     here after a Steam restart.
//   SteamClient.GameSessions.RegisterForAppLifetimeNotifications - game
//     start/exit, used for crash-on-launch rollback.
import { Router } from "@decky/ui";
import { GameInfo, SteamTool } from "./types";

declare const SteamClient: any;

/** Priority Steam stores for a tool the user picked in Properties (config.vdf CompatToolMapping). */
export const USER_PRIORITY = 250;

export function runningAppId(): string | null {
  const app: any = Router.MainRunningApp;
  return app?.appid ? String(app.appid) : null;
}

export async function globalTools(): Promise<SteamTool[]> {
  try {
    const list = await SteamClient.Settings.GetGlobalCompatTools();
    return (list ?? []).map((t: any) => ({ name: t.strToolName, display: t.strDisplayName || t.strToolName }));
  } catch (e) {
    console.warn("[ProtonPicker] GetGlobalCompatTools failed", e);
    return [];
  }
}

export async function toolsForApp(appid: string): Promise<SteamTool[]> {
  try {
    const list = await SteamClient.Apps.GetAvailableCompatTools(Number(appid));
    return (list ?? []).map((t: any) => ({ name: t.strToolName, display: t.strDisplayName || t.strToolName }));
  } catch {
    return globalTools();
  }
}

export function specifyTool(appid: string, tool: string): boolean {
  try {
    SteamClient.Apps.SpecifyCompatTool(Number(appid), tool);
    return true;
  } catch (e) {
    console.error("[ProtonPicker] SpecifyCompatTool failed", e);
    return false;
  }
}

export function appDetails(appid: string, timeoutMs = 4000): Promise<any | null> {
  return new Promise((resolve) => {
    let reg: any;
    let done = false;
    const finish = (v: any) => {
      if (done) return;
      done = true;
      clearTimeout(t);
      setTimeout(() => { try { reg?.unregister(); } catch {} }, 0);
      resolve(v);
    };
    const t = setTimeout(() => finish(null), timeoutMs);
    try {
      reg = SteamClient.Apps.RegisterForAppDetails(Number(appid), (d: any) => finish(d));
    } catch {
      finish(null);
    }
  });
}

function overview(appid: string): any {
  try {
    return (window as any).appStore?.GetAppOverviewByAppID(Number(appid)) ?? null;
  } catch {
    return null;
  }
}

/** Installed Steam games (no non-Steam shortcuts, no tools/soundtracks). */
export function installedGames(): { appid: string; name: string; lastPlayed: number; deckCategory: number }[] {
  const cs = (window as any).collectionStore;
  let apps: any[] = [];
  try {
    apps = cs?.localGamesCollection?.allApps ?? cs?.allGamesCollection?.allApps?.filter((a: any) => a.installed) ?? [];
  } catch {
    apps = [];
  }
  return apps
    .filter((a: any) => a && a.app_type === 1 && !(a.BIsShortcut?.() ?? false) && a.appid < 0x80000000)
    .map((a: any) => ({
      appid: String(a.appid),
      name: a.display_name ?? `App ${a.appid}`,
      lastPlayed: a.rt_last_time_played ?? 0,
      deckCategory: a.steam_deck_compat_category ?? 0,
    }))
    .sort((x: any, y: any) => y.lastPlayed - x.lastPlayed);
}

export async function gameInfo(appid: string): Promise<GameInfo | null> {
  const d = await appDetails(appid);
  if (!d) return null;
  const ov = overview(appid);
  const platforms: string[] = d.vecPlatforms ?? [];
  return {
    appid,
    name: d.strDisplayName || ov?.display_name || `App ${appid}`,
    lastPlayed: ov?.rt_last_time_played ?? d.rtLastTimePlayed ?? 0,
    deckCategory: ov?.steam_deck_compat_category ?? 0,
    native: platforms.includes("linux"),
    currentTool: d.strCompatToolName ?? "",
    currentPriority: d.nCompatToolPriority ?? 0,
  };
}

export function onLifetime(cb: (appid: string, running: boolean) => void): () => void {
  try {
    const reg = SteamClient.GameSessions.RegisterForAppLifetimeNotifications((n: any) =>
      cb(String(n.unAppID), !!n.bRunning),
    );
    return () => { try { reg?.unregister(); } catch {} };
  } catch {
    return () => {};
  }
}

export function restartSteam() {
  SteamClient.User.StartRestart(false);
}
