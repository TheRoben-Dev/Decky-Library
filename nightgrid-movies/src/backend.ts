import { callable } from "@decky/api";

export type Kind = "boot" | "suspend";
export interface Movie { id: string; name: string; file: string; about?: string; thumb?: string | null }
export type SlotState = "ours" | "other" | "partial" | "none";
export interface Status {
  ok: boolean; error?: string;
  catalog: Record<Kind, Movie[]>;
  boot: string; suspend: string; shuffle: boolean;
  states: Record<Kind, SlotState>;
  overrideDir: string;
  saver: SaverSettings;
}
export interface SaverSettings { enabled: boolean; minutes: number; style: string }

export const getStatus = callable<[], Status>("status");
export const applyMovie = callable<[kind: Kind, movieId: string], Status>("apply");
export const setShuffle = callable<[on: boolean], boolean>("set_shuffle");
export const getSaver = callable<[], SaverSettings>("get_saver");
export const setSaver = callable<[saver: SaverSettings], SaverSettings>("set_saver");
export const movieChunk = callable<[movieId: string, offset: number],
  { ok: boolean; error?: string; data: string; size: number; next: number; done: boolean }>("movie_chunk");

const urls = new Map<string, string>();
/** Fetches a bundled video from the backend in pieces and returns a blob: URL (cached). */
export async function movieUrl(id: string, onProgress?: (pct: number) => void): Promise<string> {
  const hit = urls.get(id); if (hit) return hit;
  const parts: Uint8Array[] = []; let off = 0;
  for (;;) {
    const c = await movieChunk(id, off);
    if (!c.ok) throw new Error(c.error ?? "couldn't read the video");
    const bin = atob(c.data), buf = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
    parts.push(buf); off = c.next; onProgress?.(Math.round((off / Math.max(1, c.size)) * 100));
    if (c.done) break;
  }
  const url = URL.createObjectURL(new Blob(parts as BlobPart[], { type: "video/webm" }));
  urls.set(id, url);
  return url;
}
