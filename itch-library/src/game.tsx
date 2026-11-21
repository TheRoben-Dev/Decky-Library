/*
 * Game page: /itch-library/game/:id
 * Install (picking the build when there's a choice), Play, Update, Cancel; for installed games
 * the launch file, re-adding to Steam, fresh artwork and Uninstall (with an opt-in to delete the
 * Proton prefix, which holds Windows saves).
 */
import { ConfirmModal, DialogButton, Dropdown, Focusable, Navigation, showModal, SteamSpinner, useParams } from "@decky/ui";
import { ReactNode, useEffect, useState } from "react";
import { addToSteam, cancelJob, refreshInstalled, removeGame, startInstall } from "./actions";
import { Exe, Game, getExecutables, getGame, Installed, setExe, Upload } from "./backend";
import { fmtBytes, jobFor, jobLine, state, useStore } from "./state";
import { applyArt, openInSteam, shortcutExists, toast } from "./steam";
import { Bar, C, PAGE_CSS, Plats } from "./ui";

function uploadLabel(u: Upload) {
  const plat = u.platforms.filter((p) => p === "linux" || p === "windows").map((p) => (p === "linux" ? "Linux" : "Windows")).join("+");
  return [u.name, plat, u.size ? fmtBytes(u.size) : "", u.demo ? "demo" : "", u.version].filter(Boolean).join(" · ");
}

