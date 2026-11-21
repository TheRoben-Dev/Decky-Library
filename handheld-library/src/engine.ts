import { getSettings, protonDBTiers, setSettings, Settings } from "./backend";
import { allGames, Game, protonDBCandidates, reason, storesReady, syncCollection, SyncResult } from "./steam";

export interface Match { g: Game; why: string }
export interface State {
  settings: Settings | null;
  tiers: Record<string, string>;
  matches: Match[];
  last: (SyncResult & { at: number }) | null;
  syncing: boolean;
}

const SYNC_EVERY_MS = 10 * 60 * 1000;
const state: State = { settings: null, tiers: {}, matches: [], last: null, syncing: false };
const listeners = new Set<() => void>();
let timer: number | undefined;
let running: Promise<void> | null = null;
let stopped = false;

function emit() { listeners.forEach((f) => f()); }
export function subscribe(f: () => void): () => void { listeners.add(f); return () => listeners.delete(f); }
export function snapshot(): State { return { ...state }; }

export async function loadSettings(): Promise<Settings> {
  if (!state.settings) { state.settings = await getSettings(); emit(); }
  return state.settings;
}

let saving: Promise<unknown> = Promise.resolve();

/**
 * Applies a settings change right away (so quick toggles build on each other instead of
 * overwriting one another) and saves in order. The backend's normalized copy wins once saved.
 */
export async function updateSettings(patch: Partial<Settings>, resync = true): Promise<void> {
  const cur = await loadSettings();
  state.settings = { ...cur, ...patch };
  emit();
  const want = state.settings;
  saving = saving.then(async () => {
    try {
      const saved = await setSettings(want);
      if (state.settings === want) { state.settings = saved; emit(); }
    } catch (e) {
      console.error("[Handheld Library] saving settings failed", e);
    }
  });
  await saving;
  if (resync) await sync();
}

function compute(games: Game[], s: Settings): Match[] {
  const out: Match[] = [];
  for (const g of games) {
    const why = reason(g, s, state.tiers);
    if (why) out.push({ g, why });
  }
  return out.sort((a, b) => a.g.name.localeCompare(b.g.name));
}

async function doSync(): Promise<void> {
  const s = await loadSettings();
  if (!storesReady()) return;
  const games = allGames();
  const want = protonDBCandidates(games, s);
  if (want.length) {
    try {
      state.tiers = { ...state.tiers, ...(await protonDBTiers(want)) };
    } catch (e) {
      console.warn("[Handheld Library] ProtonDB lookup failed", e);
    }
  }
  state.matches = compute(games, s);
  if (!s.enabled) { emit(); return; }
  let r: SyncResult;
  try {
    r = await syncCollection(s, state.matches.map((m) => m.g));
  } catch (e) {
    r = { ok: false, count: 0, added: 0, removed: 0, error: String(e) };
  }
  state.last = { ...r, at: Date.now() };
  if (r.ok && r.collectionId && r.collectionId !== s.collectionId) {
    await updateSettings({ collectionId: r.collectionId }, false);
  }
  emit();
}

/** Runs one sync; concurrent callers share it. */
export function sync(): Promise<void> {
  if (running) return running;
  state.syncing = true; emit();
  running = doSync()
    .catch((e) => console.error("[Handheld Library] sync failed", e))
    .finally(() => { running = null; state.syncing = false; emit(); });
  return running;
}

/** Waits for Steam's library to load (up to ~2 min), syncs, then re-syncs every 10 minutes. */
export function start(): void {
  stopped = false;
  let tries = 0;
  const boot = () => {
    if (stopped) return;
    let ready = false;
    try { ready = storesReady(); } catch { ready = false; }
    if (!ready && tries++ < 60) { timer = window.setTimeout(boot, 2000); return; }
    sync();
    timer = window.setInterval(() => sync(), SYNC_EVERY_MS) as unknown as number;
  };
  // First check on the next tick, so nothing Steam does during plugin import can break loading.
  timer = window.setTimeout(boot, 0);
}

export function stop(): void {
  stopped = true;
  if (timer !== undefined) { clearTimeout(timer); clearInterval(timer); }
  listeners.clear();
}
