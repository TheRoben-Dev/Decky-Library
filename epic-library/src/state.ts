/*
 * Module-level state shared by Quick Access and the full-screen pages. Steam remounts the
 * Quick Access panel whenever it opens or a dropdown closes, so nothing lives in React state
 * that has to survive that. Components subscribe with useStore() and re-render on change.
 */
import { useEffect, useState } from "react";
import type { BrowseOpts, Game, Installed, Job, Settings, StoreItem } from "./backend";

declare const SteamClient: any;

export const state = {
  settings: null as Settings | null,
  games: null as Game[] | null,
  libraryAt: 0,
  installed: {} as Record<string, Installed>,
  jobs: [] as Job[],
  checking: false,
  lastCheck: 0,
  tab: "all",
  sort: "title" as "title" | "installed" | "size",
  // Browse tab: filters, the results loaded so far and this week's free games.
  store: {
    opts: { query: "", sort: "", price: "", genre: "", controller: true, country: "", page: 1 } as BrowseOpts,
    items: null as StoreItem[] | null,
    more: false,
    key: "",
    note: "",
    genres: [] as [string, string][],
    free: null as StoreItem[] | null,
  },
  offer: null as StoreItem | null,        // the store item open on the offer page
};

/** Steam's store country for prices (falls back to US). */
export async function country(): Promise<string> {
  if (state.store.opts.country) return state.store.opts.country;
  let c = "";
  try { c = String(await SteamClient.User.GetIPCountry() ?? ""); } catch { /* not available */ }
  c = /^[A-Za-z]{2}$/.test(c) ? c.toUpperCase() : "US";
  state.store.opts.country = c;
  return c;
}

const subs = new Set<() => void>();

export function changed() { subs.forEach((f) => { try { f(); } catch { /* unmounted */ } }); }

export function useStore() {
  const [, force] = useState(0);
  useEffect(() => {
    const f = () => force((n) => n + 1);
    subs.add(f);
    return () => { subs.delete(f); };
  }, []);
  return state;
}

export function jobFor(app: string): Job | undefined {
  return state.jobs.find((j) => j.app === app);
}

/** Owned games by store namespace, to mark Browse items you already have. */
export function ownedByNs(ns: string): Game | undefined {
  return ns ? state.games?.find((g) => g.ns === ns) : undefined;
}

/** Epic's CDN resizes images on request; tiles never need the multi-megabyte originals. */
export function sized(url: string, w: number, h: number): string {
  if (!url || !/^https:\/\/[^/]*epicgames\.com\//.test(url) || url.includes("?")) return url;
  return `${url}?w=${w}&h=${h}&resize=1&quality=high`;
}

export function updateCount(): number {
  return Object.values(state.installed).filter((r) => r.update).length;
}

export function fmtBytes(n: number): string {
  if (!n) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(u.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
  return `${(n / 1024 ** i).toFixed(i >= 2 ? 1 : 0)} ${u[i]}`;
}

export function jobLine(j: Job): string {
  const pct = j.total ? Math.floor((j.done / j.total) * 100) : 0;
  switch (j.phase) {
    case "queued": return "Queued";
    case "preparing": return j.action === "repair" ? "Checking files…" : "Preparing…";
    case "downloading": return j.total ? `${pct}% · ${fmtBytes(j.done)} / ${fmtBytes(j.total)}${j.speed ? ` · ${fmtBytes(j.speed)}/s` : ""}` : `${fmtBytes(j.done)}`;
    case "finishing": return "Finishing…";
    default: return j.phase;
  }
}
