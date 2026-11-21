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
const PRICES = [["", "Any price"], ["free", "Free"], ["store", "Paid"], ["on-sale", "On sale"], ["5-dollars-or-less", "$5 or less"], ["15-dollars-or-less", "$15 or less"]];
const GENRES = [["", "Any genre"], ["action", "Action"], ["adventure", "Adventure"], ["card-game", "Card game"], ["educational", "Educational"],
  ["fighting", "Fighting"], ["interactive-fiction", "Interactive fiction"], ["platformer", "Platformer"], ["puzzle", "Puzzle"], ["racing", "Racing"],
  ["rhythm", "Rhythm"], ["role-playing", "Role playing"], ["shooter", "Shooter"], ["simulation", "Simulation"], ["sports", "Sports"],
  ["strategy", "Strategy"], ["survival", "Survival"], ["visual-novel", "Visual novel"], ["other", "Other"]];
const INPUTS = [["gamepad", "Controller: any gamepad"], ["x360", "Controller: Xbox"], ["", "All games (any input)"]];
const PLATS = [["", "Linux or Windows"], ["linux", "Linux native"], ["windows", "Windows (Proton)"]];
const RELEASED = [["", "Released: any time"], ["last-7-days", "Last 7 days"], ["last-30-days", "Last 30 days"]];
const DURATIONS = [["", "Length: any"], ["seconds", "A few seconds"], ["minutes", "A few minutes"], ["half-hour", "About a half-hour"],
  ["hour", "About an hour"], ["hours", "A few hours"], ["days", "Days or more"]];
const MULTI = [["", "Players: any"], ["local-multiplayer", "Local multiplayer"], ["multiplayer-server", "Online (server)"], ["multiplayer-adhoc", "Online (ad-hoc)"]];
const ACCESS = [["", "Accessibility: any"], ["configurable-controls", "Configurable controls"], ["subtitles", "Subtitles"],
  ["colorblind", "Color-blind support"], ["highcontrast", "High contrast"], ["blind", "Blind support"]];
const ENGINES = [["", "Made with: any"], ["godot", "Godot"], ["unity", "Unity"], ["unreal-engine", "Unreal Engine"], ["gamemaker", "GameMaker"],
  ["renpy", "Ren'Py"], ["rpg-maker", "RPG Maker"], ["pico-8", "PICO-8"], ["construct", "Construct"], ["love2d", "LÖVE"], ["pygame", "Pygame"],
  ["twine", "Twine"], ["bitsy", "Bitsy"]];
const TAGS = ["roguelike", "horror", "pixel-art", "metroidvania", "co-op", "story-rich", "singleplayer", "multiplayer", "3d", "2d",
  "retro", "cozy", "atmospheric", "exploration", "souls-like", "bullet-hell", "tower-defense", "deckbuilding", "fps", "open-world",
  "point-click", "sci-fi", "fantasy", "anime", "funny", "short", "relaxing", "difficult", "game-jam", "local-co-op"];
const ADULT_TAGS = ["adult", "nsfw", "erotic"];
const opts = (l: string[][]) => l.map(([data, label]) => ({ data, label }));
const slug = (t: string) => t.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
let debounce = 0;

function keyOf() {
  const st = state.store;
  return st.query ? `q:${st.query}` : JSON.stringify({ ...st.opts, page: 0 });
}

type Loaded = { error: string; retry: number; notice: string } | null;

