/*
 * Full-screen library: /itch-library
 * L1/R1 switch tabs (Browse, All, Installed, Updates). A opens a game, X installs or plays it straight
 * from the grid. The owned-games list comes from a cache refreshed at most every 30 minutes.
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

export const LIBRARY_ROUTE = "/itch-library";
export const GAME_ROUTE = "/itch-library/game/:id";
export const gamePath = (id: number) => `/itch-library/game/${id}`;

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
    <Focusable className="il-tile" focusClassName="il-focus"
      onActivate={() => Navigation.Navigate(gamePath(g.id))} onClick={() => Navigation.Navigate(gamePath(g.id))}
      onOKActionDescription="Details" onSecondaryButton={xLabel ? secondary : undefined} onSecondaryActionDescription={xLabel}>
      <div className="art">
        {g.still || g.cover ? <img src={g.still || g.cover} loading="lazy" decoding="async" draggable={false} /> : <div className="none">{g.title}</div>}
        {job ? <div className="badge dl">{job.phase === "downloading" && job.total ? `${Math.floor(pct * 100)}%` : job.phase.toUpperCase()}</div>
          : rec?.update ? <div className="badge upd">UPDATE</div>
            : rec ? <div className="badge">INSTALLED</div> : null}
        {job && <div className="prog"><Bar value={job.phase === "downloading" ? pct : 1} color={job.phase === "downloading" ? C.data : C.active} /></div>}
      </div>
      <div className="name">{g.title}</div>
      <div className="sub">{job ? jobLine(job) : <><Plats list={g.platforms} />{g.author && <span style={{ marginLeft: 4 }}>{g.author}</span>}</>}</div>
    </Focusable>
  );
}

function Grid({ games, empty }: { games: Game[]; empty: ReactNode }) {
  const s = state;
  if (!games.length) return <div className="il-msg">{empty}</div>;
  return (
    <Focusable className="il-grid">
      {games.map((g) => <Tile key={g.id} g={g} rec={s.installed[String(g.id)]} />)}
    </Focusable>
  );
}

export function LibraryPage() {
  const s = useStore();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [setErr, setSetErr] = useState<string | null>(null);
  const start = async () => {
    setSetErr(null);
    let set = s.settings;
    if (!set) {
      try { set = await loadSettings(); }
      catch (e) { setSetErr(e instanceof Error ? e.message : String(e)); return; }
    }
    if (set?.signedIn) setError(await loadLibrary(false));
  };
  useEffect(() => { start(); }, []);

  const refresh = async () => { setBusy(true); setError(await loadLibrary(true)); setBusy(false); };

  let body: ReactNode;
  if (!s.settings) body = setErr
    ? <Focusable className="il-msg err" style={{ display: "flex", flexDirection: "column", gap: 10, alignItems: "flex-start" }}>
        <div>{setErr}</div>
        <DialogButton className="il-btn" style={{ width: "auto" }} onClick={start}>Retry</DialogButton>
      </Focusable>
    : <SteamSpinner background="transparent" />;
  else if (!s.settings.signedIn) body = <SignIn />;
  else if (!s.games) body = error ? <div className="il-msg err">{error}</div> : <SteamSpinner background="transparent" />;
  else {
    const all = [...s.games].sort(s.sort === "title" ? (a, b) => a.title.localeCompare(b.title) : () => 0);
    const byId = new Map(s.games.map((g) => [g.id, g]));
    // Installed games no longer in the owned list (e.g. a revoked key) still show up here.
    const installedGames: Game[] = Object.values(s.installed).map((r) => byId.get(r.game_id) ?? {
      id: r.game_id, title: r.title, short: "", url: r.url, cover: r.cover, still: r.cover, classification: "", author: "", platforms: [r.kind], key: 0,
    }).sort((a, b) => a.title.localeCompare(b.title));
    const updates = installedGames.filter((g) => s.installed[String(g.id)]?.update);
    const queued = s.jobs.map((j) => byId.get(j.game_id)).filter(Boolean) as Game[];
    const bar = (
      <Focusable className="il-bar" flow-children="row" style={{ padding: "0 24px 10px" }}>
        <span className="lbl">Sort</span>
        <div style={{ minWidth: 180 }}>
          <Dropdown selectedOption={s.sort} rgOptions={[{ data: "added", label: "Recently added" }, { data: "title", label: "A–Z" }]}
            onChange={(o) => { s.sort = o.data; changed(); }} />
        </div>
        <div style={{ flex: 1 }} />
        <DialogButton className="il-btn" disabled={busy} onClick={refresh}>{busy ? "Refreshing…" : "Refresh"}</DialogButton>
        <DialogButton className="il-btn" disabled={s.checking} onClick={() => checkUpdates(true)}>{s.checking ? "Checking…" : "Check for updates"}</DialogButton>
      </Focusable>
    );
    const tabs = [
      { id: "browse", title: "Browse", content: <BrowseTab /> },
      { id: "all", title: `All · ${all.length}`, content: <>{bar}<Grid games={all} empty="Nothing here yet. Games you buy or claim on itch.io show up after Refresh." /></> },
      { id: "installed", title: `Installed · ${installedGames.length}`, content: <>{bar}<Grid games={installedGames} empty="No itch.io games installed yet. Pick one in All and press Install." /></> },
      { id: "updates", title: `Updates · ${updates.length}`, content: <>{bar}<Grid games={updates} empty={s.checking ? "Checking…" : "Everything is up to date."} /></> },
    ];
    if (queued.length) tabs.push({ id: "downloads", title: `Downloads · ${queued.length}`, content: <><div style={{ height: 8 }} /><Grid games={queued} empty="" /></> });
    body = (
      <div className="il-tabs">
        {error && <div className="il-msg err" style={{ paddingTop: 0 }}>{error}</div>}
        <Tabs activeTab={tabs.some((t) => t.id === s.tab) ? s.tab : "all"} onShowTab={(t: string) => { s.tab = t; }} autoFocusContents tabs={tabs} />
      </div>
    );
  }

  const user = s.settings?.user;
  const upd = updateCount();
  return (
    <div className="il-page">
      <style>{PAGE_CSS}</style>
      <div className="il-inner">
        <div className="il-head">
          <span className="t">Itch Library</span>
          {s.settings?.signedIn && <span className="s">{user?.name || user?.username}</span>}
          <span className="grow" />
          {upd > 0 && <span className="tag" style={{ color: C.accent, borderColor: C.accent }}>{upd} UPDATE{upd > 1 ? "S" : ""}</span>}
          <span className="tag">ITCH.IO</span>
        </div>
        {body}
      </div>
    </div>
  );
}
