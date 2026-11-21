/*
 * "Change artwork…" in the library's game menu (the one with Play / Manage / Properties),
 * placed right above "Properties…", i.e. between Manage and Properties.
 *
 * Steam builds that menu from a LibraryContextMenu component. We find it once at load, patch its
 * render, the inner menu class it wraps (render + shouldComponentUpdate, since Steam updates the
 * open menu in place) and add one MenuItem wherever the item list shows up. Each insert first
 * removes our item, so it never shows twice. Patches are undone on unload.
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

/** Inserts into whichever of these is the game menu's item list (Steam renders it at either level). */
function tryInsert(candidates: any[], appid: number | null): boolean {
  if (!appid) return false;
  for (const c of candidates) {
    if (isGameMenu(c)) { addItem(c, appid); return true; }
  }
  return false;
}

export function patchGameMenu(): Unpatch {
  const Menu = menuComponent();
  if (!Menu?.prototype?.render) return { unpatch() {} };
  const patches: Unpatch[] = [];
  let lastAppid: number | null = null;
  let inner = false;

  // The inner menu class renders its item list; it also updates in place when Steam refreshes the
  // app (shouldComponentUpdate with new children), so both paths add the entry back.
  const patchInner = (proto: any) => {
    inner = true;
    patches.push(afterPatch(proto, "render", function (this: any, _: any[], ret: any) {
      try {
        const kids = ret?.props?.children;
        tryInsert([kids?.[0], kids], appidIn(kids) ?? appidIn(this?.props) ?? lastAppid);
      } catch (e) { console.warn("[Grid Art] menu patch skipped", e); }
      return ret;
    }));
    if (typeof proto.shouldComponentUpdate === "function") {
      patches.push(afterPatch(proto, "shouldComponentUpdate", ([next]: any[], update: any) => {
        try {
          const kids = next?.children;
          tryInsert([kids, kids?.[0]], appidIn(kids) ?? lastAppid);
        } catch { /* leave Steam's decision alone */ }
        return update;
      }));
    }
  };

  patches.push(afterPatch(Menu.prototype, "render", (_: any[], tree: any) => {
    try {
      const kids = tree?.props?.children;
      lastAppid = appidIn(tree) ?? appidIn(kids) ?? lastAppid;
      // Later opens often hand the item list straight to the menu element.
      tryInsert([kids, kids?.[0]], lastAppid);
      if (!inner && typeof tree?.type === "function") {
        if (tree.type.prototype?.render) {
          patchInner(tree.type.prototype);              // already the menu class
        } else {
          // The inner class only appears once the wrapper renders; catch it on this element.
          // (afterPatch keeps the wrapper's static fields, so React treats it the same.)
          afterPatch(tree, "type", (_a: any[], r: any) => {
            if (!inner && r?.type?.prototype?.render) patchInner(r.type.prototype);
            return r;
          });
        }
      }
    } catch (e) { console.warn("[Grid Art] menu patch skipped", e); }
    return tree;
  }));

  return { unpatch() { patches.forEach((p) => p.unpatch()); } };
}
