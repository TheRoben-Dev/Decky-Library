import { callable } from "@decky/api";
import type { Config } from "./engine";

export const getConfig = callable<[], Config>("get_config");
export const setConfig = callable<[cfg: Config], Config>("set_config");
