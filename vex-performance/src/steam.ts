// Steam client integration. All of these are Steam's own internal APIs, the
// same ones the Quick Access "Performance" panel and game Properties use:
//   - SystemPerfStore + SteamClient.System.Perf.UpdateSettings: per-game
//     scaling filter (FSR), FSR sharpness, frame limit, refresh rate, TDP.
//     gamescope receives these from Steam, so no launch options are needed.
//   - SteamClient.Apps.SetAppResolutionOverride: the "Game resolution" the
//     game is told it runs at (the render resolution FSR upscales from).
//   - SteamClient.Apps.SetAppLaunchOptions: only for the optional lsfg-vk
//     gamescope-WSI workaround, added/removed automatically.
// Every call is defensive: a failure skips that feature, never the game.
import { findModuleExport, Router } from "@decky/ui";
import { ManagedLaunch, Profile, SteamLimits } from "./types";
import { matchRefresh } from "./presets";

declare const SteamClient: any;

const FILTER_LINEAR = 1; // ESplitScalingFilter
const FILTER_SHARP = 3;  // "Sharp" = gamescope FSR 1 (EASU + RCAS)

let cachedPerf: any = null;
export function perfStore(): any {
  const w = window as any;
  if (w.SystemPerfStore) return w.SystemPerfStore;
  if (cachedPerf) return cachedPerf;
  try {
    cachedPerf = findModuleExport((e: any) => e?.prototype?.SetSplitScalingScaler && e?.Get)?.Get() ?? null;
  } catch {
    cachedPerf = null;
  }
  return cachedPerf;
}

export function steamPerfAvailable(): boolean {
  const s = perfStore();
  return !!(s?.CreateSettingsUpdateRequest && SteamClient?.System?.Perf?.UpdateSettings);
}

export function getLimits(): SteamLimits {
  const l = perfStore()?.msgState?.limits ?? {};
  return {
    fsrMin: l.fsr_sharpness_min ?? 0,
    fsrMax: l.fsr_sharpness_max ?? 5,
    refreshMin: l.display_refresh_manual_hz_min ?? 40,
    refreshMax: l.display_refresh_manual_hz_max ?? 120,
    refreshAvailable: !!l.is_manual_display_refresh_rate_available,
    fpsOptions: l.fps_limit_options ?? [],
    tdpMin: l.tdp_limit_min ?? 0,
    tdpMax: l.tdp_limit_max ?? 0,
    filters: l.split_scaling_filters_available ?? [],
  };
}

export interface RunningApp {
  appid: string;
  name: string;
}

export function runningApp(): RunningApp | null {
  const app: any = Router.MainRunningApp;
  if (!app?.appid) return null;
  return { appid: String(app.appid), name: app.display_name ?? `App ${app.appid}` };
}

/** Steam's 64-bit game id for the running game (equals appid for Steam games). */
async function waitForGameId(timeoutMs = 10000): Promise<string | null> {
  const store = perfStore();
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    const id = store?.msgState?.current_game_id;
    if (id && String(id) !== "0" && String(id) !== "769") return String(id);
    await new Promise((r) => setTimeout(r, 250));
  }
  return null;
}

function call(obj: any, method: string, value: unknown): boolean {
  if (typeof obj?.[method] === "function") {
    obj[method](value);
    return true;
  }
  return false;
}

export interface SteamApplyOpts {
  steamTdp: boolean; // Steam owns TDP (HHD reads Steam's slider via its FUSE hook)
}

