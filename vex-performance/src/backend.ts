import { callable } from "@decky/api";
import { Environment, Settings } from "./types";

export const getSettings = callable<[], Partial<Settings>>("get_settings");
export const saveSettings = callable<[data: Settings], boolean>("save_settings");
export const getEnvironment = callable<[], Environment>("get_environment");
export const applyPower = callable<
  [backend: string, tdpEnabled: boolean, tdp: number, gpuMode: string, gpuMin: number, gpuMax: number],
  { tdp: string | null; gpu: string | null; error?: string }
>("apply_power");
export const resetPower = callable<[backend: string], boolean>("reset_power");
export const lsfgSetGame = callable<
  [appid: string, name: string, enabled: boolean, multiplier: number, flowScale: number, perfMode: boolean],
  { ok: boolean; error?: string; dll?: string }
>("lsfg_set_game");
export const lsfgInstall = callable<[force: boolean], { ok: boolean; error?: string; skipped?: string; installed?: string }>("lsfg_install");
export const log = callable<[msg: string], void>("log");
