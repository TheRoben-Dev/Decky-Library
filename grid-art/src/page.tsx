/*
 * Full-screen artwork browser: /grid-art/:appid
 * One tab per artwork slot (L1/R1 switch tabs). Pick a tile to apply it, Reset to go back to
 * Steam's own art. Pages of results are fetched only when a tab is opened or "More" is pressed.
 * Search (or Y on a tile) looks the art up under any name; the pick is remembered per app.
 */
import { DialogButton, Dropdown, Focusable, Navigation, showModal, SteamSpinner, Tabs, Toggle, useParams } from "@decky/ui";
import { openFilePicker, toaster } from "@decky/api";
import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Asset, getApplied, getAssets, getImage, getMatch, getSettings, markApplied, Match, readLocal, saveIcon, searchGames, setMatch, setOptions, Settings } from "./backend";
import { appInfo, clearArt, setArt, setShortcutIcon, Slot, SLOTS } from "./steam";
import { state } from "./state";
import { SearchModal } from "./search";

import { C, PAGE_CSS } from "./ui";

const STYLE_NAMES: Record<string, string> = {
  alternate: "Alternate", blurred: "Blurred", white_logo: "White logo", material: "Material", no_logo: "No logo",
  official: "Official", white: "White", black: "Black", custom: "Custom",
};
const STYLES: Record<string, string[]> = {
  grids: ["alternate", "blurred", "white_logo", "material", "no_logo"],
  heroes: ["alternate", "blurred", "material"],
  logos: ["official", "white", "black", "custom"],
  icons: ["official", "custom"],
};

function toast(body: string) { toaster.toast({ title: "Grid Art", body }); }

function Thumb({ a }: { a: Asset }) {
  const src = a.thumb || a.url;
  if (/\.webm($|\?)/i.test(src)) return <video src={src} muted loop autoPlay playsInline />;
  return <img src={src} loading="lazy" decoding="async" draggable={false} />;
}

