import { callable } from "@decky/api";

export type Kind = "boot" | "suspend";
export interface Movie { id: string; name: string; file: string; about?: string }
export type SlotState = "ours" | "other" | "partial" | "none";
export interface Status {
  ok: boolean; error?: string;
  catalog: Record<Kind, Movie[]>;
  boot: string; suspend: string; shuffle: boolean;
  states: Record<Kind, SlotState>;
  overrideDir: string;
}

export const getStatus = callable<[], Status>("status");
export const applyMovie = callable<[kind: Kind, movieId: string], Status>("apply");
export const setShuffle = callable<[on: boolean], boolean>("set_shuffle");
