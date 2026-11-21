/*
 * Full-screen library: /epic-library
 * L1/R1 switch tabs (Browse, Library, Installed, Updates, Downloads). A opens a game, X installs or
 * plays it straight from the grid. The owned-games list comes from a cache refreshed at most every
 * 30 minutes (or with Refresh).
 */
import { DialogButton, Dropdown, Focusable, Navigation, SteamSpinner, Tabs } from "@decky/ui";
import { ReactNode, useEffect, useState } from "react";
import { checkUpdates, loadLibrary, loadSettings, startInstall } from "./actions";
import { Game, Installed } from "./backend";
import { gamePath } from "./routes";
import { SignIn } from "./signin";
import { BrowseTab } from "./store";
import { changed, jobFor, jobLine, sized, state, updateCount, useStore } from "./state";
import { openInSteam, shortcutExists } from "./steam";
import { Bar, C, Chip, PAGE_CSS } from "./ui";


function Tile({ g, rec }: { g: Game; rec?: Installed }) {
  const job = jobFor(g.app);
  const canPlay = rec && rec.appid && shortcutExists(rec.appid) && rec.present;
  const secondary = () => {
    if (job) return;
    if (canPlay && !rec!.update) openInSteam(rec!.appid);
    else if (g.installable || rec) startInstall(g.app);
  };
  const xLabel = job ? undefined : canPlay && !rec!.update ? "Play" : rec?.update ? "Update" : (g.installable && !rec) ? "Install" : undefined;
  const pct = job && job.total ? job.done / job.total : 0;
  const open = () => Navigation.Navigate(gamePath(g.app));
  return (
    <Focusable className="ep-tile" focusClassName="ep-focus" onActivate={open} onClick={open}
      onOKActionDescription="Details" onSecondaryButton={xLabel ? secondary : undefined} onSecondaryActionDescription={xLabel}>
      <div className="art">
        {g.tall || g.wide ? <img src={sized(g.tall || g.wide, 300, 400)} loading="lazy" decoding="async" draggable={false} /> : <div className="none">{g.title}</div>}
        {job ? <div className="badge dl">{job.phase === "downloading" && job.total ? `${Math.floor(pct * 100)}%` : job.phase.toUpperCase()}</div>
          : rec?.update ? <div className="badge upd">UPDATE</div>
            : rec ? <div className="badge">INSTALLED</div>
              : g.third_party ? <div className="badge off">{g.third_party.toUpperCase().slice(0, 14)}</div> : null}
        {job && <div className="prog"><Bar value={job.phase === "downloading" ? pct : 1} color={job.phase === "downloading" ? C.data : C.active} /></div>}
      </div>
      <div className="name">{g.title}</div>
      <div className="sub">{job ? jobLine(job) : <>{rec ? <Chip color={C.ok}>{rec.size ? `${(rec.size / 1024 ** 3).toFixed(1)} GB` : "READY"}</Chip> : null}
        {g.developer && <span style={{ marginLeft: rec ? 4 : 0 }}>{g.developer}</span>}</>}</div>
    </Focusable>
  );
}

