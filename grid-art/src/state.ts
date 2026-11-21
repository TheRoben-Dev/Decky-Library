/*
 * Module-level state. Steam remounts the Quick Access panel whenever it opens or a dropdown
 * closes, so anything the user picked has to live outside React.
 */
import type { Asset, Settings } from "./backend";

export const state = {
  picked: null as number | null,     // game chosen in the Quick Access picker
  settings: null as Settings | null,
  // `${appid}:${slot}:${gameId}` -> pages loaded so far, kept for the session (cleared on filter change).
  pages: new Map<string, { items: Asset[]; page: number; more: boolean }>(),
  // non-Steam shortcut -> SteamGridDB game it was matched to
  matched: new Map<number, { id: number; name: string }>(),
};

export function clearPages() { state.pages.clear(); }
