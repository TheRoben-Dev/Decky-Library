/* Things both Quick Access and the pages do; they keep `state` current and notify subscribers. */
import { addEventListener, removeEventListener } from "@decky/api";
import * as be from "./backend";
import { changed, state } from "./state";
import { ensureShortcut, removeShortcut, toast } from "./steam";

export async function loadSettings() {
  const s = await be.getSettings();
  state.settings = s;
  changed();
  if (s.imported) toast(s.imported);
  return s;
}

export async function loadLibrary(refresh = false): Promise<string | null> {
  const r = await be.getLibrary(refresh);
  if (!r.ok) { changed(); return r.error; }
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

export async function startInstall(gameId: number, uploadId = 0) {
  const r = await be.install(gameId, uploadId);
  if (!r.ok) { toast(r.error); return; }
  state.jobs = r.jobs; changed();
}

export async function cancelJob(gameId: number) {
  state.jobs = await be.cancel(gameId); changed();
}

/** Adds/refreshes the Steam shortcut for an installed game; returns its appid or 0. */
export async function addToSteam(rec: be.Installed, art = true): Promise<number> {
  try {
    const appid = await ensureShortcut(rec, state.settings, art);
    state.installed[String(rec.game_id)] = { ...rec, appid };
    changed();
    return appid;
  } catch (e: any) {
    toast(`Couldn't add ${rec.title} to Steam: ${e?.message ?? e}`);
    return 0;
  }
}

export async function removeGame(gameId: number, deletePrefix: boolean) {
  const r = await be.uninstall(gameId, deletePrefix);
  if (!r.ok) { toast(r.error); return false; }
  await removeShortcut(r.appid);
  delete state.installed[String(gameId)];
  changed();
  return true;
}

/* Backend events. Registered once for the plugin's lifetime: they only fire while a download
 * runs or the phone sign-in page is open, so nothing here costs anything when idle. */
export function listen(): () => void {
  const onJobs = (jobs: be.Job[]) => { state.jobs = jobs ?? []; changed(); };
  const onDone = async (d: be.Job & { result: be.Installed | null }) => {
    if (d.phase === "done" && d.result) {
      state.installed[String(d.game_id)] = d.result;
      changed();
      const appid = await addToSteam(d.result, true);
      const what = d.action === "update" ? "updated" : "installed";
      if (d.result.installer) toast(`${d.title} ${what}. It's an installer: run it once from Steam, then pick the game in Itch Library.`);
      else toast(appid ? `${d.title} ${what}. It's in your Steam library.` : `${d.title} ${what}.`);
    } else if (d.phase === "error") {
      toast(`${d.title}: ${d.error}`);
    } else if (d.phase === "cancelled") {
      toast(`${d.title}: download cancelled`);
    }
  };
  const onSignedIn = (s: be.Settings) => {
    state.settings = s; state.games = null; changed();
    toast(`Signed in as ${s.user?.name || s.user?.username || "your itch.io account"}`);
    loadLibrary(true);
  };
  addEventListener<[be.Job[]]>("itch_job", onJobs);
  addEventListener<[be.Job & { result: be.Installed | null }]>("itch_job_done", onDone);
  addEventListener<[be.Settings]>("itch_signed_in", onSignedIn);
  return () => {
    removeEventListener("itch_job", onJobs);
    removeEventListener("itch_job_done", onDone);
    removeEventListener("itch_signed_in", onSignedIn);
  };
}
