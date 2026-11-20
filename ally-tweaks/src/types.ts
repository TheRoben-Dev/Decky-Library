export type LightMode = "off" | "solid" | "pulse" | "duality" | "rainbow" | "spiral";
export type Speed = "low" | "medium" | "high";
export type Reactive = "none" | "battery" | "temperature" | "tdp";

export interface Light {
  mode: LightMode;
  hue: number;
  hue2: number;
  saturation: number;
  brightness: number;
  speed: Speed;
  direction: "left" | "right";
}

export interface GameLight { name: string; light: Light }
export interface GameButtons { name: string; paddles: string; nintendo: boolean }

export interface Settings {
  rgb: {
    managed: boolean;
    base: Light;
    reactive: Reactive;
    lowBattery: boolean;
    lowBatteryAt: number;
    offOnBattery: boolean;
    followScreen: boolean;
    perGame: Record<string, GameLight>;
  };
  charge: { limit: number; travel: boolean };
  buttons: { perGame: Record<string, GameButtons>; default: { paddles: string; nintendo: boolean } | null };
  panel: Record<string, boolean>;
}

export interface AppState {
  device: { product: string; chip: string; bios: string; isAlly2023: boolean };
  hhd: { running: boolean; error?: string };
  battery: {
    present: boolean;
    capacity?: number;
    status?: string;
    ac?: boolean;
    cycles?: number | null;
    health?: number | null;
    watts?: number | null;
    threshold?: number | null;
    thresholdSupported?: boolean;
  };
  panel: { panelOverdrive: boolean | null; bootSound: boolean | null };
  rgb?: {
    supported: boolean;
    hhdRgbEnabled: boolean;
    mode: string | null;
    controllerOwnsLeds: boolean;
    rgbBoot: boolean;
    rgbCharging: boolean;
    hasBootFlags: boolean;
  };
  buttons?: {
    supported: boolean;
    controllerMode: string | null;
    paddles: string | null;
    paddleOptions: string[];
    nintendo: boolean;
  };
  chargeBackend: "hhd" | "sysfs" | "none";
  settings: Settings;
  lightReason: string;
  screen: number | null;
  game: { appid: string; name: string } | null;
}

export const DEFAULT_LIGHT: Light = {
  mode: "solid", hue: 200, hue2: 300, saturation: 100, brightness: 50, speed: "medium", direction: "left",
};

export const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));
