/* Things both Quick Access and the pages do; they keep `state` current and notify subscribers. */
import { addEventListener, removeEventListener } from "@decky/api";
import * as be from "./backend";
import { changed, state } from "./state";
import { ensureShortcut, removeShortcut, toast } from "./steam";

export async function loadSettings() {
  const s = await be.getSettings();
  state.settings = s;
  changed();
  return s;
}

export async function loadLibrary(refresh = false): Promise<string | null> {
  const r = await be.getLibrary(refresh);
  if (!r.ok) { changed(); return r.status === 401 ? "Your Epic sign-in expired. Sign out in Quick Access → Epic Library → Settings and sign in again." : r.error; }
  state.games = r.games;
  state.libraryAt = r.at;
  state.installed = r.installed;
  state.jobs = r.jobs;
  changed();
  if (r.updatesDue && !state.checking) checkUpdates(false);
  return null;
}

export async function refreshInstalled() {
  state.installed = await be.getInstalled();
  changed();
}

export async function checkUpdates(announce = true) {
  if (state.checking) return;
  state.checking = true; changed();
  try {
    const r = await be.checkUpdates();
    if (r.ok) {
      state.installed = r.installed;
      state.lastCheck = Date.now();
      if (announce || r.updates) toast(r.updates ? `${r.updates} update${r.updates > 1 ? "s" : ""} available` : `All ${r.checked} installed games are up to date`);
    } else if (announce) toast(`Couldn't check for updates: ${r.error}`);
  } finally {
    state.checking = false; changed();
  }
}

export async function startInstall(app: string, repair = false) {
  const r = await be.install(app, repair);
  if (!r.ok) { toast(r.error); return; }
  state.jobs = r.jobs; changed();
}

export async function cancelJob(app: string) {
  state.jobs = await be.cancel(app); changed();
}

/** Adds/refreshes the Steam shortcut for an installed game; returns its appid or 0. */
export async function addToSteam(app: string, art = true): Promise<number> {
  const info = await be.shortcutInfo(app);
  if (!info.ok) { toast(info.error); return 0; }
  const rec = info.installed;
  try {
    const game = state.games?.find((g) => g.app === app) ?? null;
    const appid = await ensureShortcut(rec, info.options, game, state.settings, art);
    state.installed[app] = { ...rec, appid };
    changed();
    return appid;
  } catch (e: any) {
    toast(`Couldn't add ${rec.title} to Steam: ${e?.message ?? e}`);
    return 0;
  }
}

export async function removeGame(app: string, deletePrefix: boolean) {
  const r = await be.uninstall(app, deletePrefix);
  if (!r.ok) { toast(r.error); return false; }
  await removeShortcut(r.appid);
  delete state.installed[app];
  changed();
  return true;
}

/* Backend events. Registered once for the plugin's lifetime: they only fire while a download
 * runs or the phone sign-in page is open, so nothing here costs anything when idle. */
export function listen(): () => void {
  const onJobs = (jobs: be.Job[]) => { state.jobs = jobs ?? []; changed(); };
  const onDone = async (d: be.Job & { result: be.Installed | null }) => {
    if (d.phase === "done" && d.result) {
      state.installed[d.app] = d.result;
      changed();
      const appid = await addToSteam(d.app, d.action === "install" || !d.result.appid);
      const what = d.action === "update" ? "updated" : d.action === "repair" ? "repaired" : "installed";
      toast(appid ? `${d.title} ${what}. It's in your Steam library.` : `${d.title} ${what}.`);
    } else if (d.phase === "error") {
      toast(`${d.title}: ${d.error}`);
    } else if (d.phase === "cancelled") {
      toast(`${d.title}: download paused. Install again to resume, or discard it on the game page.`);
    }
  };
  const onSignedIn = (s: be.Settings) => {
    state.settings = s; state.games = null; changed();
    toast(`Signed in as ${s.user?.name || "your Epic account"}`);
    loadLibrary(true);
  };
  addEventListener<[be.Job[]]>("epic_job", onJobs);
  addEventListener<[be.Job & { result: be.Installed | null }]>("epic_job_done", onDone);
  addEventListener<[be.Settings]>("epic_signed_in", onSignedIn);
  return () => {
    removeEventListener("epic_job", onJobs);
    removeEventListener("epic_job_done", onDone);
    removeEventListener("epic_signed_in", onSignedIn);
  };
}
