import { callable } from "@decky/api";
import { DiskTool, Family, InstallState, ProtonDBSummary, Release, Settings } from "./types";

export const getSettings = callable<[], Partial<Settings>>("get_settings");
export const saveSettings = callable<[data: Settings], boolean>("save_settings");
export const listTools = callable<[], { tools: DiskTool[]; compatDir: string }>("list_tools");
export const latestRelease = callable<[family: Family, force: boolean], Release>("latest_release");
export const install = callable<[family: Family], { ok: boolean; error?: string }>("install");
export const installState = callable<[], InstallState>("install_state");
export const removeTool = callable<[name: string], { ok: boolean; error?: string }>("remove_tool");
export const protondbSummaries = callable<
  [appids: string[], force: boolean],
  Record<string, ProtonDBSummary | null | "error">
>("protondb_summaries");
export const log = callable<[msg: string], void>("log");
