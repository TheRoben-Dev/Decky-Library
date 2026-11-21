/*
 * Hooks Steam's UI sound player and swaps its files for the selected Nightgrid pack.
 *
 * Steam plays every Game Mode UI sound through GamepadUIAudio.m_AudioPlaybackManager.PlayAudioURL(url)
 * with URLs like "/sounds/deck_ui_navigation.wav". We patch that one method (before it runs) and
 * hand it the path of our rendered sound instead.
 *
 * Steam's player only plays files from its own UI folder (a blob: URL just comes out silent, which
 * is what 0.1.0 did), so each pack+volume is rendered once, written by the backend to the plugin's
 * data folder, and served through <steam>/steamui/sounds_nightgrid. Later starts find the files on
 * disk and skip rendering. Nothing is polled; unloading removes the patch and Steam's sounds return.
 */
import { beforePatch, findModuleChild } from "@decky/ui";
import { prepare, storeSounds } from "./backend";
import { Cat, CATS, DESIGN_VERSION, PACKS, render, SILENT, wav, categoryOf } from "./sounds";

export type Mode = "pack" | "steam" | "off";
export interface Config { enabled: boolean; pack: string; volume: number; cats: Partial<Record<Cat, Mode>> }
export const DEFAULT_CONFIG: Config = { enabled: true, pack: "nightgrid", volume: 0.8, cats: {} };

let cfg: Config = DEFAULT_CONFIG;
let urls = new Map<Cat, string>();
let silent: string | null = null;
let lastError: string | null = null;
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
  if (mode === "off") return urls.size ? silent : null;
  return urls.get(cat) ?? null;   // not rendered yet -> Steam's own sound this once
}

async function b64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

/** Makes sure the current pack+volume exists as files Steam can load, then points the patch at them. */
async function build() {
  const my = ++gen;
  const pack = PACKS.find((p) => p.id === cfg.pack) ?? PACKS[0];
  const key = `${DESIGN_VERSION}-${pack.id}-${Math.round(cfg.volume * 100)}`;
  try {
    const prep = await prepare(key);
    if (!prep.ok) throw new Error(prep.error);
    if (!prep.have) {
      const files: Record<string, string> = { silent: await b64(SILENT()) };
      for (const { id } of CATS) files[id] = await b64(wav(await render(pack, id, cfg.volume)));
      if (my !== gen) return;                       // settings changed meanwhile
      const st = await storeSounds(key, files);
      if (!st.ok) throw new Error(st.error);
    }
    if (my !== gen) return;
    const next = new Map<Cat, string>();
    for (const { id } of CATS) next.set(id, `${prep.base}${key}/${id}.wav`);
    urls = next;
    silent = `${prep.base}${key}/silent.wav`;
    lastError = null;
  } catch (e: any) {
    // Without files Steam can play, keep Steam's own sounds rather than silence.
    urls = new Map(); silent = null;
    lastError = String(e?.message ?? e);
    console.warn("[Nightgrid Sounds] couldn't prepare sounds:", e);
  }
}

export function engineError(): string | null { return lastError; }

export function hookStatus(): boolean { return hooked; }

export function start(config: Config) {
  cfg = config;
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
  urls = new Map(); silent = null;
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
