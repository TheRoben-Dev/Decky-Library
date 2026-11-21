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
  if (!r.ok) {
    if (r.status === 401) await loadSettings().catch(() => {});
    changed();
    return r.error;
  }
  state.games = r.games;
  state.libraryAt = r.at;
  state.installed = r.installed;
  state.jobs = r.jobs;
  changed();
  if (r.updatesDue && !state.checking) checkUpdates(false);
  return null;
}

export async function loadOffers(refresh = false) {
  const r = await be.getOffers(refresh);
  state.claimsUrl = r.claims || state.claimsUrl;
  if (r.ok) { state.offers = r.items; state.offersError = ""; }
  else { state.offers = state.offers ?? []; state.offersError = r.error; }
  changed();
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

export async function startInstall(gameId: string, repair = false) {
  const r = await be.install(gameId, repair);
  if (!r.ok) { toast(r.error); return; }
  state.jobs = r.jobs; changed();
}

export async function cancelJob(gameId: string) {
  state.jobs = await be.cancel(gameId); changed();
}

/** Adds/refreshes the Steam shortcut for an installed game; returns its appid or 0. */
export async function addToSteam(rec: be.Installed, art = true): Promise<number> {
  try {
    const appid = await ensureShortcut(rec, state.settings, art);
    state.installed[rec.game_id] = { ...rec, appid };
    changed();
    return appid;
  } catch (e: any) {
    toast(`Couldn't add ${rec.title} to Steam: ${e?.message ?? e}`);
    return 0;
  }
}

export async function removeGame(gameId: string, deletePrefix: boolean) {
  const r = await be.uninstall(gameId, deletePrefix);
  if (!r.ok) { toast(r.error); return false; }
  await removeShortcut(r.appid);
  delete state.installed[gameId];
  changed();
  return true;
}

/* Backend events. Registered once for the plugin's lifetime: they only fire while a download
 * runs or the phone sign-in page is open, so nothing here costs anything when idle. */
export function listen(): () => void {
  const onJobs = (jobs: be.Job[]) => { state.jobs = jobs ?? []; changed(); };
  const onDone = async (d: be.Job & { result: be.Installed | null }) => {
    if (d.phase === "done" && d.result) {
      state.installed[d.game_id] = d.result;
      changed();
      const appid = await addToSteam(d.result, d.action === "install" || !d.result.appid);
      const what = d.action === "update" ? "updated" : d.action === "repair" ? "repaired" : "installed";
      toast(appid ? `${d.title} ${what}. It's in your Steam library.` : `${d.title} ${what}.`);
    } else if (d.phase === "error") {
      toast(`${d.title}: ${d.error}`);
    } else if (d.phase === "cancelled") {
      toast(`${d.title}: download cancelled`);
    }
  };
  const onSignedIn = (s: be.Settings) => {
    state.settings = s; state.games = null; state.offers = null; changed();
    toast(`Signed in as ${s.user?.name || "your Amazon account"}`);
    loadLibrary(true);
  };
  const onSignedOut = (s: be.Settings) => { state.settings = s; state.games = null; changed(); };
  addEventListener<[be.Job[]]>("amazon_job", onJobs);
  addEventListener<[be.Job & { result: be.Installed | null }]>("amazon_job_done", onDone);
  addEventListener<[be.Settings]>("amazon_signed_in", onSignedIn);
  addEventListener<[be.Settings]>("amazon_signed_out", onSignedOut);
  return () => {
    removeEventListener("amazon_job", onJobs);
    removeEventListener("amazon_job_done", onDone);
    removeEventListener("amazon_signed_in", onSignedIn);
    removeEventListener("amazon_signed_out", onSignedOut);
  };
}
