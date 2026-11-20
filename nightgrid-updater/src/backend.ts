import { callable } from "@decky/api";

export interface Status {
  installed: string | null;
  latest: string | null;
  updateAvailable: boolean;
  error: string | null;
  release: { tag: string; url: string; notes: string } | null;
}

export const getStatus = callable<[], Status>("status");
export const installLatest = callable<[], { ok: boolean; version?: string; error?: string }>("install_latest");

/** Asks CSS Loader to rescan its themes folder (the same call its own Refresh button makes). */
export async function reloadCssLoader(): Promise<boolean> {
  try {
    const loader = (window as any).DeckyPluginLoader;
    const api = loader?.createLegacyPluginAPI?.("CSS Loader");
    if (!api) return false;
    const r = await api.callPluginMethod("reset", {});
    return !!r?.success;
  } catch (e) {
    console.warn("[Nightgrid Updater] CSS Loader reload failed", e);
    return false;
  }
}
