/*
 * Steam Library tab hiding (+ optional "Handheld Ready" collection tab).
 *
 * Steam has no setting for this: Game Mode builds its Library tabs in a useMemo inside the library
 * component (ids AllGames, Installed, GreatOnDeck / SteamOSCompatible / GreatOnMachine / GreatOnFrame /
 * Xbox / PS4 / PS5, Favorites, RemotePlay, ReadyToPlay, Collections, DesktopApps, Soundtracks; checked
 * against the Nov 2026 client). We use the same technique TabMaster uses: patch the /library route,
 * and while the inner library component renders, wrap React's useMemo so the tab list it returns can
 * be filtered. Every step checks the shape it expects; anything else returns Steam's own tabs.
 * If TabMaster is installed we stay out of its way (it owns this list).
 */
import { routerHook } from "@decky/api";
import { afterPatch, replacePatch, wrapReactType } from "@decky/ui";
import { cloneElement, isValidElement, ReactElement } from "react";
import { getCollection } from "./steam";

export const LIBRARY_TABS: Record<string, string> = {
  GreatOnDeck: "Great on Deck",
  SteamOSCompatible: "SteamOS Compatible",
  GreatOnMachine: "Great on Steam Machine",
  GreatOnFrame: "Great on Steam Frame",
  Xbox: "Controller games",
  PS4: "PS4 controller games",
  PS5: "PS5 controller games",
  AllGames: "All games",
  Installed: "Installed",
  Favorites: "Favorites",
  RemotePlay: "Remote Play",
  ReadyToPlay: "Ready to play",
  Collections: "Collections",
  DesktopApps: "Non-Steam",
  Soundtracks: "Soundtracks",
};
export const READY_TAB_ID = "HandheldReady";

export interface LibraryConfig { hidden: Set<string>; readyTab: { name: string; collectionId: string } | null }

let config: LibraryConfig = { hidden: new Set(), readyTab: null };
let active = false;
let failed = false;
let routePatch: any = null;
let version = 0;
const seen = new Set<string>();

export function setLibraryConfig(c: LibraryConfig) {
  config = c;
  version++;
}
export function libraryActive(): boolean { return active && !failed; }
export function tabMasterInstalled(): boolean {
  try {
    const plugins: any[] = (window as any).DeckyPluginLoader?.plugins ?? [];
    return plugins.some((p) => p?.name === "TabMaster");
  } catch { return false; }
}
export function seenLibraryTabs(): string[] { return [...seen]; }

function dispatcher(): any {
  const R: any = (window as any).SP_REACT;
  return R?.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED?.ReactCurrentDispatcher?.current
    || Object.values(R?.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE ?? {}).find((p: any) => p?.useEffect);
}

function readyTab(tpl: any): any | null {
  const rt = config.readyTab;
  if (!rt) return null;
  const col = getCollection(rt.collectionId);
  const inner = tpl?.content?.props?.children;
  if (!col || !isValidElement(tpl?.content) || !isValidElement(inner) || !(inner.props as any)?.collection) return null;
  const addon = typeof tpl.renderTabAddon === "function" ? tpl.renderTabAddon() : null;
  return {
    id: READY_TAB_ID,
    title: rt.name,
    renderTabAddon: () => (isValidElement(addon) && (addon.props as any)?.collection ? cloneElement(addon as ReactElement<any>, { collection: col }) : null),
    content: cloneElement(tpl.content as ReactElement<any>, { value: { label: rt.name } }, cloneElement(inner as ReactElement<any>, { collection: col })),
    footer: tpl.footer ? { onOptionsButton: tpl.footer.onOptionsButton, onOptionsActionDescription: tpl.footer.onOptionsActionDescription } : undefined,
  };
}

/** Returns the patched tab list, or `original` untouched if anything doesn't look as expected. */
export function transform(original: any): any {
  if (!active || failed || !Array.isArray(original)) return original;
  const nested = Array.isArray(original[0]);
  const tabs: any[] = nested ? original[0] : original;
  if (!tabs.length || !tabs.every((t) => t && typeof t.id === "string" && "content" in t)) return original;
  if (!tabs.some((t) => t.id === "AllGames")) return original;
  try {
    tabs.forEach((t) => seen.add(t.id));
    let out = tabs.filter((t) => !config.hidden.has(t.id));
    const extra = readyTab(tabs.find((t) => t.id === "AllGames"));
    if (extra && !config.hidden.has(READY_TAB_ID)) out.splice(Math.min(1, out.length), 0, extra);
    if (!out.length) out = tabs;   // never leave the Library without tabs
    return nested ? [out, ...original.slice(1)] : out;
  } catch (e) {
    console.error("[Handheld Library] library tab patch failed; using Steam's tabs", e);
    failed = true;
    return original;
  }
}

export function installLibrary(): boolean {
  if (active) return true;
  if (tabMasterInstalled()) return false;
  failed = false;
  try {
    routePatch = routerHook.addPatch("/library", (props: any) => {
      if (!active) return props;
      afterPatch(props.children, "type", (_a: any[], ret1: any) => {
        if (!active || !ret1?.type) return ret1;
        let cached: any;
        afterPatch(ret1, "type", (_b: any[], ret2: any) => {
          if (!active || !ret2?.type) return ret2;
          if (cached) { ret2.type = cached; return ret2; }
          const orig = ret2.type?.type;
          if (typeof orig !== "function") return ret2;
          wrapReactType(ret2);
          replacePatch(ret2.type, "type", (args: any[]) => {
            const d = dispatcher();
            if (!active || failed || !d?.useMemo) return orig(...args);
            const real = d.useMemo;
            d.useMemo = (fn: () => any, deps: any[]) =>
              real(() => transform(fn()), Array.isArray(deps) ? [...deps, version] : deps);
            try { return orig(...args); } finally { d.useMemo = real; }
          });
          cached = ret2.type;
          return ret2;
        });
        return ret1;
      });
      return props;
    });
    active = true;
    return true;
  } catch (e) {
    console.error("[Handheld Library] couldn't patch the Library route", e);
    return false;
  }
}

export function uninstallLibrary() {
  active = false;   // patched components already mounted become pass-throughs immediately
  if (routePatch) { try { routerHook.removePatch("/library", routePatch); } catch { /* ignore */ } }
  routePatch = null;
}

