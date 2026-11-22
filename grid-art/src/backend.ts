import { callable } from "@decky/api";

export type Kind = "grids" | "heroes" | "logos" | "icons";
export interface Settings {
  hasKey: boolean; keyHint: string; home: string;
  nsfw: boolean; humor: boolean; epilepsy: boolean; animated: boolean;
  styles: Record<Kind, string[]>;
}
export interface Asset {
  id: number; url: string; thumb: string; width: number; height: number;
  style: string; mime: string; score: number; nsfw: boolean; humor: boolean; epilepsy: boolean; author: string;
}
export interface Game { id: number; name: string; verified: boolean; year: number | null }
type Fail = { ok: false; error: string; status?: number };

export const getSettings = callable<[], Settings>("settings");
export const setKey = callable<[key: string], { ok: true; checked: boolean; settings: Settings } | Fail>("set_key");
export const clearKey = callable<[], Settings>("clear_key");
export const setOptions = callable<[opts: Partial<Settings>], Settings>("set_options");
export const getAssets = callable<[kind: Kind, appid: number, gameId: number, shape: string, page: number],
  { ok: true; items: Asset[]; page: number; more: boolean } | Fail>("assets");
export const searchGames = callable<[term: string], { ok: true; games: Game[] } | Fail>("search");
export const getImage = callable<[url: string], { ok: true; data: string; ext: "png" | "jpg"; bytes: number } | Fail>("image");
export const saveIcon = callable<[appid: number, url: string], { ok: true; path: string } | Fail>("save_icon");
export const readLocal = callable<[appid: number, slot: string, path: string],
  { ok: true; data?: string; ext?: "png" | "jpg"; path?: string } | Fail>("read_local");
export const getApplied = callable<[appid: number], Partial<Record<string, number>>>("applied");
export const markApplied = callable<[appid: number, slot: string, assetId: number | null], Partial<Record<string, number>>>("mark_applied");
export type Match = { id: number; name: string };
export const getMatch = callable<[appid: number], Match | null>("match");
export const setMatch = callable<[appid: number, game: Match | null], Match | null>("set_match");
