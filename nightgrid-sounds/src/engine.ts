/*
 * Hooks Steam's UI sound player and swaps its files for the selected Nightgrid pack.
 *
 * Steam plays every Game Mode UI sound through GamepadUIAudio.m_AudioPlaybackManager.PlayAudioURL(url)
 * with URLs like "/sounds/deck_ui_navigation.wav". We patch that one method (before it runs) and
 * hand it a blob: URL of our rendered sound instead. No files are written, nothing is polled, and
 * unloading the plugin removes the patch, so Steam's own sounds come straight back.
 */
import { beforePatch, findModuleChild } from "@decky/ui";
import { Cat, CATS, PACKS, render, SILENT, wav, categoryOf } from "./sounds";

export type Mode = "pack" | "steam" | "off";
export interface Config { enabled: boolean; pack: string; volume: number; cats: Partial<Record<Cat, Mode>> }
export const DEFAULT_CONFIG: Config = { enabled: true, pack: "nightgrid", volume: 0.8, cats: {} };

let cfg: Config = DEFAULT_CONFIG;
let urls = new Map<Cat, string>();
let silent: string | null = null;
let gen = 0;
let patch: { unpatch(): void } | null = null;
let hooked = false;

function audioManager(): any {
  try {
    const parent = findModuleChild((m: any) => {
      if (typeof m !== "object" || !m) return undefined;
      for (const k in m) if (m[k]?.GamepadUIAudio?.m_AudioPlaybackManager) return m[k];
      return undefined;
    });
    return parent?.GamepadUIAudio?.m_AudioPlaybackManager ?? null;
  } catch { return null; }
}

function resolve(url: string): string | null {
  if (!cfg.enabled || typeof url !== "string") return null;
  const cat = categoryOf(url);
  if (!cat) return null;
  const mode = cfg.cats[cat] ?? "pack";
  if (mode === "steam") return null;
  if (mode === "off") return silent;
  return urls.get(cat) ?? null;   // not rendered yet -> Steam's own sound this once
}

/** Renders every category of the current pack at the current volume (a few ms each). */
async function build() {
  const my = ++gen;
  const pack = PACKS.find((p) => p.id === cfg.pack) ?? PACKS[0];
  const next = new Map<Cat, string>();
  for (const { id } of CATS) {
    try {
      const data = await render(pack, id, cfg.volume);
      if (my !== gen) { next.forEach(URL.revokeObjectURL); return; }   // settings changed meanwhile
      next.set(id, URL.createObjectURL(wav(data)));
    } catch (e) {
      console.warn("[Nightgrid Sounds] render failed", id, e);
    }
  }
  const old = urls;
  urls = next;
  // Steam may still be decoding an old URL for a moment; let it finish before revoking.
  setTimeout(() => old.forEach(URL.revokeObjectURL), 5000);
}

export function hookStatus(): boolean { return hooked; }

export function start(config: Config) {
  cfg = config;
  if (!silent) silent = URL.createObjectURL(SILENT());
  if (!patch) {
    const mgr = audioManager();
    const proto = mgr && Object.getPrototypeOf(mgr);
    if (proto && typeof proto.PlayAudioURL === "function") {
      patch = beforePatch(proto, "PlayAudioURL", (args: any[]) => {
        const swap = resolve(args[0]);
        if (swap) args[0] = swap;
        return args;
      });
      hooked = true;
    } else {
      console.warn("[Nightgrid Sounds] Steam's sound player wasn't found; this Steam build isn't supported yet.");
    }
  }
  if (cfg.enabled) build(); else { gen++; }
}

export function update(next: Config) {
  const rebuild = next.enabled && (!cfg.enabled || next.pack !== cfg.pack || next.volume !== cfg.volume || urls.size === 0);
  cfg = next;
  if (rebuild) build();
}

export function stop() {
  gen++;
  patch?.unpatch(); patch = null; hooked = false;
  urls.forEach(URL.revokeObjectURL); urls = new Map();
  if (silent) { URL.revokeObjectURL(silent); silent = null; }
}

let previewEl: HTMLAudioElement | null = null;
/** Plays one sound of a pack straight away (rendered on the spot, not cached). */
export async function preview(packId: string, cat: Cat, volume: number) {
  const pack = PACKS.find((p) => p.id === packId) ?? PACKS[0];
  const url = URL.createObjectURL(wav(await render(pack, cat, volume)));
  previewEl?.pause();
  previewEl = new Audio(url);
  previewEl.onended = () => URL.revokeObjectURL(url);
  await previewEl.play().catch(() => URL.revokeObjectURL(url));
}

/** Other sound plugins patch the same player; tell the user instead of fighting over it. */
export function otherSoundPlugin(): string | null {
  try {
    const names: string[] = ((window as any).DeckyPluginLoader?.plugins ?? []).map((p: any) => String(p?.name ?? ""));
    return names.find((n) => /audio\s*loader/i.test(n)) ?? null;
  } catch { return null; }
}
