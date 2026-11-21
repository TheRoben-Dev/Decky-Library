/*
 * Browse tab: the Epic Games Store. This week's free games on top, then search and Epic's own
 * filters (sort, price, genre, controller support). Controller support is on by default; pick
 * "All games" to see everything. Filters apply to search too. A opens a game; games you own open
 * their library page, the rest open a store page with Get/Buy (Steam browser or phone QR).
 */
import { DialogButton, Dropdown, Focusable, Navigation, SteamSpinner, TextField } from "@decky/ui";
import { useEffect, useState } from "react";
import { startInstall } from "./actions";
import * as be from "./backend";
import { gamePath, OFFER_ROUTE } from "./routes";
import { changed, country, ownedByNs, sized, state, useStore } from "./state";
import { C, Chip } from "./ui";

const SORTS = [["", "Popular"], ["new", "Newest"], ["price", "Price: low to high"], ["price-desc", "Price: high to low"], ["title", "A–Z"]];
const PRICES = [["", "Any price"], ["free", "Free"], ["sale", "On sale"]];
const opts = (l: string[][]) => l.map(([data, label]) => ({ data, label }));

function keyOf() {
  return JSON.stringify({ ...state.store.opts, page: 0 });
}

async function load(page: number) {
  const st = state.store;
  await country();
  const key = keyOf();
  const r = await be.browse({ ...st.opts, page });
  if (keyOf() !== key) return null;   // filters changed meanwhile
  if (!r.ok) return r.error;
  st.items = page > 1 ? [...(st.items ?? []), ...r.items.filter((i) => !(st.items ?? []).some((x) => x.id === i.id))] : r.items;
  st.opts.page = page;
  st.more = r.more;
  st.key = key;
  st.note = r.note;
  if (r.genres?.length) st.genres = r.genres;
  changed();
  return null;
}

export function openOffer(it: be.StoreItem) {
  const mine = ownedByNs(it.ns);
  if (mine) { Navigation.Navigate(gamePath(mine.app)); return; }
  state.offer = it;
  Navigation.Navigate(OFFER_ROUTE);
}

function StoreTile({ it, until }: { it: be.StoreItem; until?: boolean }) {
  const mine = ownedByNs(it.ns);
  const rec = mine ? state.installed[mine.app] : undefined;
  const claim = !mine && it.free && it.checkout
    ? () => { Navigation.CloseSideMenus(); Navigation.NavigateToExternalWeb(it.checkout); } : undefined;
  const quick = mine && mine.installable && !rec ? () => startInstall(mine.app) : claim;
  const badge = rec ? "INSTALLED" : mine ? "OWNED" : it.free ? "FREE" : it.sale ? `-${it.sale}%` : "";
  const open = () => openOffer(it);
  return (
    <Focusable className="ep-tile" focusClassName="ep-focus" onActivate={open} onClick={open}
      onOKActionDescription={mine ? "Details" : "Store page"}
      onSecondaryButton={quick} onSecondaryActionDescription={quick ? (claim && quick === claim ? "Claim free" : "Install") : undefined}>
      <div className="art">
        {it.tall || it.wide ? <img src={sized(it.tall || it.wide, 300, 400)} loading="lazy" decoding="async" draggable={false} /> : <div className="none">{it.title}</div>}
        {badge && <div className={`badge${rec || mine ? "" : it.free ? " dl" : " upd"}`}>{badge}</div>}
      </div>
      <div className="name">{it.title}</div>
      <div className="sub">
        {until && it.until ? <span style={{ color: C.data }}>FREE UNTIL {it.until}</span> : <>
          {it.price && <span style={{ color: it.free ? C.ok : C.text0 }}>{it.price}</span>}
          {it.sale > 0 && it.original && <s style={{ marginLeft: 4, opacity: 0.6 }}>{it.original}</s>}
          {it.controller && <span style={{ marginLeft: 4 }}><Chip color={C.data}>PAD</Chip></span>}
        </>}
      </div>
    </Focusable>
  );
}

