export type Family = "ge" | "cachyos";
export type Mode = "auto" | "pinned" | "off";

export interface GameRecord {
  mode: Mode;
  /** Tool we last applied ("" = Steam default). */
  setByUs: string | null;
  /** Previous tools, oldest first. "" means Steam default. */
  history: string[];
  /** Has the current tool survived a real play session yet? */
  verified: boolean;
  changedAt: number;
  note?: string;
}

export interface Settings {
  autoManage: boolean;
  preferredFamily: Family;
  autoInstall: boolean;
  autoUpdate: boolean;
  autoRollback: boolean;
  games: Record<string, GameRecord>;
}

export const DEFAULT_SETTINGS: Settings = {
  autoManage: true,
  preferredFamily: "ge",
  autoInstall: true,
  autoUpdate: true,
  autoRollback: true,
  games: {},
};

export interface DiskTool {
  name: string;
  display: string;
  dir: string;
  family: string;
  owned: boolean;
  system: boolean;
}

export interface ProtonDBSummary {
  tier?: string;
  bestReportedTier?: string;
  trendingTier?: string;
  provisionalTier?: string;
  confidence?: string;
  score?: number;
  total?: number;
}

export interface Release {
  ok: boolean;
  error?: string;
  family?: Family;
  label?: string;
  tag?: string;
  published?: string;
  asset?: { file: string; size: number } | null;
}

export interface InstallState {
  phase: "idle" | "starting" | "downloading" | "verifying" | "extracting" | "done" | "error";
  family?: Family;
  tag?: string;
  done_bytes?: number;
  total?: number;
  error?: string | null;
  tool?: string;
  display?: string;
  verified?: boolean;
  already?: boolean;
}

export interface SteamTool {
  name: string;
  display: string;
}

export interface GameInfo {
  appid: string;
  name: string;
  lastPlayed: number;
  deckCategory: number; // 0 unknown, 1 unsupported, 2 playable, 3 verified
  native: boolean;
  currentTool: string;
  currentPriority: number;
}

export const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v));

export function newRecord(): GameRecord {
  return { mode: "auto", setByUs: null, history: [], verified: true, changedAt: 0 };
}
