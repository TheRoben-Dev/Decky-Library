import { callable } from "@decky/api";
import { AppState, Settings } from "./types";

type Res = { ok: boolean; error?: string; backend?: string };

export const getState = callable<[], AppState>("get_state");
export const saveSettings = callable<[patch: Partial<Settings>], boolean>("save_settings");
export const setGame = callable<[appid: string, name: string], boolean>("set_game");
export const setCharge = callable<[limit: number, travel: boolean], Res>("set_charge");
export const setRgbFlags = callable<[boot: boolean, charging: boolean], Res>("set_rgb_flags");
export const setPanel = callable<[key: string, on: boolean], Res>("set_panel");
export const setButtonsGlobal = callable<[paddles: string, nintendo: boolean], Res>("set_buttons_global");
export const setSystem = callable<[key: string, on: boolean | string], Res>("set_system");
export const setPcie = callable<[off: boolean], Res>("set_pcie");
export const setApuMem = callable<[index: number], Res>("set_apu_mem");
export const reapplyButtons = callable<[], Res>("reapply_buttons");
export const log = callable<[msg: string], void>("log");