function SlotTab({ appid, gameIds, names, slot, settings, onSettings, applied, setApplied, shortcut, onSearch }: {
  appid: number; gameIds: number[]; names: Map<number, string>; slot: Slot; settings: Settings; onSettings: (s: Settings) => void;
  applied: Partial<Record<string, number>>; setApplied: (a: Partial<Record<string, number>>) => void; shortcut: boolean;
  onSearch: () => void;
}) {
  // Filters are part of the key, so changing one starts a fresh list instead of showing stale results.
  const filt = [settings.animated, settings.nsfw, settings.humor, settings.epilepsy, (settings.styles[slot.kind] ?? []).join(",")].join("|");
  const key = `${appid}:${slot.id}:${gameIds.join(",")}:${filt}`;
  const [data, setData] = useState(() => state.pages.get(key) ?? null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | "reset" | "file" | null>(null);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const keyRef = useRef(key);
  keyRef.current = key;
  const load = async (page: number) => {
    const forKey = key;
    setLoading(true); setError(null);
    try {
      const r = await getAssets(slot.kind, appid, gameIds, slot.shape, page);
      if (!alive.current || keyRef.current !== forKey) return;
      if (!r.ok) { setError(r.error); return; }
      const prev = page > 0 ? state.pages.get(forKey)?.items ?? [] : [];
      const seen = new Set(prev.map((x) => x.id));
      const next = { items: [...prev, ...r.items.filter((x) => !seen.has(x.id))], page, more: r.more };
      state.pages.set(forKey, next);
      setData(next);
    } catch (e) {
      if (alive.current && keyRef.current === forKey) setError(String(e));
    } finally {
      if (alive.current && keyRef.current === forKey) setLoading(false);
    }
  };

  useEffect(() => {
    const hit = state.pages.get(key);
    setData(hit ?? null);
    if (!hit) load(0);
  }, [key]);

  const apply = async (a: Asset) => {
    if (busy !== null) return;
    setBusy(a.id);
    try {
      if (slot.id === "icon" && shortcut) {
        const r = await saveIcon(appid, a.url);
        if (!r.ok) throw new Error(r.error);
        setShortcutIcon(appid, r.path);
      } else {
        const r = await getImage(a.url);
        if (!r.ok) throw new Error(r.error);
        await setArt(appid, r.data, r.ext, slot.asset);
      }
      setApplied(await markApplied(appid, slot.id, a.id));
      toast(`${slot.title} set`);
    } catch (e: any) {
      toast(`Couldn't set ${slot.title.toLowerCase()}: ${e?.message ?? e}`);
    } finally {
      if (alive.current) setBusy(null);
    }
  };

  const reset = async () => {
    setBusy("reset");
    try {
      if (slot.id === "icon" && shortcut) setShortcutIcon(appid, "");
      else await clearArt(appid, slot.asset);
      setApplied(await markApplied(appid, slot.id, null));
      toast(`${slot.title} reset to Steam's`);
    } catch (e: any) {
      toast(`Reset failed: ${e?.message ?? e}`);
    } finally {
      if (alive.current) setBusy(null);
    }
  };

  const fromFile = async () => {
    setBusy("file");
    try {
      const pick = await openFilePicker(0 /* FileSelectionType.FILE */, settings.home || "/home", true, true, undefined,
        ["png", "jpg", "jpeg"], false, false);
      const r = await readLocal(appid, slot.id === "icon" && shortcut ? "icon" : "art", pick.realpath ?? pick.path);
      if (!r.ok) throw new Error(r.error);
      if (slot.id === "icon" && shortcut) setShortcutIcon(appid, r.path!);
      else await setArt(appid, r.data!, r.ext!, slot.asset);
      setApplied(await markApplied(appid, slot.id, null));
      toast(`${slot.title} set from file`);
    } catch (e: any) {
      if (e && String(e).toLowerCase().includes("cancel")) return;
      toast(`Couldn't use that file: ${e?.message ?? e}`);
    } finally {
      if (alive.current) setBusy(null);
    }
  };

  const styleSel = settings.styles[slot.kind]?.[0] ?? "";
  const changeFilter = async (patch: Partial<Settings>) => {
    onSettings(await setOptions(patch));
  };

  const contain = slot.id === "logo" || slot.id === "icon";
  const cur = applied[slot.id];
  const canAnimate = slot.kind !== "icons";

  return (
    <div style={{ padding: "0 24px" }}>
      <Focusable className="ga-bar" flow-children="row">
        <DialogButton className="ga-btn" onClick={onSearch}>Search…</DialogButton>
        <span className="lbl" style={{ marginLeft: "6px" }}>Style</span>
        <div style={{ minWidth: "170px" }}>
          <Dropdown selectedOption={styleSel}
            rgOptions={[{ data: "", label: "Any" }, ...STYLES[slot.kind].map((x) => ({ data: x, label: STYLE_NAMES[x] ?? x }))]}
            onChange={(o) => changeFilter({ styles: { ...settings.styles, [slot.kind]: o.data ? [o.data] : [] } })} />
        </div>
        {canAnimate && <>
          <span className="lbl" style={{ marginLeft: "10px" }}>Animated</span>
          <Toggle value={settings.animated} onChange={(v) => changeFilter({ animated: v })} />
        </>}
        <div style={{ flex: 1 }} />
        <DialogButton className="ga-btn" disabled={busy !== null} onClick={fromFile}>
          {busy === "file" ? "Opening…" : "From file"}
        </DialogButton>
        <DialogButton className="ga-btn" disabled={busy !== null} onClick={reset}>
          {busy === "reset" ? "Resetting…" : "Reset to Steam's"}
        </DialogButton>
      </Focusable>
      {error && <div className="ga-msg err">{error}</div>}
      {data && data.items.length === 0 && !loading && !error &&
        <div className="ga-msg">Nothing on SteamGridDB for this with the current filters. Try Style: Any{canAnimate && settings.animated ? " or turn Animated off" : ""}, or Search under another name.</div>}
      {data && data.items.length > 0 && (
        <Focusable className="ga-grid" style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${slot.min}px, 1fr))` }}>
          {data.items.map((a) => (
            <Focusable key={a.id} className={`ga-tile${contain ? " contain" : ""}`} focusClassName="ga-focus"
              style={{ aspectRatio: slot.ratio }} onActivate={() => apply(a)} onClick={() => apply(a)}
              onOKActionDescription={`Set ${slot.title.toLowerCase()}`}
              onSecondaryButton={onSearch} onSecondaryActionDescription="Search">
              <Thumb a={a} />
              {cur === a.id && <div className="mark">SET</div>}
              <div className="meta">{[a.game && names.get(a.game), STYLE_NAMES[a.style] ?? a.style, a.width && `${a.width}×${a.height}`, a.author && `by ${a.author}`].filter(Boolean).join("  ·  ")}</div>
              {busy === a.id && <div className="busy">APPLYING…</div>}
            </Focusable>
          ))}
        </Focusable>
      )}
      {loading && <div style={{ height: "80px" }}><SteamSpinner background="transparent" /></div>}
      {data && data.more && !loading && (
        <Focusable style={{ display: "flex", justifyContent: "center", paddingBottom: "32px" }}>
          <DialogButton className="ga-btn" onClick={() => load(data.page + 1)}>More</DialogButton>
        </Focusable>
      )}
    </div>
  );
}

/**
 * Which SteamGridDB game the browser shows. Steam games are looked up by app id unless the user
 * picked another game with Search; non-Steam shortcuts have no Steam app id, so they are matched
 * by name (first hit) until the user picks one. A pick is saved per app in the settings file.
 */
function useMatch(appid: number, name: string, shortcut: boolean, hasKey: boolean) {
  const [match, setM] = useState(() => state.matched.get(appid) ?? null);
  const [ready, setReady] = useState(() => state.matched.has(appid));
  const [error, setError] = useState<string | null>(null);
  const live = useRef(true);
  useEffect(() => () => { live.current = false; }, []);

  const put = (m: (Match & { custom: boolean }) | null) => {
    state.matched.set(appid, m);
    if (live.current) { setM(m); setReady(true); }
  };
  const auto = async () => {
    if (!shortcut) return put(null);
    setError(null);
    const r = await searchGames(name);
    if (!live.current) return;
    if (!r.ok) { state.matched.delete(appid); setM(null); setError(r.error); setReady(true); return; }
    if (r.games[0]) put({ id: r.games[0].id, name: r.games[0].name, custom: false });
    else { state.matched.delete(appid); setM(null); setReady(true); setError(`SteamGridDB has nothing called “${name}”.`); }
  };

  useEffect(() => {
    if (!hasKey || state.matched.has(appid)) return;
    getMatch(appid)
      .then((m) => (m ? put({ ...m, custom: true }) : auto()))
      .catch((e) => { if (live.current) { setError(String(e)); setReady(true); } });
  }, [appid, hasKey]);

  const choose = async (m: Match | null) => {
    try {
      await setMatch(appid, m);
    } catch (e: any) {
      toast(`Couldn't save the search: ${e?.message ?? e}`);
    }
    if (m) put({ ...m, custom: true });
    else { setReady(false); await auto().catch((e) => live.current && setError(String(e))); }
  };
  return { match, ready, error, choose };
}