function ExePicker({ rec }: { rec: Installed }) {
  const [list, setList] = useState<Exe[] | null>(null);
  useEffect(() => { getExecutables(rec.game_id).then(setList).catch(() => setList([])); }, [rec.game_id, rec.appid]);
  if (!list) return <div className="v" style={{ color: C.text1 }}>Looking for executables…</div>;
  if (!list.length) return <div className="v" style={{ color: C.warn }}>No executables found in the game folder.</div>;
  const rel = (p: string) => p.startsWith(rec.dir + "/") ? p.slice(rec.dir.length + 1) : p.replace(/^.*\/drive_c\//, "C:/");
  const opts = list.map((e) => ({ data: e.path, label: `${rel(e.path)} · ${e.kind === "linux" ? "Linux" : "Windows"}` }));
  if (!list.some((e) => e.path === rec.exe)) opts.unshift({ data: rec.exe, label: rel(rec.exe) });
  return (
    <Dropdown selectedOption={rec.exe} rgOptions={opts} menuLabel="Launch file"
      onChange={async (o) => {
        const r = await setExe(rec.game_id, o.data);
        if (!r.ok) { toast(r.error); return; }
        state.installed[String(rec.game_id)] = r.installed;
        await addToSteam(r.installed, false);
        toast(`Steam now launches ${rel(o.data)}`);
      }} />
  );
}

export function GamePage() {
  const s = useStore();
  const id = Number(useParams<{ id: string }>().id);
  const [game, setGame] = useState<Game | null>(() => s.games?.find((g) => g.id === id) ?? null);
  const [uploads, setUploads] = useState<Upload[] | null>(null);
  const [pick, setPick] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getGame(id).then((r) => {
      if (!live) return;
      if (r.game) setGame(r.game);
      if (r.installed) { s.installed[String(id)] = r.installed; }
      if (!r.ok) { setError(r.error); setUploads([]); return; }
      setUploads(r.uploads);
      setPick(r.installed?.upload_id && r.uploads.some((u) => u.id === r.installed!.upload_id && u.usable) ? r.installed.upload_id : r.best);
    }).catch((e) => live && setError(String(e)));
    return () => { live = false; };
  }, [id]);

  const rec = s.installed[String(id)];
  const job = jobFor(id);
  const usable = (uploads ?? []).filter((u) => u.usable);
  const inSteam = !!rec && shortcutExists(rec.appid);

  const uninstall = () => {
    const prefix = rec?.kind === "windows" && rec.appid > 0;
    showModal(
      <ConfirmModal strTitle={`Uninstall ${rec!.title}?`}
        strDescription={prefix
          ? "Removes the game's files and its Steam shortcut. Windows games keep saves in their Proton prefix: keep it unless you're sure you don't need those saves."
          : "Removes the game's files and its Steam shortcut. Saves the game kept in its own folder are deleted too."}
        strOKButtonText="Uninstall" strCancelButtonText="Cancel"
        strMiddleButtonText={prefix ? "Uninstall + delete saves" : undefined}
        onMiddleButton={prefix ? async () => { if (await removeGame(id, true)) toast(`${rec!.title} and its prefix removed`); } : undefined}
        onOK={async () => { if (await removeGame(id, false)) toast(`${rec!.title} uninstalled`); }} />,
    );
  };

  const run = async (what: string, f: () => Promise<any>) => {
    setBusy(what);
    try { await f(); } catch (e: any) { toast(`${what} failed: ${e?.message ?? e}`); } finally { setBusy(null); }
  };

  let actions: ReactNode;
  if (job) {
    actions = (
      <>
        <div className="il-row" style={{ justifyContent: "space-between" }}>
          <span className="k">{job.action === "update" ? "Updating" : "Installing"}</span>
          <span className="v" style={{ fontFamily: "monospace" }}>{jobLine(job)}</span>
        </div>
        <Bar value={job.phase === "downloading" && job.total ? job.done / job.total : job.phase === "queued" ? 0 : 1}
          color={job.phase === "downloading" ? C.data : C.active} />
        <Focusable className="il-row" flow-children="row">
          <DialogButton className="il-btn" onClick={() => cancelJob(id)}>Cancel</DialogButton>
        </Focusable>
      </>
    );
  } else if (rec) {
    actions = (
      <Focusable className="il-row" flow-children="row">
        {inSteam && <DialogButton className="il-btn primary" onClick={() => openInSteam(rec.appid)}>Play</DialogButton>}
        {!inSteam && <DialogButton className="il-btn primary" disabled={!!busy} onClick={() => run("Add to Steam", async () => {
          const a = await addToSteam(rec, true); if (a) toast(`${rec.title} added to Steam`);
        })}>{busy === "Add to Steam" ? "Adding…" : "Add to Steam"}</DialogButton>}
        {(rec.update || !rec.present) && <DialogButton className="il-btn" onClick={() => startInstall(id, rec.update ? 0 : rec.upload_id)}>
          {rec.present ? `Update${rec.update_name ? ` · ${rec.update_name}` : ""}` : "Reinstall"}</DialogButton>}
        <DialogButton className="il-btn" onClick={uninstall}>Uninstall</DialogButton>
      </Focusable>
    );
  } else if (uploads === null) {
    actions = <div className="v" style={{ color: C.text1 }}>Looking up builds…</div>;
  } else if (!usable.length) {
    const mac = (uploads ?? []).some((u) => u.platforms.includes("mac"));
    actions = <div className="v" style={{ color: C.warn }}>{error ?? (mac ? "Only a macOS build, nothing to install here." : "No Linux or Windows build to download. It may be a web game: open it on itch.io.")}</div>;
  } else {
    const cur = usable.find((u) => u.id === pick) ?? usable[0];
    actions = (
      <>
        {usable.length > 1 && (
          <div className="il-row">
            <span className="k" style={{ minWidth: 60 }}>Build</span>
            <div style={{ flex: 1, minWidth: 260 }}>
              <Dropdown selectedOption={cur.id} menuLabel="Build" rgOptions={usable.map((u) => ({ data: u.id, label: uploadLabel(u) }))}
                onChange={(o) => setPick(o.data)} />
            </div>
          </div>
        )}
        <Focusable className="il-row" flow-children="row">
          <DialogButton className="il-btn primary" onClick={() => startInstall(id, cur.id)}>
            Install{cur.size ? ` · ${fmtBytes(cur.size)}` : ""}
          </DialogButton>
          <span style={{ fontSize: 12, color: C.text1 }}>
            {cur.platforms.includes("linux") && (s.settings?.prefer !== "windows" || !cur.platforms.includes("windows")) ? "Native Linux build" : "Windows build · runs with Proton"}
          </span>
        </Focusable>
      </>
    );
  }

  return (
    <div className="il-page">
      <style>{PAGE_CSS}</style>
      <div className="il-inner">
        <div className="il-head">
          <span className="t">Itch Library</span>
          <span className="s">{game?.title ?? ""}</span>
          <span className="grow" />
          <span className="tag">ITCH.IO</span>
        </div>
        {!game && !error ? <SteamSpinner background="transparent" /> : !game ? (
          <div className="il-msg err">{error}<div style={{ marginTop: 16 }}><DialogButton className="il-btn" onClick={() => Navigation.NavigateBack()}>Back</DialogButton></div></div>
        ) : (
          <div className="il-detail">
            <div className="cover">
              <div className="frame">{(game.still || game.cover) && <img src={game.still || game.cover} draggable={false} />}</div>
            </div>
            <Focusable className="info" flow-children="column">
              <h1>{game.title}</h1>
              <div className="il-row"><Plats list={game.platforms} />{game.author && <span className="by">by {game.author}</span>}</div>
              {game.short && <div className="short">{game.short}</div>}
              <div className="il-panel">{actions}</div>
              {rec && !job && (
                <div className="il-panel">
                  {rec.installer && <div style={{ color: C.warn, fontSize: 13 }}>
                    This build is an installer. Play runs it once through Proton: install to the suggested folder, then pick the game below.</div>}
                  {!rec.present && <div style={{ color: C.warn, fontSize: 13 }}>The game's folder is missing (SD card out, or deleted). Reinstall or uninstall it.</div>}
                  <div className="il-kv">
                    <span className="k">Build</span><span className="v">{rec.upload_name}{rec.version ? ` · ${rec.version}` : ""}</span>
                    <span className="k">Runs</span><span className="v">{rec.kind === "linux" ? "Native Linux" : `Proton${s.settings?.tool ? ` (${s.settings.tool})` : ""}`}</span>
                    <span className="k">Folder</span><span className="v">{rec.dir}</span>
                    <span className="k">Size</span><span className="v">{fmtBytes(rec.size)}</span>
                  </div>
                  {rec.present && <><span className="k">Launch file</span><ExePicker rec={rec} /></>}
                  <Focusable className="il-row" flow-children="row">
                    {inSteam && <DialogButton className="il-btn" disabled={!!busy} onClick={() => run("Artwork", async () => {
                      await applyArt(id, rec.appid, rec.title); toast("Artwork refreshed");
                    })}>{busy === "Artwork" ? "Drawing…" : "Redo artwork"}</DialogButton>}
                    {inSteam && <DialogButton className="il-btn" disabled={!!busy} onClick={() => run("Steam shortcut", async () => {
                      await addToSteam(rec, false); await refreshInstalled(); toast("Steam shortcut refreshed");
                    })}>Fix Steam shortcut</DialogButton>}
                  </Focusable>
                </div>
              )}
            </Focusable>
          </div>
        )}
      </div>
    </div>
  );
}
