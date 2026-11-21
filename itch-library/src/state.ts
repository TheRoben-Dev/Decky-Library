/*
 * Module-level state shared by Quick Access and the full-screen pages. Steam remounts the
 * Quick Access panel whenever it opens or a dropdown closes, so nothing lives in React state
 * that has to survive that. Components subscribe with useStore() and re-render on change.
 */
import { useEffect, useState } from "react";
import type { BrowseOpts, Game, Installed, Job, Settings, StoreItem } from "./backend";

export const state = {
  settings: null as Settings | null,
  games: null as Game[] | null,
  libraryAt: 0,
  installed: {} as Record<string, Installed>,
  jobs: [] as Job[],
  checking: false,
  lastCheck: 0,
  tab: "all",
  sort: "added" as "added" | "title",
  // Browse tab: filters, the query when searching, and the results loaded so far.
  store: {
    opts: { sort: "", price: "", genre: "", controller: "gamepad", platform: "", page: 1, released: "", duration: "",
      multiplayer: "", accessibility: "", engine: "", tags: [], demo: false } as BrowseOpts,
    moreFilters: false,
    web: "",      // the same browse page on itch.io's website
    query: "",
    items: null as StoreItem[] | null,
    more: false,
    key: "",
  },
  resolved: new Map<string, number>(),   // feed item URL -> game id
};

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

export function jobFor(gameId: number): Job | undefined {
  return state.jobs.find((j) => j.game_id === gameId);
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
    case "preparing": return "Preparing…";
    case "downloading": return j.total ? `${pct}% · ${fmtBytes(j.done)} / ${fmtBytes(j.total)}${j.speed ? ` · ${fmtBytes(j.speed)}/s` : ""}` : `${fmtBytes(j.done)}`;
    case "unpacking": return "Unpacking…";
    case "merging": return "Keeping your saves…";
    case "finishing": return "Finding the game…";
    default: return j.phase;
  }
}
