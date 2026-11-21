/*
 * Browse tab: discover games on itch.io. Filters are itch.io's own (sort, price, genre, controller
 * support, platform); controller support defaults to Gamepad. Search uses the on-screen keyboard.
 * A opens a game, X installs a free one straight away.
 */
import { DialogButton, Dropdown, Focusable, Navigation, SteamSpinner, TextField } from "@decky/ui";
import { useEffect, useState } from "react";
import { startInstall } from "./actions";
import * as be from "./backend";
import { changed, state, useStore } from "./state";
import { toast } from "./steam";
import { Plats } from "./ui";

const gamePath = (id: number) => `/itch-library/game/${id}`;

const SORTS = [["", "Popular"], ["new-and-popular", "New & popular"], ["top-sellers", "Top sellers"], ["top-rated", "Top rated"], ["newest", "Newest"]];
const PRICES = [["", "Any price"], ["free", "Free"], ["on-sale", "On sale"], ["5-dollars-or-less", "$5 or less"], ["15-dollars-or-less", "$15 or less"]];
const GENRES = [["", "Any genre"], ["action", "Action"], ["adventure", "Adventure"], ["card-game", "Card game"], ["educational", "Educational"],
  ["fighting", "Fighting"], ["interactive-fiction", "Interactive fiction"], ["platformer", "Platformer"], ["puzzle", "Puzzle"], ["racing", "Racing"],
  ["rhythm", "Rhythm"], ["role-playing", "Role playing"], ["shooter", "Shooter"], ["simulation", "Simulation"], ["sports", "Sports"],
  ["strategy", "Strategy"], ["survival", "Survival"], ["visual-novel", "Visual novel"], ["other", "Other"]];
const INPUTS = [["gamepad", "Controller: any gamepad"], ["x360", "Controller: Xbox"], ["", "All games (any input)"]];
const PLATS = [["", "Linux or Windows"], ["linux", "Linux native"], ["windows", "Windows (Proton)"]];
const opts = (l: string[][]) => l.map(([data, label]) => ({ data, label }));

function keyOf() {
  const st = state.store;
  return st.query ? `q:${st.query}` : JSON.stringify({ ...st.opts, page: 0 });
}

async function load(page: number) {
  const st = state.store;
  const key = keyOf();
  const r = st.query ? await be.search(st.query, page) : await be.browse({ ...st.opts, page });
  if (keyOf() !== key) return null;   // filters changed meanwhile
  if (!r.ok) return r.error;
  st.items = page > 1 ? [...(st.items ?? []), ...r.items.filter((i) => !(st.items ?? []).some((x) => x.url === i.url))] : r.items;
  st.opts.page = page;
  st.more = r.more;
  st.key = key;
  changed();
  return null;
}

async function idFor(it: be.StoreItem): Promise<number | null> {
  if (it.id) return it.id;
  const hit = state.resolved.get(it.url);
  if (hit) return hit;
  const r = await be.resolve(it.url);
  if (!r.ok) { toast(`Couldn't open ${it.title}: ${r.error}`); return null; }
  state.resolved.set(it.url, r.id);
  return r.id;
}

