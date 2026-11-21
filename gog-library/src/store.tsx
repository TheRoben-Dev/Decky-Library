/*
 * Browse tab: the GOG store catalog. Filters are GOG's own (sort, price, genre, controller support,
 * system); controller support is on by default, with "All games" to see everything. Search uses the
 * on-screen keyboard. A opens a game; X installs a game you already own straight away.
 */
import { DialogButton, Dropdown, Focusable, Navigation, SteamSpinner, TextField } from "@decky/ui";
import { useEffect, useState } from "react";
import { startInstall } from "./actions";
import * as be from "./backend";
import { changed, state, useStore } from "./state";
import { toast } from "./steam";
import { Plats } from "./ui";

const gamePath = (id: number) => `/gog-library/game/${id}`;

const SORTS = [["", "Trending"], ["bestselling", "Bestselling"], ["newest", "Newest"], ["rating", "Top rated"], ["discount", "Biggest discount"], ["title", "A–Z"]];
const PRICES = [["", "Any price"], ["free", "Free"], ["sale", "On sale"], ["under10", "Under $10"], ["under25", "Under $25"]];
const GENRES = [["", "Any genre"], ["action", "Action"], ["adventure", "Adventure"], ["racing", "Racing"], ["rpg", "Role-playing"],
  ["shooter", "Shooter"], ["simulation", "Simulation"], ["sports", "Sports"], ["strategy", "Strategy"]];
const INPUTS = [["controller", "Controller support"], ["", "All games (any input)"]];
const PLATS = [["", "Linux or Windows"], ["linux", "Linux native"], ["windows", "Windows (Proton)"]];
const opts = (l: string[][]) => l.map(([data, label]) => ({ data, label }));

function keyOf() {
  return JSON.stringify({ ...state.store.opts, page: 0 });
}

async function load(page: number) {
  const st = state.store;
  const key = keyOf();
  const r = await be.browse({ ...st.opts, page });
  if (keyOf() !== key) return null;   // filters changed meanwhile
  if (!r.ok) return r.error;
  for (const it of r.items) state.seen.set(it.id, it);
  st.items = page > 1 ? [...(st.items ?? []), ...r.items.filter((i) => !(st.items ?? []).some((x) => x.id === i.id))] : r.items;
  st.opts.page = page;
  st.more = r.more;
  st.total = r.total;
  st.key = key;
  changed();
  return null;
}

/** What the game page needs before GOG's product API answers. */
export function hintOf(it: be.StoreItem): Partial<be.Game> {
  return { id: it.id, title: it.title, url: it.url, cover: it.cover, vertical: it.vertical, platforms: it.platforms,
    price: it.price, free: it.free, sale: it.sale, developer: it.developer };
}

function StoreTile({ it }: { it: be.StoreItem }) {
  const s = state;
  const rec = s.installed[String(it.id)];
  const owned = !!s.games?.some((g) => g.id === it.id);
  const open = () => Navigation.Navigate(gamePath(it.id));
  const quick = async () => { await startInstall(it.id); toast(`Downloading ${it.title}`); };
  const badge = rec ? "INSTALLED" : owned ? "OWNED" : it.free ? "FREE" : it.price ? it.price.toUpperCase() : "";
  return (
    <Focusable className="gl-tile" focusClassName="gl-focus" onActivate={open} onClick={open} onOKActionDescription="Details"
      onSecondaryButton={owned && !rec ? quick : undefined} onSecondaryActionDescription={owned && !rec ? "Install" : undefined}>
      <div className="art">
        {it.cover ? <img src={it.cover} loading="lazy" decoding="async" draggable={false} /> : <div className="none">{it.title}</div>}
        {badge && <div className={`badge${rec || owned ? "" : it.free ? " dl" : " upd"}`}>{badge}</div>}
      </div>
      <div className="name">{it.title}</div>
      <div className="sub"><Plats list={it.platforms} />{it.controller && <span className="gl-plat pad">PAD</span>}
        {it.developer && <span style={{ marginLeft: 4 }}>{it.developer}</span>}
        {it.sale && <span style={{ marginLeft: 4, color: "var(--ng-accent, #F3E600)" }}>{it.sale}</span>}</div>
    </Focusable>
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

  const setOpt = (k: keyof be.BrowseOpts, v: string) => {
    (st.opts as any)[k] = v;
    st.items = null; changed(); run(1);
  };
  const doSearch = () => {
    const q = draft.trim();
    if (q === st.opts.query) return;
    setOpt("query", q);
  };

  return (
    <div>
      <Focusable className="gl-bar" flow-children="row" style={{ padding: "0 24px 6px" }}>
        <div style={{ flex: "1 1 260px", minWidth: 220 }}>
          <TextField label="Search GOG" value={draft} onChange={(e) => setDraft(e.target.value)}
            onBlur={doSearch} onKeyDown={(e) => { if (e.key === "Enter") doSearch(); }} bShowClearAction />
        </div>
        <DialogButton className="gl-btn" onClick={doSearch}>Search</DialogButton>
        {st.opts.query && <DialogButton className="gl-btn" onClick={() => { setDraft(""); setOpt("query", ""); }}>Clear</DialogButton>}
      </Focusable>
      <Focusable className="gl-bar" flow-children="row" style={{ padding: "0 24px 10px" }}>
        {([["sort", SORTS, 160], ["price", PRICES, 140], ["genre", GENRES, 160], ["controller", INPUTS, 210], ["platform", PLATS, 180]] as [keyof be.BrowseOpts, string[][], number][])
          .map(([k, list, w]) => (
            <div key={k} style={{ minWidth: w }}>
              <Dropdown selectedOption={(st.opts as any)[k]} rgOptions={opts(list)} onChange={(o) => setOpt(k, o.data)} />
            </div>
          ))}
      </Focusable>
      {st.opts.query && st.items && <div className="gl-msg" style={{ padding: "0 24px 10px" }}>
        {st.total} result{st.total === 1 ? "" : "s"} for “{st.opts.query}” with these filters.</div>}
      {error && <div className="gl-msg err" style={{ paddingTop: 0 }}>{error}</div>}
      {st.items && st.items.length === 0 && !loading && !error && <div className="gl-msg">
        Nothing matches.{st.opts.controller ? " Try All games (any input): many games play fine with Steam Input even without official controller support." : " Try fewer filters."}</div>}
      {st.items && st.items.length > 0 && (
        <Focusable className="gl-grid">{st.items.map((it) => <StoreTile key={it.id} it={it} />)}</Focusable>
      )}
      {loading && <div style={{ height: 80 }}><SteamSpinner background="transparent" /></div>}
      {st.items && st.more && !loading && (
        <Focusable style={{ display: "flex", justifyContent: "center", paddingBottom: 32 }}>
          <DialogButton className="gl-btn" onClick={() => run(st.opts.page + 1)}>More</DialogButton>
        </Focusable>
      )}
    </div>
  );
}