function Grid({ games, empty }: { games: Game[]; empty: ReactNode }) {
  if (!games.length) return <div className="ep-msg">{empty}</div>;
  return (
    <Focusable className="ep-grid">
      {games.map((g) => <Tile key={g.app} g={g} rec={state.installed[g.app]} />)}
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
  else if (s.settings.problem) body = <div className="ep-msg err">{s.settings.problem}</div>;
  else if (!s.settings.signedIn) body = <SignIn />;
  else if (!s.games) body = error ? <div className="ep-msg err">{error}</div> : (
    <div><SteamSpinner background="transparent" /><div className="ep-msg" style={{ textAlign: "center" }}>
      Fetching your Epic library. The first time can take a minute for large libraries.</div></div>
  );
  else {
    const byApp = new Map(s.games.map((g) => [g.app, g]));
    const sorted = [...s.games].sort(
      s.sort === "installed" ? (a, b) => (s.installed[b.app] ? 1 : 0) - (s.installed[a.app] ? 1 : 0) || a.title.localeCompare(b.title)
        : s.sort === "size" ? (a, b) => (s.installed[b.app]?.size ?? 0) - (s.installed[a.app]?.size ?? 0) || a.title.localeCompare(b.title)
          : (a, b) => a.title.localeCompare(b.title));
    // Installed games no longer in the owned list (refunded, or a stale cache) still show up here.
    const installedGames: Game[] = Object.values(s.installed).map((r) => byApp.get(r.app) ?? {
      app: r.app, title: r.title, ns: "", catalog: "", tall: "", wide: "", logo: "", developer: "", description: "",
      version: r.latest, installable: true, third_party: "", dlcs: 0, cloud_saves: false,
    }).sort((a, b) => a.title.localeCompare(b.title));
    const updates = installedGames.filter((g) => s.installed[g.app]?.update);
    const queued = s.jobs.map((j) => byApp.get(j.app) ?? installedGames.find((g) => g.app === j.app)).filter(Boolean) as Game[];
    const bar = (
      <Focusable className="ep-bar" flow-children="row" style={{ padding: "0 24px 10px" }}>
        <span className="lbl">Sort</span>
        <div style={{ minWidth: 180 }}>
          <Dropdown selectedOption={s.sort} rgOptions={[{ data: "title", label: "A–Z" }, { data: "installed", label: "Installed first" }, { data: "size", label: "Largest installs" }]}
            onChange={(o) => { s.sort = o.data; changed(); }} />
        </div>
        <div style={{ flex: 1 }} />
        <DialogButton className="ep-btn" disabled={busy} onClick={refresh}>{busy ? "Refreshing…" : "Refresh"}</DialogButton>
        <DialogButton className="ep-btn" disabled={s.checking} onClick={() => checkUpdates(true)}>{s.checking ? "Checking…" : "Check for updates"}</DialogButton>
      </Focusable>
    );
    const tabs = [
      { id: "browse", title: "Browse", content: <BrowseTab /> },
      { id: "all", title: `Library · ${sorted.length}`, content: <>{bar}<Grid games={sorted} empty="Nothing here yet. Games you buy or claim on the Epic Games Store show up after Refresh." /></> },
      { id: "installed", title: `Installed · ${installedGames.length}`, content: <>{bar}<Grid games={installedGames} empty="No Epic games installed yet. Pick one in Library and press Install." /></> },
      { id: "updates", title: `Updates · ${updates.length}`, content: <>{bar}<Grid games={updates} empty={s.checking ? "Checking…" : "Everything is up to date."} /></> },
    ];
    if (queued.length) tabs.push({ id: "downloads", title: `Downloads · ${queued.length}`, content: <><div style={{ height: 8 }} /><Grid games={queued} empty="" /></> });
    body = (
      <div className="ep-tabs">
        {error && <div className="ep-msg err" style={{ paddingTop: 0 }}>{error}</div>}
        <Tabs activeTab={tabs.some((t) => t.id === s.tab) ? s.tab : "all"} onShowTab={(t: string) => { s.tab = t; }} autoFocusContents tabs={tabs} />
      </div>
    );
  }

  const user = s.settings?.user;
  const upd = updateCount();
  return (
    <div className="ep-page">
      <style>{PAGE_CSS}</style>
      <div className="ep-inner">
        <div className="ep-head">
          <span className="t">Epic Library</span>
          {s.settings?.signedIn && <span className="s">{user?.name}</span>}
          <span className="grow" />
          {upd > 0 && <span className="tag" style={{ color: C.accent, borderColor: C.accent }}>{upd} UPDATE{upd > 1 ? "S" : ""}</span>}
          <span className="tag">EPIC GAMES</span>
        </div>
        {body}
      </div>
    </div>
  );
}