function StoreTile({ it }: { it: be.StoreItem }) {
  const s = state;
  const id = it.id ?? s.resolved.get(it.url);
  const rec = id ? s.installed[String(id)] : undefined;
  const owned = id ? !!s.games?.some((g) => g.id === id) : false;
  const open = async () => { const gid = await idFor(it); if (gid) Navigation.Navigate(gamePath(gid)); };
  const quick = async () => {
    const gid = await idFor(it);
    if (!gid) return;
    const g = await be.getGame(gid);   // loads its store details, which install needs
    if (!g.ok) { toast(`${it.title}: ${g.error}`); return; }
    if (!g.best) { toast(`${it.title} has no Linux or Windows build to install`); return; }
    await startInstall(gid, g.best);
    toast(`Downloading ${it.title}`);
  };
  const badge = rec ? "INSTALLED" : owned ? "OWNED" : it.free ? "FREE" : it.price ? it.price.toUpperCase() : "";
  return (
    <Focusable className="il-tile" focusClassName="il-focus" onActivate={open} onClick={open} onOKActionDescription="Details"
      onSecondaryButton={it.free && !rec ? quick : undefined} onSecondaryActionDescription={it.free && !rec ? "Get" : undefined}>
      <div className="art">
        {it.cover || it.still ? <img src={it.still || it.cover} loading="lazy" decoding="async" draggable={false} /> : <div className="none">{it.title}</div>}
        {badge && <div className={`badge${rec || owned ? "" : it.free ? " dl" : " upd"}`}>{badge}</div>}
      </div>
      <div className="name">{it.title}</div>
      <div className="sub"><Plats list={it.platforms} />{it.author && <span style={{ marginLeft: 4 }}>{it.author}</span>}
        {it.sale && <span style={{ marginLeft: 4, color: "var(--ng-accent, #F3E600)" }}>-{it.sale}%</span>}</div>
    </Focusable>
  );
}

export function BrowseTab() {
  const s = useStore();
  const st = s.store;
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState(st.query);

  const run = async (page: number) => {
    setLoading(true); setError(null);
    try { setError(await load(page)); } catch (e) { setError(String(e)); } finally { setLoading(false); }
  };
  useEffect(() => { if (st.key !== keyOf() || !st.items) run(1); }, []);

  const setOpt = (k: keyof be.BrowseOpts, v: string) => {
    (st.opts as any)[k] = v;
    st.query = ""; setDraft("");
    st.items = null; changed(); run(1);
  };
  const doSearch = () => {
    const q = draft.trim();
    if (q === st.query) return;
    st.query = q; st.items = null; changed(); run(1);
  };

  return (
    <div>
      <Focusable className="il-bar" flow-children="row" style={{ padding: "0 24px 6px" }}>
        <div style={{ flex: "1 1 260px", minWidth: 220 }}>
          <TextField label="Search itch.io" value={draft} onChange={(e) => setDraft(e.target.value)}
            onBlur={doSearch} onKeyDown={(e) => { if (e.key === "Enter") doSearch(); }} bShowClearAction />
        </div>
        <DialogButton className="il-btn" onClick={doSearch}>Search</DialogButton>
        {st.query && <DialogButton className="il-btn" onClick={() => { setDraft(""); st.query = ""; st.items = null; changed(); run(1); }}>Clear</DialogButton>}
      </Focusable>
      {!st.query && (
        <Focusable className="il-bar" flow-children="row" style={{ padding: "0 24px 10px" }}>
          {([["sort", SORTS, 150], ["price", PRICES, 140], ["genre", GENRES, 170], ["controller", INPUTS, 230], ["platform", PLATS, 180]] as [keyof be.BrowseOpts, string[][], number][])
            .map(([k, list, w]) => (
              <div key={k} style={{ minWidth: w }}>
                <Dropdown selectedOption={(st.opts as any)[k]} rgOptions={opts(list)} onChange={(o) => setOpt(k, o.data)} />
              </div>
            ))}
        </Focusable>
      )}
      {st.query && <div className="il-msg" style={{ padding: "0 24px 10px" }}>
        Search results for “{st.query}”. Filters and controller support apply to browsing only.</div>}
      {error && <div className="il-msg err" style={{ paddingTop: 0 }}>{error}</div>}
      {st.items && st.items.length === 0 && !loading && !error && <div className="il-msg">Nothing matches. Try fewer filters.</div>}
      {st.items && st.items.length > 0 && (
        <Focusable className="il-grid">{st.items.map((it) => <StoreTile key={it.url || it.id} it={it} />)}</Focusable>
      )}
      {loading && <div style={{ height: 80 }}><SteamSpinner background="transparent" /></div>}
      {st.items && st.more && !loading && (
        <Focusable style={{ display: "flex", justifyContent: "center", paddingBottom: 32 }}>
          <DialogButton className="il-btn" onClick={() => run(st.opts.page + 1)}>More</DialogButton>
        </Focusable>
      )}
    </div>
  );
}
