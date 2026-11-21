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
import { staticClasses } from "@decky/ui";
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

/**
 * Decky pushes all its tabs again when its count doesn't match; keep only the newest of each key, and
 * drop Decky tabs that were removed from the hook (e.g. a plugin tab the user switched off).
 */
function dedupeDecky(list: any[]): any[] {
  const registered = new Set((hook?.tabs ?? []).map((t: any) => String(t?.id)));
  const last = new Map<string, any>();
  for (const t of list) if (t?.decky) last.set(keyOf(t), t);
  return list.filter((t) => !t?.decky || (last.get(keyOf(t)) === t && registered.has(keyOf(t))));
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
    // Take our tabs out of Steam's array as well, or Decky would count tabs it no longer has.
    const ours = new Set([String(HIDDEN_TAB_ID), ...[...pluginTabIds.values()].map(String)]);
    full.forEach((_all, arr) => {
      for (let i = arr.length - 1; i >= 0; i--) if (arr[i]?.decky && ours.has(keyOf(arr[i]))) arr.splice(i, 1);
    });
    hook.removeById?.(HIDDEN_TAB_ID);
    pluginTabIds.forEach((id) => hook.removeById?.(id));
    pluginTabIds.clear();
    if (pluginTimer !== undefined) clearInterval(pluginTimer);
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
  const active = new Set([...pluginTabIds.values()].map(String));
  const out = new Map([...seen].filter(([k]) => {
    const n = Number(k);
    return !(n >= 49000 && n < 59000) || active.has(k);
  }));
  hidden.forEach((k) => { if (!out.has(k)) out.set(k, { key: k, label: STEAM_TABS[k] ?? `Tab ${k}`, locked: false }); });
  return [...out.values()];
}

export function onSeenTabs(f: () => void): () => void {
  seenListeners.add(f);
  return () => seenListeners.delete(f);
}

/* ---------- Decky plugins as their own QAM tabs ---------- */

const pluginTabIds = new Map<string, number>();   // plugin name → our QAM tab id
let wantedPlugins: string[] = [];
let pluginTimer: number | undefined;

export function deckyPlugins(): any[] {
  try {
    const list: any[] = (window as any).DeckyPluginLoader?.plugins ?? [];
    return list.filter((p) => p && typeof p.name === "string" && p.content);
  } catch { return []; }
}

/** Stable id per plugin name (FNV-1a into 49000..58999), so hidden-tab settings survive restarts. */
export function pluginTabId(name: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < name.length; i++) { h ^= name.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
  return 49000 + (h % 10000);
}

/** Renders the plugin's own panel, looked up on every render so updates/reloads are picked up. */
function HostedPlugin({ name }: { name: string }) {
  const p = deckyPlugins().find((x) => x.name === name);
  if (!p) return <div style={{ padding: "16px", fontSize: "13px", opacity: 0.7 }}>{name} isn't loaded right now.</div>;
  return <div style={{ paddingTop: "8px" }}>{p.content}</div>;
}

function syncPluginTabs() {
  if (!hook || broken) return;
  const loaded = new Map(deckyPlugins().map((p) => [p.name, p]));
  for (const [name, id] of [...pluginTabIds]) {
    if (!wantedPlugins.includes(name) || !loaded.has(name)) { hook.removeById?.(id); pluginTabIds.delete(name); }
  }
  for (const name of wantedPlugins) {
    const p = loaded.get(name);
    if (!p || pluginTabIds.has(name)) continue;
    const id = pluginTabId(name);
    try {
      hook.add({
        id,
        title: p.titleView ?? <div className={staticClasses.Title}>{name}</div>,
        icon: p.icon ?? <span>{name.slice(0, 2)}</span>,
        content: <HostedPlugin name={name} />,
      });
      pluginTabIds.set(name, id);
      STEAM_TABS[String(id)] = `${name} (plugin tab)`;
    } catch (e) {
      console.error(`[Handheld Library] couldn't add a QAM tab for ${name}`, e);
    }
  }
}


/** Gives each named plugin its own QAM tab (it stays in Decky's list too). Re-checks every 5 s for plugins that load later or reload. */
export function setPluginTabs(names: string[]) {
  wantedPlugins = names.filter((n) => n !== "Handheld Library");
  syncPluginTabs();
  if (pluginTimer === undefined && hook) pluginTimer = window.setInterval(syncPluginTabs, 5000) as unknown as number;
}
