/*
 * Module-level state shared by Quick Access and the full-screen pages. Steam remounts the
 * Quick Access panel whenever it opens or a dropdown closes, so nothing lives in React state
 * that has to survive that. Components subscribe with useStore() and re-render on change.
 */
import { useEffect, useState } from "react";
import type { Game, Installed, Job, Offer, Settings } from "./backend";

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
  offers: null as Offer[] | null,
  offersError: "",
  claimsUrl: "https://luna.amazon.com/claims/home",
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

export function jobFor(gameId: string): Job | undefined {
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
    case "downloading": return j.total ? `${pct}% · ${fmtBytes(j.done)} / ${fmtBytes(j.total)}${j.speed ? ` · ${fmtBytes(j.speed)}/s` : ""}` : "Checking files…";
    case "finishing": return "Finishing…";
    default: return j.phase;
  }
}

export const gamePath = (id: string) => `/amazon-library/game/${encodeURIComponent(id)}`;
export const offerPath = (id: string) => `/amazon-library/offer/${encodeURIComponent(id)}`;
