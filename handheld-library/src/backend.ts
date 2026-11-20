import { callable } from "@decky/api";

export type DeckMin = "verified" | "playable" | "off";
export type PdbMin = "off" | "gold" | "platinum";
export interface Settings {
  enabled: boolean;
  collectionName: string;
  deckMin: DeckMin;
  steamOS: boolean;
  native: boolean;
  protonDB: PdbMin;
  controller: "partial" | "full";
  excludeUnsupported: boolean;
  installedOnly: boolean;
  collectionId: string;
  hiddenQamTabs: string[];
  hiddenLibraryTabs: string[];
  readyLibraryTab: boolean;
  pluginTabs: string[];
}

export const getSettings = callable<[], Settings>("get_settings");
export const setSettings = callable<[s: Settings], Settings>("set_settings");
/** {appid: tier}; tier is a ProtonDB tier, "pending" or "none". Unreachable apps are left out. */
export const protonDBTiers = callable<[appids: number[]], Record<string, string>>("protondb_tiers");

export interface PinResult { ok: boolean; retryIn?: number; error?: string }
export const pinStatus = callable<[], { set: boolean; retryIn: number }>("pin_status");
export const pinVerify = callable<[code: string], PinResult>("pin_verify");
export const pinSet = callable<[next: string, current: string], PinResult>("pin_set");
export const pinClear = callable<[current: string], PinResult>("pin_clear");