/** Writes the profile into Steam's per-game performance profile and makes it active. */
export async function applySteamPerf(p: Profile, opts: SteamApplyOpts): Promise<string[]> {
  const done: string[] = [];
  if (!steamPerfAvailable()) return ["Steam performance API not found"];
  const gameId = await waitForGameId();
  if (!gameId) return ["game id not ready"];
  const store = perfStore();
  const limits = getLimits();

  const req = store.CreateSettingsUpdateRequest(gameId);
  const a = req.settings_delta().per_app(true);
  a.set_is_game_perf_profile_enabled(true);

  if (p.scaling.enabled) {
    const filter = p.scaling.fsr ? FILTER_SHARP : FILTER_LINEAR;
    if (!call(a, "set_split_scaling_filter", filter)) call(a, "set_scaling_filter", p.scaling.fsr ? 2 : 0);
    if (p.scaling.fsr) {
      const s = Math.max(limits.fsrMin, Math.min(limits.fsrMax, p.scaling.sharpness));
      call(a, "set_fsr_sharpness", s);
    }
    done.push(p.scaling.fsr ? "FSR" : "linear scaling");
  }

  if (p.frame.enabled) {
    const fps = p.frame.fps;
    call(a, "set_is_fps_limit_enabled", fps > 0);
    if (fps > 0) call(a, "set_fps_limit", fps);
    if (limits.refreshAvailable) {
      const hz = p.frame.refresh > 0 ? p.frame.refresh : matchRefresh(fps, limits.refreshMin, limits.refreshMax);
      call(a, "set_display_refresh_manual_hz", Math.max(limits.refreshMin, Math.min(limits.refreshMax, hz)));
      done.push(`${fps || "∞"} fps @ ${hz} Hz`);
    } else {
      done.push(`${fps || "∞"} fps`);
    }
  }

  if (opts.steamTdp && limits.tdpMax > 0) {
    call(a, "set_is_tdp_limit_enabled", p.power.tdpEnabled);
    if (p.power.tdpEnabled) {
      call(a, "set_tdp_limit", Math.max(limits.tdpMin, Math.min(limits.tdpMax, p.power.tdp)));
      done.push(`${p.power.tdp} W`);
    }
  }

  SteamClient.System.Perf.UpdateSettings(req.serializeBase64String());
  return done;
}

/** Render resolution Steam tells the game it runs at. Takes effect on next launch. */
export function setResolution(appid: string, res: string): boolean {
  if (!res) return false;
  try {
    SteamClient.Apps.SetAppResolutionOverride(Number(appid), res);
    return true;
  } catch (e) {
    console.warn("[Vex] SetAppResolutionOverride failed", e);
    return false;
  }
}

// ---------------- launch options (lsfg-vk workaround only) ----------------
const MARK = "VEXPERF=1";

export function readLaunchOptions(appid: string): Promise<string> {
  return new Promise((resolve, reject) => {
    let reg: any;
    let done = false;
    const t = setTimeout(() => finish(undefined, new Error("timeout reading launch options")), 5000);
    const finish = (v?: string, err?: Error) => {
      if (done) return;
      done = true;
      clearTimeout(t);
      setTimeout(() => { try { reg?.unregister(); } catch {} }, 0);
      err ? reject(err) : resolve(v ?? "");
    };
    try {
      reg = SteamClient.Apps.RegisterForAppDetails(Number(appid), (d: any) => finish(d?.strLaunchOptions ?? ""));
    } catch (e) {
      finish(undefined, e as Error);
    }
  });
}

/** Removes the block we added, leaving the user's own options exactly as they were. */
export function stripManaged(opts: string, rec?: ManagedLaunch): string {
  let s = opts.trim();
  if (!s.startsWith(MARK)) return opts;
  s = s.slice(MARK.length).trimStart();
  const envs = rec?.envs ?? [];
  for (const e of envs) if (s.startsWith(e + " ") || s === e) s = s.slice(e.length).trimStart();
  if (rec?.addedCommand && s.startsWith("%command%")) s = s.slice("%command%".length).trimStart();
  return s;
}

export async function setManagedLaunch(
  appid: string,
  envs: string[],
  previous?: ManagedLaunch,
): Promise<ManagedLaunch | null> {
  const current = await readLaunchOptions(appid);
  const user = stripManaged(current, previous);
  let next = user;
  let rec: ManagedLaunch | null = null;
  if (envs.length) {
    const hasCmd = user.includes("%command%");
    next = [MARK, ...envs, hasCmd ? "" : "%command%", user].filter(Boolean).join(" ");
    rec = { envs, addedCommand: !hasCmd };
  }
  if (next !== current) SteamClient.Apps.SetAppLaunchOptions(Number(appid), next);
  return rec;
}