function FreeNow() {
  const s = useStore();
  useEffect(() => {
    if (s.store.free) return;
    country().then((c) => be.freeNow(c)).then((r) => { s.store.free = r.ok ? r.items : []; changed(); }).catch(() => { s.store.free = []; changed(); });
  }, []);
  const items = s.store.free;
  if (!items?.length) return null;
  return (
    <>
      <div className="ep-h2">Free this week · X claims it (Epic checkout, nothing is charged), then it's yours to keep</div>
      <Focusable className="ep-strip" flow-children="row">{items.map((it) => <StoreTile key={`free-${it.id}`} it={it} until />)}</Focusable>
    </>
  );
}

export function BrowseTab() {
  const s = useStore();
  const st = s.store;
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState(st.opts.query);

  const run = async (page: number) => {
    setLoading(true); setError(null);
    try { setError(await load(page)); } catch (e) { setError(String(e)); } finally { setLoading(false); }
  };
  useEffect(() => { if (st.key !== keyOf() || !st.items) run(1); }, []);

  const setOpt = (k: keyof be.BrowseOpts, v: any) => {
    (st.opts as any)[k] = v;
    st.items = null; changed(); run(1);
  };
  const doSearch = () => {
    const q = draft.trim();
    if (q === st.opts.query) return;
    setOpt("query", q);
  };
  const genres = [["", "Any genre"], ...st.genres];

  return (
    <div>
      <Focusable className="ep-bar" flow-children="row" style={{ padding: "0 24px 6px" }}>
        <div style={{ flex: "1 1 260px", minWidth: 220 }}>
          <TextField label="Search the Epic Games Store" value={draft} onChange={(e) => setDraft(e.target.value)}
            onBlur={doSearch} onKeyDown={(e) => { if (e.key === "Enter") doSearch(); }} bShowClearAction />
        </div>
        <DialogButton className="ep-btn" onClick={doSearch}>Search</DialogButton>
        {st.opts.query && <DialogButton className="ep-btn" onClick={() => { setDraft(""); setOpt("query", ""); }}>Clear</DialogButton>}
      </Focusable>
      <Focusable className="ep-bar" flow-children="row" style={{ padding: "0 24px 10px" }}>
        <div style={{ minWidth: 230 }}>
          <Dropdown selectedOption={st.opts.controller ? "1" : ""} rgOptions={[{ data: "1", label: "Controller support" }, { data: "", label: "All games (any input)" }]}
            onChange={(o) => setOpt("controller", !!o.data)} />
        </div>
        <div style={{ minWidth: 170 }}><Dropdown selectedOption={st.opts.sort} rgOptions={opts(SORTS)} onChange={(o) => setOpt("sort", o.data)} /></div>
        <div style={{ minWidth: 130 }}><Dropdown selectedOption={st.opts.price} rgOptions={opts(PRICES)} onChange={(o) => setOpt("price", o.data)} /></div>
        {genres.length > 1 && <div style={{ minWidth: 160 }}><Dropdown selectedOption={st.opts.genre} rgOptions={opts(genres)} onChange={(o) => setOpt("genre", o.data)} /></div>}
      </Focusable>
      {!st.opts.query && <FreeNow />}
      {st.opts.query && <div className="ep-h2">Results for “{st.opts.query}”</div>}
      {st.note && <div className="ep-msg" style={{ padding: "0 24px 10px", color: C.warn }}>{st.note}</div>}
      {error && <div className="ep-msg err" style={{ paddingTop: 0 }}>{error}</div>}
      {st.items && st.items.length === 0 && !loading && !error && <div className="ep-msg">Nothing matches. Try fewer filters.</div>}
      {st.items && st.items.length > 0 && (
        <Focusable className="ep-grid">{st.items.map((it) => <StoreTile key={it.id || it.title} it={it} />)}</Focusable>
      )}
      {loading && <div style={{ height: 80 }}><SteamSpinner background="transparent" /></div>}
      {st.items && st.more && !loading && (
        <Focusable style={{ display: "flex", justifyContent: "center", paddingBottom: 32 }}>
          <DialogButton className="ep-btn" onClick={() => run(st.opts.page + 1)}>More</DialogButton>
        </Focusable>
      )}
    </div>
  );
}
