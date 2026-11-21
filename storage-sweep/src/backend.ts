import { callable } from "@decky/api";

export type Kind = "shadercache" | "compatdata" | "workshop";
export interface Entry { kind: Kind; appid: number; path: string; bytes: number; orphan: boolean; shortcut: boolean }
type Fail = { ok: false; error: string };

export const scan = callable<[knownShortcuts: number[], running: number],
  { ok: true; entries: Entry[]; libraries: string[]; missing: string[] } | Fail>("scan");
export const remove = callable<[paths: string[], running: number],
  { ok: true; freed: number; deleted: string[]; failed: { path: string; error: string }[] } | Fail>("delete");
