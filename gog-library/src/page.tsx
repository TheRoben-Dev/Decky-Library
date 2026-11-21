/*
 * Full-screen library: /gog-library
 * L1/R1 switch tabs (Browse, Library, Installed, Updates, Downloads). A opens a game, X installs or
 * plays it straight from the grid. The owned-games list comes from a cache refreshed at most every
 * 30 minutes.
 */
import { DialogButton, Dropdown, Focusable, Navigation, SteamSpinner, Tabs } from "@decky/ui";
import { ReactNode, useEffect, useState } from "react";
import { checkUpdates, loadLibrary, loadSettings, startInstall } from "./actions";
import { Game, Installed } from "./backend";
import { SignIn } from "./signin";
import { BrowseTab } from "./store";
import { changed, jobFor, jobLine, state, updateCount, useStore } from "./state";
import { openInSteam, shortcutExists } from "./steam";
import { Bar, C, PAGE_CSS, Plats } from "./ui";

export const LIBRARY_ROUTE = "/gog-library";
export const GAME_ROUTE = "/gog-library/game/:id";
export const gamePath = (id: number) => `/gog-library/game/${id}`;

// GOG's library sometimes reports no platforms at all for a game; let the install find out.
const playable = (g: Game) => g.platforms.includes("linux") || g.platforms.includes("windows") || g.platforms.length === 0;

function Tile({ g, rec }: { g: Game; rec?: Installed }) {
  const job = jobFor(g.id);
  const canPlay = rec && rec.appid && shortcutExists(rec.appid);
  const secondary = () => {
    if (job) return;
    if (canPlay && !rec!.update) openInSteam(rec!.appid);
    else if (playable(g)) startInstall(g.id);
  };
  const xLabel = job ? undefined : canPlay && !rec!.update ? "Play" : rec?.update ? "Update" : playable(g) ? "Install" : undefined;
  const pct = job && job.total ? job.done / job.total : 0;
  return (
    <Focusable className="gl-tile" focusClassName="gl-focus"
      onActivate={() => Navigation.Navigate(gamePath(g.id))} onClick={() => Navigation.Navigate(gamePath(g.id))}
      onOKActionDescription="Details" onSecondaryButton={xLabel ? secondary : undefined} onSecondaryActionDescription={xLabel}>
      <div className="art">
        {g.cover ? <img src={g.cover} loading="lazy" decoding="async" draggable={false} /> : <div className="none">{g.title}</div>}
        {job ? <div className="badge dl">{job.phase === "downloading" && job.total ? `${Math.floor(pct * 100)}%` : job.phase.toUpperCase()}</div>
          : rec?.update ? <div className="badge upd">UPDATE</div>
            : rec ? <div className="badge">INSTALLED</div> : null}
        {job && <div className="prog"><Bar value={job.phase === "downloading" ? pct : 1} color={job.phase === "downloading" ? C.data : C.active} /></div>}
      </div>
      <div className="name">{g.title}</div>
      <div className="sub">{job ? jobLine(job) : <Plats list={g.platforms} />}</div>
    </Focusable>
  );
}

function Grid({ games, empty }: { games: Game[]; empty: ReactNode }) {
  const s = state;
  if (!games.length) return <div className="gl-msg">{empty}</div>;
  return (
    <Focusable className="gl-grid">
      {games.map((g) => <Tile key={g.id} g={g} rec={s.installed[String(g.id)]} />)}
    </Focusable>
  );
}

export function LibraryPage() {
  const s = useStore();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      const set = s.settings ?? await loadSettings().catch(() => null);
      if (set?.signedIn) setError(await loadLibrary(false));
    })();
  }, []);

  const refresh = async () => { setBusy(true); setError(await loadLibrary(true)); setBusy(false); };

  let body: ReactNode;
  if (!s.settings) body = <SteamSpinner background="transparent" />;
  else if (!s.settings.signedIn) body = <SignIn />;
  else if (!s.games) body = error ? <div className="gl-msg err">{error}</div> : <SteamSpinner background="transparent" />;
  else {
    const all = [...s.games].sort(s.sort === "title" ? (a, b) => a.title.localeCompare(b.title) : () => 0);
    const byId = new Map(s.games.map((g) => [g.id, g]));
    // Installed games no longer in the owned list (e.g. a refunded game) still show up here.
    const installedGames: Game[] = Object.values(s.installed).map((r) => byId.get(r.game_id) ?? {
      id: r.game_id, title: r.title, url: r.url, cover: r.cover, platforms: [r.kind],
    }).sort((a, b) => a.title.localeCompare(b.title));
    const updates = installedGames.filter((g) => s.installed[String(g.id)]?.update);
    const queued = s.jobs.map((j) => byId.get(j.game_id) ?? installedGames.find((g) => g.id === j.game_id) ??
      { id: j.game_id, title: j.title, url: "", cover: state.seen.get(j.game_id)?.cover ?? "", platforms: [] } as Game);
    const bar = (
      <Focusable className="gl-bar" flow-children="row" style={{ padding: "0 24px 10px" }}>
        <span className="lbl">Sort</span>
        <div style={{ minWidth: 180 }}>
          <Dropdown selectedOption={s.sort} rgOptions={[{ data: "added", label: "Recently added" }, { data: "title", label: "A–Z" }]}
            onChange={(o) => { s.sort = o.data; changed(); }} />
        </div>
        <div style={{ flex: 1 }} />
        <DialogButton className="gl-btn" disabled={busy} onClick={refresh}>{busy ? "Refreshing…" : "Refresh"}</DialogButton>
        <DialogButton className="gl-btn" disabled={s.checking} onClick={() => checkUpdates(true)}>{s.checking ? "Checking…" : "Check for updates"}</DialogButton>
      </Focusable>
    );
    const tabs = [
      { id: "browse", title: "Browse", content: <BrowseTab /> },
      { id: "all", title: `Library · ${all.length}`, content: <>{bar}<Grid games={all} empty="Nothing here yet. Games you buy or add on GOG show up after Refresh." /></> },
      { id: "installed", title: `Installed · ${installedGames.length}`, content: <>{bar}<Grid games={installedGames} empty="No GOG games installed yet. Pick one in Library and press Install." /></> },
      { id: "updates", title: `Updates · ${updates.length}`, content: <>{bar}<Grid games={updates} empty={s.checking ? "Checking…" : "Everything is up to date."} /></> },
      { id: "downloads", title: `Downloads · ${queued.length}`, content: <><div style={{ height: 8 }} /><Grid games={queued} empty="Nothing downloading. Installs and updates queue here, one at a time." /></> },
    ];
    body = (
      <div className="gl-tabs">
        {error && <div className="gl-msg err" style={{ paddingTop: 0 }}>{error}</div>}
        <Tabs activeTab={tabs.some((t) => t.id === s.tab) ? s.tab : "all"} onShowTab={(t: string) => { if (state.tab !== t) { state.tab = t; changed(); } }} autoFocusContents tabs={tabs} />
      </div>
    );
  }

  const user = s.settings?.user;
  const upd = updateCount();
  return (
    <div className="gl-page">
      <style>{PAGE_CSS}</style>
      <div className="gl-inner">
        <div className="gl-head">
          <span className="t">GOG Library</span>
          {s.settings?.signedIn && <span className="s">{user?.username}</span>}
          <span className="grow" />
          {upd > 0 && <span className="tag" style={{ color: C.accent, borderColor: C.accent }}>{upd} UPDATE{upd > 1 ? "S" : ""}</span>}
          <span className="tag">GOG</span>
        </div>
        {body}
      </div>
    </div>
  );
}