export function ArtPage() {
  const params = useParams<{ appid: string }>();
  const appid = Number(params.appid);
  const app = useMemo(() => appInfo(appid), [appid]);
  const [settings, setSettings] = useState<Settings | null>(state.settings);
  const [applied, setApplied] = useState<Partial<Record<string, number>>>({});
  const [tab, setTab] = useState<string>("capsule");
  const sc = useMatch(appid, app?.name ?? "", !!app?.shortcut, !!settings?.hasKey);

  useEffect(() => {
    getSettings().then((s) => { state.settings = s; setSettings(s); }).catch(() => {});
    getApplied(appid).then(setApplied).catch(() => {});
  }, [appid]);

  const onSettings = (s: Settings) => { state.settings = s; setSettings(s); };
  const slots = SLOTS;
  const m = sc.match;
  const gameIds = m ? m.ids ?? [m.id] : [];
  const names = useMemo(() => new Map(gameIds.map((id, i) => [id, m?.names?.[i] ?? ""] as [number, string])), [gameIds.join(",")]);
  const openSearch = () => showModal(
    <SearchModal start={m?.custom ? m.name : app?.name ?? ""} current={m && !m.term ? m.id : 0}
      auto={app?.shortcut ? "Match by name again" : "Use Steam's own"} onPick={sc.choose} />);

  let body: ReactNode;
  if (!app) body = <div className="ga-msg err" style={{ padding: "24px" }}>Steam doesn't know app {params.appid}.</div>;
  else if (!settings) body = <SteamSpinner background="transparent" />;
  else if (!settings.hasKey) body = (
    <div className="ga-msg" style={{ padding: "24px" }}>
      Add your free SteamGridDB API key first: Quick Access → Grid Art → API key.
      <div style={{ marginTop: "16px" }}><DialogButton className="ga-btn" onClick={() => Navigation.NavigateBack()}>Back</DialogButton></div>
    </div>);
  else if (!sc.ready || (app.shortcut && !sc.match)) body = (
    <div className="ga-msg" style={{ padding: "24px" }}>
      {sc.error ?? (app.shortcut ? "Looking this shortcut up on SteamGridDB…" : <SteamSpinner background="transparent" />)}
      {sc.error && <Focusable style={{ marginTop: "16px", display: "flex" }}>
        <DialogButton className="ga-btn" onClick={openSearch}>Search under another name…</DialogButton>
      </Focusable>}
    </div>);
  else body = (
    <div className="ga-tabs">
      <Tabs activeTab={tab} onShowTab={setTab} autoFocusContents
        tabs={slots.map((s) => ({
          id: s.id, title: s.title,
          content: <SlotTab key={`${s.id}:${gameIds.join(",")}`} appid={appid} gameIds={gameIds} names={names} slot={s} settings={settings} onSettings={onSettings}
            applied={applied} setApplied={setApplied} shortcut={app.shortcut} onSearch={openSearch} />,
        }))} />
    </div>);

  return (
    <div className="ga-page">
      <style>{PAGE_CSS}</style>
      <div className="ga-inner">
        <div className="ga-head">
          <span className="t">{app?.name ?? "Unknown app"}</span>
          <span className="s">Artwork</span>
          {sc.match && (sc.match.custom || sc.match.name !== app?.name) &&
            <span className="as">{sc.match.term ? "search" : "as"} <b>{sc.match.term ? `“${sc.match.name}”` : sc.match.name}</b>{sc.match.custom ? "" : " (auto)"}</span>}
          <span className="tag" style={{ color: C.data }}>STEAMGRIDDB</span>
        </div>
        {body}
      </div>
    </div>
  );
}
