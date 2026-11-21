import { callable } from "@decky/api";
import type { Config } from "./engine";

export const getConfig = callable<[], Config>("get_config");
export const setConfig = callable<[cfg: Config], Config>("set_config");
export const prepare = callable<[key: string], { ok: true; base: string; have: boolean } | { ok: false; error: string }>("prepare");
export const storeSounds = callable<[key: string, files: Record<string, string>], { ok: true } | { ok: false; error: string }>("store_sounds");
