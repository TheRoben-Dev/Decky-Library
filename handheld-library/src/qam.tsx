/*
 * Quick Access (QAM) tab handling.
 *
 * Steam builds the QAM tab list in a memoized array of {key, tab (icon), title, panel} (keys are
 * Steam's EQuickAccessTab: 0 Notifications, 1 Remote Play Together, 2 Voice chat, 3 Friends,
 * 4 Settings, 5 Performance, 6 Help, 7 Soundtrack, 8 VR batteries). Decky Loader patches the QAM
 * renderer and calls `window.__TABS_HOOK_INSTANCE.render(tabs, visible)` on every QAM render to push
 * its own tabs (Decky = 999) into that array; tabs added with `.add({id,title,icon,content})` are
 * rendered by Decky inside its ErrorBoundary.
 *
 * We don't patch Steam ourselves. We:
 *  - add our "Hidden games" tab through Decky's own tabs hook, and
 *  - wrap that hook's render() to filter the array after Decky has filled it.
 * Before each render we put back what we filtered last time, so Decky always sees its full list
 * (it counts its tabs to decide whether to push them again). Anything unexpected → we stop
 * filtering and Steam/Decky render exactly as they would without this plugin.
 */
import { ReactNode } from "react";

const DECKY_KEY = "999";
export const HIDDEN_TAB_ID = 48151;

export const STEAM_TABS: Record<string, string> = {
  "0": "Notifications",
  "1": "Remote Play Together",
  "2": "Voice chat",
  "3": "Friends",
  "4": "Settings",
  "5": "Performance",
  "6": "Help",
  "7": "Soundtrack / Music",
  "8": "VR batteries",
  [DECKY_KEY]: "Decky",
  [String(HIDDEN_TAB_ID)]: "Hidden games (this plugin)",
};

export interface SeenTab { key: string; label: string; locked: boolean }

let hook: any = null;
let origRender: ((tabs: any[], visible: boolean) => void) | null = null;
let wrapper: ((tabs: any[], visible: boolean) => void) | null = null;
let hidden = new Set<string>();
let broken = false;
const full = new Map<any[], any[]>();   // QAM array → its complete list before our filter
const seen = new Map<string, SeenTab>();
const seenListeners = new Set<() => void>();

function keyOf(t: any): string {
  return String(t?.key ?? "");
}

function labelOf(t: any, key: string): string {
  if (STEAM_TABS[key]) return STEAM_TABS[key];
  if (typeof t?.title === "string" && t.title.trim()) return t.title.trim();
  const p = t?.title?.props;
  if (typeof p?.children === "string") return p.children;
  return `Plugin tab ${key}`;
}

function record(list: any[]) {
  let changed = false;
  for (const t of list) {
    const key = keyOf(t);
    if (!key || seen.has(key)) continue;
    seen.set(key, { key, label: labelOf(t, key), locked: key === DECKY_KEY });
    changed = true;
  }
  if (changed) seenListeners.forEach((f) => f());
}

/** Decky pushes all its tabs again when its count doesn't match; keep only the newest of each key. */
function dedupeDecky(list: any[]): any[] {
  const last = new Map<string, any>();
  for (const t of list) if (t?.decky) last.set(keyOf(t), t);
  return list.filter((t) => !t?.decky || last.get(keyOf(t)) === t);
}

function render(this: any, tabs: any[], visible: boolean) {
  const prev = Array.isArray(tabs) ? full.get(tabs) : undefined;
  if (prev && !broken) tabs.splice(0, tabs.length, ...prev);
  origRender!.call(this, tabs, visible);
  if (broken || !Array.isArray(tabs)) return;
  try {
    const all = dedupeDecky(tabs);
    full.set(tabs, all);
    record(all);
    const shown = all.filter((t) => keyOf(t) === DECKY_KEY || !hidden.has(keyOf(t)));
    // Never leave the QAM empty.
    tabs.splice(0, tabs.length, ...(shown.length ? shown : all));
  } catch (e) {
    console.error("[Handheld Library] QAM filter failed, leaving Quick Access as is", e);
    broken = true;
    restoreArrays();
  }
}

function restoreArrays() {
  full.forEach((all, arr) => { try { arr.splice(0, arr.length, ...all); } catch { /* ignore */ } });
}

/** Installs the render wrapper and our tab. Returns false (and changes nothing) if Decky's hook isn't there. */
export function installQam(tab: { title: ReactNode; icon: ReactNode; content: ReactNode } | null): boolean {
  const h = (window as any).__TABS_HOOK_INSTANCE;
  if (!h || typeof h.render !== "function" || typeof h.add !== "function" || !Array.isArray(h.tabs)) {
    console.warn("[Handheld Library] Decky's QAM tabs hook not found; QAM features are off");
    return false;
  }
  hook = h;
  broken = false;
  origRender = h.render;
  wrapper = render;
  h.render = wrapper;
  if (tab && !h.tabs.some((t: any) => t.id === HIDDEN_TAB_ID)) {
    h.add({ id: HIDDEN_TAB_ID, ...tab });
  }
  return true;
}

export function uninstallQam() {
  if (!hook) return;
  try {
    restoreArrays();
    // Take our tab out of Steam's array as well, or Decky would count a tab it no longer has.
    full.forEach((_all, arr) => {
      const i = arr.findIndex((t: any) => t?.decky && keyOf(t) === String(HIDDEN_TAB_ID));
      if (i >= 0) arr.splice(i, 1);
    });
    hook.removeById?.(HIDDEN_TAB_ID);
    if (hook.render === wrapper) hook.render = origRender;
    else broken = true;   // someone wrapped after us: become a pass-through
  } catch (e) {
    console.error("[Handheld Library] QAM uninstall", e);
  }
  full.clear();
  hook = null;
}

export function setHiddenTabs(keys: string[]) {
  hidden = new Set(keys.filter((k) => k !== DECKY_KEY));
}

export function qamActive(): boolean {
  return !!hook && !broken;
}

export function seenTabs(): SeenTab[] {
  const out = new Map(seen);
  hidden.forEach((k) => { if (!out.has(k)) out.set(k, { key: k, label: STEAM_TABS[k] ?? `Tab ${k}`, locked: false }); });
  return [...out.values()];
}

export function onSeenTabs(f: () => void): () => void {
  seenListeners.add(f);
  return () => seenListeners.delete(f);
}
