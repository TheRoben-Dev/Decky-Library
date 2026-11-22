import { callable } from "@decky/api";

export interface Dep { kind: "decky" | "steam"; name: string; appid?: number; why?: string; installed: boolean }
export interface Item {
  id: string; kind: "theme" | "plugin"; name: string;
  installed: boolean; installedVersion: string | null; latest: string;
  updateAvailable: boolean; isSelf: boolean; url: string; notes: string; deps: Dep[];
}
export interface Status { items: Item[]; error: string | null; cssLoader: boolean; legacyUpdater: boolean }
interface Prepared { ok: boolean; error?: string; artifact?: string; hash?: string; name?: string; version?: string; installType?: number }

export const getStatus = callable<[force?: boolean], Status>("status");
const preparePlugin = callable<[id: string], Prepared>("prepare_plugin");
const prepareStorePlugin = callable<[name: string], Prepared>("prepare_store_plugin");
export const installTheme = callable<[id: string], { ok: boolean; version?: string; error?: string }>("install_theme");
export const uninstallTheme = callable<[id: string], { ok: boolean; removed?: boolean; error?: string }>("uninstall_theme");

/** Decky Loader's own websocket router (the one its store and Developer page use). */
function deckyBackend(): { call: (route: string, ...args: any[]) => Promise<any> } {
  const b = (window as any).DeckyBackend;
  if (!b?.call) throw new Error("Decky's installer isn't reachable (needs Decky Loader 3).");
  return b;
}

async function handToDecky(p: Prepared): Promise<string | null> {
  if (!p.ok) return p.error ?? "unknown error";
  // Decky shows its install confirmation, downloads the same URL, checks the same SHA-256,
  // replaces any older copy and loads the plugin.
  await deckyBackend().call("utilities/install_plugin", p.artifact, p.name, p.version, p.hash, p.installType);
  return null;
}

/** Returns an error message, or null once Decky's install prompt is up. */
export async function installPlugin(id: string): Promise<string | null> {
  try { return await handToDecky(await preparePlugin(id)); } catch (e) { return String(e); }
}

/** Update several plugins with one Decky prompt: each is downloaded and SHA-256 checked here
 * first, then handed to Decky's batch installer (utilities/install_plugins) in the given order. */
export async function installPluginsBatch(ids: string[], onProgress: (text: string) => void): Promise<string | null> {
  try {
    const reqs: any[] = [];
    for (let i = 0; i < ids.length; i++) {
      onProgress(`Checking ${i + 1}/${ids.length}: ${ids[i]}…`);
      const p = await preparePlugin(ids[i]);
      if (!p.ok) return `${ids[i]}: ${p.error}`;
      reqs.push({ name: p.name, artifact: p.artifact, version: p.version, hash: p.hash, install_type: p.installType });
    }
    if (!reqs.length) return null;
    onProgress("Confirm the updates in Decky's prompt.");
    await deckyBackend().call("utilities/install_plugins", reqs);
    return null;
  } catch (e) { return String(e); }
}

export async function installStorePlugin(name: string): Promise<string | null> {
  try { return await handToDecky(await prepareStorePlugin(name)); } catch (e) { return String(e); }
}

export async function uninstallPlugin(name: string): Promise<string | null> {
  try { await deckyBackend().call("utilities/uninstall_plugin", name); return null; } catch (e) { return String(e); }
}

/** Asks CSS Loader to rescan its themes folder (the same call its own Refresh button makes). */
export async function reloadCssLoader(): Promise<boolean> {
  try {
    const loader = (window as any).DeckyPluginLoader;
    const api = loader?.createLegacyPluginAPI?.("CSS Loader");
    if (!api) return false;
    const r = await api.callPluginMethod("reset", {});
    return !!r?.success;
  } catch (e) {
    console.warn("[Library Hub] CSS Loader reload failed", e);
    return false;
  }
}
