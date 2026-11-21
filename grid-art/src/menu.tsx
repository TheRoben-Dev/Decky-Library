/*
 * "Change artwork…" in the library's game menu (the one with Play / Manage / Properties),
 * placed right above "Properties…", i.e. between Manage and Properties.
 *
 * Steam builds that menu from a LibraryContextMenu component. We find it once at load, patch its
 * render (and, the first time it renders, the inner menu class it wraps) and add one MenuItem.
 * Each render first removes our item, so it never shows twice. Patches are undone on unload.
 * Everything is wrapped in try/catch: if a Steam update moves things, the menu just stays stock.
 */
import { afterPatch, fakeRenderComponent, findInReactTree, findInTree, findModuleByExport, MenuItem, Navigation } from "@decky/ui";

const KEY = "grid-art-change-artwork";
type Unpatch = { unpatch(): void };

function menuComponent(): any | null {
  try {
    const mod = findModuleByExport((e: any) => typeof e?.toString === "function" && e.toString().includes("().LibraryContextMenu"));
    if (!mod) return null;
    const render = Object.values(mod).find((v: any) => typeof v === "function" && v.toString().includes("navigator:"));
    return render ? fakeRenderComponent(render as any)?.type ?? null : null;
  } catch (e) {
    console.warn("[Grid Art] game menu not found", e);
    return null;
  }
}

/** The app the menu is for: newer clients pass `app` down the tree, older ones an `overview` prop. */
function appidIn(node: any): number | null {
  try {
    const hit = findInTree(node, (x: any) => typeof x?.app?.appid === "number", { walkable: ["props", "children"] });
    if (hit) return hit.app.appid;
  } catch { /* fall through */ }
  const owner = node?._owner?.pendingProps?.overview?.appid;
  return typeof owner === "number" ? owner : null;
}

const isGameMenu = (items: any) =>
  Array.isArray(items) && items.length > 0 &&
  !!findInReactTree(items, (x: any) => typeof x?.props?.onSelected === "function" && x.props.onSelected.toString().includes("launchSource"));

function addItem(items: any[], appid: number) {
  const old = items.findIndex((x: any) => x?.key === KEY);
  if (old >= 0) items.splice(old, 1);
  let at = items.findIndex((x: any) =>
    findInReactTree(x, (y: any) => typeof y?.onSelected === "function" && y.onSelected.toString().includes("AppProperties")));
  if (at < 0) at = items.length;
  items.splice(at, 0,
    <MenuItem key={KEY} onSelected={() => Navigation.Navigate(`/grid-art/${appid}`)}>Change artwork…</MenuItem>);
}

export function patchGameMenu(): Unpatch {
  const Menu = menuComponent();
  if (!Menu?.prototype?.render) return { unpatch() {} };
  const patches: Unpatch[] = [];
  let lastAppid: number | null = null;
  let inner = false;

  const patchInner = (proto: any) => {
    inner = true;
    patches.push(afterPatch(proto, "render", (_: any[], ret: any) => {
      try {
        const items = ret?.props?.children?.[0];
        if (!isGameMenu(items)) return ret;
        const appid = appidIn(items) ?? lastAppid;
        if (appid) addItem(items, appid);
      } catch (e) { console.warn("[Grid Art] menu patch skipped", e); }
      return ret;
    }));
  };

  patches.push(afterPatch(Menu.prototype, "render", (_: any[], tree: any) => {
    try {
      lastAppid = appidIn(tree) ?? appidIn(tree?.props?.children) ?? lastAppid;
      if (!inner && typeof tree?.type === "function" && tree.type.prototype?.render) {
        patchInner(tree.type.prototype);              // already the menu class
      } else if (!inner && typeof tree?.type === "function") {
        // The inner menu class isn't reachable until the wrapper renders once; catch it there.
        const wrapped = tree.type;
        tree.type = function GridArtMenuProbe(this: any, ...args: any[]) {
          const r = wrapped.apply(this, args);
          if (!inner && r?.type?.prototype?.render) patchInner(r.type.prototype);
          return r;
        };
      }
    } catch (e) { console.warn("[Grid Art] menu patch skipped", e); }
    return tree;
  }));

  return { unpatch() { patches.forEach((p) => p.unpatch()); } };
}
