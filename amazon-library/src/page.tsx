/*
 * Full-screen library: /amazon-library
 * L1/R1 switch tabs (Free games, All, Installed, Updates, Downloads). A opens a game, X installs
 * or plays it straight from the grid. The games list comes from a cache refreshed at most every
 * 30 minutes.
 */
import { DialogButton, Dropdown, Focusable, Navigation, SteamSpinner, Tabs } from "@decky/ui";
import { ReactNode, useEffect, useState } from "react";
import { checkUpdates, loadLibrary, loadSettings, startInstall } from "./actions";
import { Game, Installed } from "./backend";
import { FreeTab } from "./offers";
import { SignIn } from "./signin";
import { changed, gamePath, jobFor, jobLine, state, updateCount, useStore } from "./state";
import { openInSteam, shortcutExists } from "./steam";
import { Bar, C, PAGE_CSS } from "./ui";

export const LIBRARY_ROUTE = "/amazon-library";
export const GAME_ROUTE = "/amazon-library/game/:id";

function Tile({ g, rec }: { g: Game; rec?: Installed }) {
  const job = jobFor(g.id);
  const canPlay = rec && rec.appid && shortcutExists(rec.appid);
  const secondary = () => {
    if (job) return;
    if (canPlay && !rec!.update) openInSteam(rec!.appid);
    else startInstall(g.id);
  };
  const xLabel = job ? undefined : canPlay && !rec!.update ? "Play" : rec?.update ? "Update" : rec ? undefined : "Install";
  const pct = job && job.total ? job.done / job.total : 0;
  const art = g.cover || g.icon;
  return (
    <Focusable className="al-tile" focusClassName="al-focus"
      onActivate={() => Navigation.Navigate(gamePath(g.id))} onClick={() => Navigation.Navigate(gamePath(g.id))}
      onOKActionDescription="Details" onSecondaryButton={xLabel ? secondary : undefined} onSecondaryActionDescription={xLabel}>
      <div className="art">
        {art ? <img src={art} loading="lazy" decoding="async" draggable={false} /> : <div className="none">{g.title}</div>}
        {job ? <div className="badge dl">{job.phase === "downloading" && job.total ? `${Math.floor(pct * 100)}%` : job.phase.toUpperCase()}</div>
          : rec?.update ? <div className="badge upd">UPDATE</div>
            : rec ? <div className="badge">INSTALLED</div> : null}
        {job && <div className="prog"><Bar value={job.phase === "downloading" ? pct : 1} color={job.phase === "downloading" ? C.data : C.active} /></div>}
      </div>
      <div className="name">{g.title}</div>
      <div className="sub">{job ? jobLine(job) : <span>{g.developer || g.publisher || (g.genres[0] ?? "")}</span>}</div>
    </Focusable>
  );
}

function Grid({ games, empty }: { games: Game[]; empty: ReactNode }) {
  if (!games.length) return <div className="al-msg">{empty}</div>;
  return (
    <Focusable className="al-grid">
      {games.map((g) => <Tile key={g.id} g={g} rec={state.installed[g.id]} />)}
    </Focusable>
  );
}

const fromRec = (r: Installed): Game => ({
  id: r.game_id, entitlement: r.entitlement, sku: r.sku, title: r.title, icon: r.icon, cover: r.cover, background: r.background,
  logo: r.logo, short: "", developer: "", publisher: "", genres: [], released: "", screenshot: "", added: "",
});

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
  else if (!s.games) body = error ? <div className="al-msg err">{error}</div> : <SteamSpinner background="transparent" />;
  else {
    const all = [...s.games].sort(s.sort === "title" ? (a, b) => a.title.localeCompare(b.title) : () => 0);
    const byId = new Map(s.games.map((g) => [g.id, g]));
    // Installed games no longer on the account still show up here.
    const installedGames = Object.values(s.installed).map((r) => byId.get(r.game_id) ?? fromRec(r))
      .sort((a, b) => a.title.localeCompare(b.title));
    const updates = installedGames.filter((g) => s.installed[g.id]?.update);
    const queued = s.jobs.map((j) => byId.get(j.game_id) ?? (s.installed[j.game_id] ? fromRec(s.installed[j.game_id]) : null))
      .filter(Boolean) as Game[];
    const bar = (
      <Focusable className="al-bar" flow-children="row" style={{ padding: "0 24px 10px" }}>
        <span className="lbl">Sort</span>
        <div style={{ minWidth: 180 }}>
          <Dropdown selectedOption={s.sort} rgOptions={[{ data: "added", label: "Recently added" }, { data: "title", label: "A–Z" }]}
            onChange={(o) => { s.sort = o.data; changed(); }} />
        </div>
        <div style={{ flex: 1 }} />
        <DialogButton className="al-btn" disabled={busy} onClick={refresh}>{busy ? "Refreshing…" : "Refresh"}</DialogButton>
        <DialogButton className="al-btn" disabled={s.checking} onClick={() => checkUpdates(true)}>{s.checking ? "Checking…" : "Check for updates"}</DialogButton>
      </Focusable>
    );
    const tabs = [
      { id: "free", title: "Free games", content: <FreeTab /> },
      { id: "all", title: `All · ${all.length}`, content: <>{bar}<Grid games={all} empty="No games on this Amazon account yet. Claim free games with Prime in the Free games tab." /></> },
      { id: "installed", title: `Installed · ${installedGames.length}`, content: <>{bar}<Grid games={installedGames} empty="No Amazon games installed yet. Pick one in All and press Install." /></> },
      { id: "updates", title: `Updates · ${updates.length}`, content: <>{bar}<Grid games={updates} empty={s.checking ? "Checking…" : "Everything is up to date."} /></> },
      { id: "downloads", title: `Downloads · ${queued.length}`, content: <><div style={{ height: 8 }} /><Grid games={queued} empty="Nothing downloading." /></> },
    ];
    body = (
      <div className="al-tabs">
        {error && <div className="al-msg err" style={{ paddingTop: 0 }}>{error}</div>}
        <Tabs activeTab={tabs.some((t) => t.id === s.tab) ? s.tab : "all"} onShowTab={(t: string) => { s.tab = t; }} autoFocusContents tabs={tabs} />
      </div>
    );
  }

  const user = s.settings?.user;
  const upd = updateCount();
  return (
    <div className="al-page">
      <style>{PAGE_CSS}</style>
      <div className="al-inner">
        <div className="al-head">
          <span className="t">Amazon Library</span>
          {s.settings?.signedIn && <span className="s">{user?.name}</span>}
          <span className="grow" />
          {upd > 0 && <span className="tag" style={{ color: C.accent, borderColor: C.accent }}>{upd} UPDATE{upd > 1 ? "S" : ""}</span>}
          <span className="tag">AMAZON GAMES</span>
        </div>
        {body}
      </div>
    </div>
  );
}