async function load(page: number): Promise<Loaded> {
  const st = state.store;
  const key = keyOf();
  const r = st.query ? await be.search(st.query, page) : await be.browse({ ...st.opts, page });
  if (keyOf() !== key) return null;   // filters changed meanwhile
  if (!r.ok) return { error: r.error, retry: r.status === 429 ? r.retry_after || 60 : 0, notice: "" };
  st.items = page > 1 ? [...(st.items ?? []), ...r.items.filter((i) => !(st.items ?? []).some((x) => x.url === i.url))] : r.items;
  st.opts.page = page;
  st.more = r.more;
  st.key = key;
  changed();
  const notice = (r as { notice?: string }).notice ?? "";
  return notice ? { error: "", retry: 0, notice } : null;
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
  const adult = !!s.settings?.adult;
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [wait, setWait] = useState(0);          // seconds until itch.io accepts requests again
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState(st.query);
  const [tagDraft, setTagDraft] = useState("");

  const run = async (page: number) => {
    setLoading(true); setError(null); setNotice(null);
    try {
      const r = await load(page);
      if (r?.error) setError(r.error);
      if (r?.notice) setNotice(r.notice);
      setWait(r?.retry ?? 0);
    } catch (e) { setError(String(e)); } finally { setLoading(false); }
  };
  useEffect(() => { if (st.key !== keyOf() || !st.items) run(1); return () => window.clearTimeout(debounce); }, []);
  useEffect(() => {
    if (wait <= 0) return;
    const t = window.setTimeout(() => setWait((w) => w - 1), 1000);
    return () => window.clearTimeout(t);
  }, [wait]);

  // Filter changes are batched: flicking through dropdowns sends one request, not one per change.
  const refetch = () => {
    st.items = null; changed();
    window.clearTimeout(debounce);
    debounce = window.setTimeout(() => run(1), 700);
  };
  const setOpt = (k: keyof be.BrowseOpts, v: any) => {
    (st.opts as any)[k] = v;
    st.query = ""; setDraft("");
    refetch();
  };
  const addTag = (raw: string) => {
    const t = slug(raw);
    if (!t || st.opts.tags.includes(t) || st.opts.tags.length >= 3) return;
    if (!adult && ADULT_TAGS.includes(t)) { toast("Turn on adult content in Quick Access → Itch Library → Settings first"); return; }
    setOpt("tags", [...st.opts.tags, t]); setTagDraft("");
  };
  const clearFilters = () => {
    Object.assign(st.opts, { sort: "", price: "", genre: "", platform: "", released: "", duration: "", multiplayer: "",
      accessibility: "", engine: "", tags: [], demo: false });
    setOpt("page", 1);
  };
  const doSearch = () => {
    const q = draft.trim();
    if (q === st.query) return;
    st.query = q; st.items = null; changed(); window.clearTimeout(debounce); run(1);
  };
  const extra = ["released", "duration", "multiplayer", "accessibility", "engine"].filter((k) => (st.opts as any)[k]).length
    + st.opts.tags.length + (st.opts.demo ? 1 : 0);
  const tagChoices = [...TAGS, ...(adult ? ADULT_TAGS : [])].filter((t) => !st.opts.tags.includes(t));
  const dd = (k: keyof be.BrowseOpts, list: string[][], w: number) => (
    <div key={k} style={{ minWidth: w }}>
      <Dropdown selectedOption={(st.opts as any)[k]} rgOptions={opts(list)} onChange={(o) => setOpt(k, o.data)} />
    </div>
  );

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
        <Focusable className="il-bar" flow-children="row" style={{ padding: "0 24px 6px" }}>
          {dd("sort", SORTS, 150)}{dd("price", PRICES, 140)}{dd("genre", GENRES, 170)}{dd("controller", INPUTS, 230)}{dd("platform", PLATS, 180)}
          <DialogButton className="il-btn" onClick={() => { st.moreFilters = !st.moreFilters; changed(); }}>
            {st.moreFilters ? "Fewer filters" : extra ? `More filters · ${extra}` : "More filters"}
          </DialogButton>
        </Focusable>
      )}
      {!st.query && st.moreFilters && (
        <>
          <Focusable className="il-bar" flow-children="row" style={{ padding: "0 24px 6px" }}>
            {dd("released", RELEASED, 170)}{dd("duration", DURATIONS, 170)}{dd("multiplayer", MULTI, 180)}
            {dd("accessibility", ACCESS, 210)}{dd("engine", ENGINES, 160)}
            <DialogButton className="il-btn" onClick={() => setOpt("demo", !st.opts.demo)}>{st.opts.demo ? "✓ Has a demo" : "Has a demo"}</DialogButton>
          </Focusable>
          <Focusable className="il-bar" flow-children="row" style={{ padding: "0 24px 10px" }}>
            <span className="lbl">Tags</span>
            {st.opts.tags.map((t) => (
              <DialogButton key={t} className="il-btn" onClick={() => setOpt("tags", st.opts.tags.filter((x) => x !== t))}>{t} ✕</DialogButton>
            ))}
            {st.opts.tags.length < 3 && (
              <>
                <div style={{ minWidth: 170 }}>
                  <Dropdown selectedOption="" rgOptions={[{ data: "", label: "Add a tag" }, ...tagChoices.map((t) => ({ data: t, label: t }))]}
                    onChange={(o) => o.data && addTag(o.data)} />
                </div>
                <div style={{ minWidth: 180 }}>
                  <TextField label="Other tag" value={tagDraft} onChange={(e) => setTagDraft(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") addTag(tagDraft); }} onBlur={() => tagDraft && addTag(tagDraft)} />
                </div>
              </>
            )}
            {extra > 0 && <DialogButton className="il-btn" onClick={clearFilters}>Clear filters</DialogButton>}
          </Focusable>
        </>
      )}
      {st.query && <div className="il-msg" style={{ padding: "0 24px 10px" }}>
        Search results for “{st.query}”. Filters and controller support apply to browsing only.</div>}
      {notice && <div className="il-msg" style={{ paddingTop: 0 }}>{notice}</div>}
      {error && (
        <Focusable className="il-msg err" style={{ paddingTop: 0, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <span>{wait > 0 ? error.replace(/Try again in .*$/, `Try again in ${wait} s.`) : error}</span>
          <DialogButton className="il-btn" disabled={wait > 0 || loading} onClick={() => run(st.items?.length ? st.opts.page + 1 : 1)}>
            {wait > 0 ? `Retry in ${wait}` : "Retry"}
          </DialogButton>
        </Focusable>
      )}
      {st.items && st.items.length === 0 && !loading && !error && <div className="il-msg">Nothing matches. Try fewer filters.</div>}
      {st.items && st.items.length > 0 && (
        <Focusable className="il-grid">{st.items.map((it) => <StoreTile key={it.url || it.id} it={it} />)}</Focusable>
      )}
      {(loading || (!st.items && !error)) && <div style={{ height: 80 }}><SteamSpinner background="transparent" /></div>}
      {st.items && st.more && !loading && !error && (
        <Focusable style={{ display: "flex", justifyContent: "center", paddingBottom: 32 }}>
          <DialogButton className="il-btn" onClick={() => run(st.opts.page + 1)}>More</DialogButton>
        </Focusable>
      )}
    </div>
  );
}
