export type GpuMode = "auto" | "max" | "fixed" | "range";
export type PowerBackend = "auto" | "steam" | "powerstation" | "sysfs" | "hhd" | "off";

export interface Profile {
  name: string;
  scaling: {
    enabled: boolean;     // manage Steam's scaling filter for this game
    fsr: boolean;         // gamescope FSR 1 ("Sharp" filter) vs Linear
    sharpness: number;    // Steam's FSR sharpness value (Steam's own scale)
    resolution: string;   // "" = leave alone, "Default", "Native" or "WxH"
  };
  frame: {
    enabled: boolean;
    fps: number;          // 0 = uncapped
    refresh: number;      // 0 = auto-match to fps, otherwise fixed Hz
  };
  power: {
    tdpEnabled: boolean;
    tdp: number;
    gpuMode: GpuMode;
    gpuMin: number;
    gpuMax: number;
  };
  fg: {
    enabled: boolean;
    multiplier: number;
    flowScale: number;
    perfMode: boolean;
    wsiWorkaround: boolean; // auto-add ENABLE_GAMESCOPE_WSI=0 to launch options
  };
}

export interface ManagedLaunch {
  envs: string[];
  addedCommand: boolean;
}

export interface Settings {
  autoApply: boolean;
  powerBackend: PowerBackend;
  profiles: Record<string, Profile>; // "default" + appids
  launch: Record<string, ManagedLaunch>;
}

export interface Environment {
  powerstation: { running: boolean; card?: string; tdp?: number | null; tdpUnsupported?: boolean; gpuRange?: [number, number] | null; error?: string };
  hhd: { running: boolean; tdpEnabled?: boolean; tdpPrefix?: string; gpuControl?: boolean; steamFuse?: boolean; error?: string };
  power: { sysfsTdp: boolean; tdpMin: number | null; tdpMax: number | null; gpuRange: [number, number] | null };
  lsfg: {
    installed: boolean; ownedByVex: boolean; otherPlugin: string | null; bundled: boolean; bundledVersion: string;
    legacyV1: boolean; configExists: boolean; dll: string; dllFound: boolean; version: number | null; error?: string;
    lossless: { installed: boolean; branch: string | null; needsBranch: boolean; dll: string };
  };
  conflicts: { plugins: { name: string; controls: string }[]; tuned_ppd: boolean };
}

export interface SteamLimits {
  fsrMin: number;
  fsrMax: number;
  refreshMin: number;
  refreshMax: number;
  refreshAvailable: boolean;
  fpsOptions: number[];
  tdpMin: number;
  tdpMax: number;
  filters: number[];
}

export const DEFAULT_PROFILE: Profile = {
  name: "Default",
  scaling: { enabled: false, fsr: true, sharpness: 2, resolution: "" },
  frame: { enabled: false, fps: 60, refresh: 0 },
  power: { tdpEnabled: false, tdp: 20, gpuMode: "auto", gpuMin: 800, gpuMax: 2700 },
  fg: { enabled: false, multiplier: 2, flowScale: 0.8, perfMode: true, wsiWorkaround: true },
};

export const DEFAULT_SETTINGS: Settings = {
  autoApply: true,
  powerBackend: "auto",
  profiles: { default: DEFAULT_PROFILE },
  launch: {},
};

export const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v));

/** Deep-merge saved data over defaults so older saves gain new fields. */
export function normalizeProfile(p: Partial<Profile> | undefined, name?: string): Profile {
  const d = clone(DEFAULT_PROFILE);
  const src: any = p ?? {};
  return {
    name: src.name ?? name ?? d.name,
    scaling: { ...d.scaling, ...(src.scaling ?? {}) },
    frame: { ...d.frame, ...(src.frame ?? {}) },
    power: { ...d.power, ...(src.power ?? {}) },
    fg: { ...d.fg, ...(src.fg ?? {}) },
  };
}
