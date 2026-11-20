import { Profile } from "./types";

// Starting points tuned for a Z1 Extreme / 780M at 1080p. They only touch the
// fields they name; anything else in the profile stays as the user set it.
export const PRESETS: { label: string; apply: (p: Profile) => void }[] = [
  {
    label: "Battery (40/80, 12W)",
    apply: (p) => {
      p.scaling = { ...p.scaling, enabled: true, fsr: true, sharpness: 2, resolution: "1280x720" };
      p.frame = { enabled: true, fps: 40, refresh: 0 };
      p.power = { ...p.power, tdpEnabled: true, tdp: 12, gpuMode: "auto" };
    },
  },
  {
    label: "Balanced (45/90, 17W)",
    apply: (p) => {
      p.scaling = { ...p.scaling, enabled: true, fsr: true, sharpness: 2, resolution: "1600x900" };
      p.frame = { enabled: true, fps: 45, refresh: 0 };
      p.power = { ...p.power, tdpEnabled: true, tdp: 17, gpuMode: "auto" };
    },
  },
  {
    label: "Performance (60/120, 25W)",
    apply: (p) => {
      p.scaling = { ...p.scaling, enabled: true, fsr: true, sharpness: 2, resolution: "1728x972" };
      p.frame = { enabled: true, fps: 60, refresh: 0 };
      p.power = { ...p.power, tdpEnabled: true, tdp: 25, gpuMode: "auto" };
    },
  },
  {
    label: "Heavy AAA (40/80 + FG, 30W)",
    apply: (p) => {
      p.scaling = { ...p.scaling, enabled: true, fsr: true, sharpness: 3, resolution: "1536x864" };
      p.frame = { enabled: true, fps: 40, refresh: 0 };
      p.power = { ...p.power, tdpEnabled: true, tdp: 30, gpuMode: "auto" };
      p.fg = { ...p.fg, enabled: true, multiplier: 2, flowScale: 0.75, perfMode: true };
    },
  },
];

export const RESOLUTIONS: { label: string; value: string }[] = [
  { label: "Leave as is", value: "" },
  { label: "Steam default", value: "Default" },
  { label: "Native (100%)", value: "Native" },
  { label: "1728x972 (90%)", value: "1728x972" },
  { label: "1600x900 (83%)", value: "1600x900" },
  { label: "1536x864 (80%)", value: "1536x864" },
  { label: "1280x720 (67%)", value: "1280x720" },
];

/** Lowest refresh that is a whole multiple of fps and inside the panel range. */
export function matchRefresh(fps: number, min: number, max: number): number {
  if (!fps) return max;
  for (let m = 1; m <= 8; m++) {
    const hz = fps * m;
    if (hz >= min && hz <= max) return hz;
  }
  return Math.min(max, Math.max(min, fps));
}
