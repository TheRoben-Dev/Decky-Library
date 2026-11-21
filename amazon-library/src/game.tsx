/*
 * Game page: /amazon-library/game/:id
 * Install, Play, Update, Cancel; for installed games the launch file, re-adding to Steam, fresh
 * artwork, Verify files and Uninstall (with an opt-in to delete the Proton prefix, which holds
 * most saves).
 */
import { ConfirmModal, DialogButton, Dropdown, Focusable, Navigation, showModal, SteamSpinner, useParams } from "@decky/ui";
import { ReactNode, useEffect, useState } from "react";
import { addToSteam, cancelJob, refreshInstalled, removeGame, startInstall } from "./actions";
import { Exe, Game, getExecutables, getGame, Installed, setExe } from "./backend";
import { fmtBytes, jobFor, jobLine, state, useStore } from "./state";
import { applyArt, openInSteam, shortcutExists, toast } from "./steam";
import { Bar, C, PAGE_CSS } from "./ui";

function ExePicker({ rec }: { rec: Installed }) {
  const [list, setList] = useState<Exe[] | null>(null);
  useEffect(() => { getExecutables(rec.game_id).then(setList).catch(() => setList([])); }, [rec.game_id, rec.exe]);
  if (!list) return <div className="v" style={{ color: C.text1 }}>Looking for executables…</div>;
  if (!list.length) return <div className="v" style={{ color: C.warn }}>No executables found in the game folder.</div>;
  const rel = (p: string) => p.startsWith(rec.dir + "/") ? p.slice(rec.dir.length + 1) : p;
  const opts = list.map((e) => ({ data: e.path, label: `${rel(e.path)}${e.fuel ? " · Amazon's choice" : ""}` }));
  if (!list.some((e) => e.path === rec.exe)) opts.unshift({ data: rec.exe, label: rel(rec.exe) });
  return (
    <Dropdown selectedOption={rec.exe} rgOptions={opts} menuLabel="Launch file"
      onChange={async (o) => {
        const r = await setExe(rec.game_id, o.data);
        if (!r.ok) { toast(r.error); return; }
        state.installed[rec.game_id] = r.installed;
        await addToSteam(r.installed, false);
        toast(`Steam now launches ${rel(o.data)}`);
      }} />
  );
}

export function GamePage() {
  const s = useStore();
  const id = decodeURIComponent(useParams<{ id: string }>().id);
  const [game, setGame] = useState<Game | null>(() => s.games?.find((g) => g.id === id) ?? null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getGame(id).then((r) => {
      if (!live) return;
      if (!r.ok) { setError(r.error); return; }
      setGame(r.game);
      if (r.installed) s.installed[id] = r.installed;
    }).catch((e) => live && setError(String(e)));
    return () => { live = false; };
  }, [id]);

  const rec = s.installed[id];
  const job = jobFor(id);
  const inSteam = !!rec && shortcutExists(rec.appid);

  const uninstall = () => {
    const prefix = rec!.appid > 0;
    showModal(
      <ConfirmModal strTitle={`Uninstall ${rec!.title}?`}
        strDescription={prefix
          ? "Removes the game's files and its Steam shortcut. Most games keep saves in their Proton prefix: keep it unless you're sure you don't need those saves."
          : "Removes the game's files and its Steam shortcut."}
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
    const verb = job.action === "update" ? "Updating" : job.action === "repair" ? "Verifying" : "Installing";
    actions = (
      <>
        <div className="al-row" style={{ justifyContent: "space-between" }}>
          <span className="k">{verb}</span>
          <span className="v" style={{ fontFamily: "monospace" }}>{jobLine(job)}</span>
        </div>
        <Bar value={job.phase === "downloading" && job.total ? job.done / job.total : job.phase === "queued" ? 0 : 1}
          color={job.phase === "downloading" ? C.data : C.active} />
        <Focusable className="al-row" flow-children="row">
          <DialogButton className="al-btn" onClick={() => cancelJob(id)}>Cancel</DialogButton>
        </Focusable>
      </>
    );
  } else if (rec) {
    actions = (
      <Focusable className="al-row" flow-children="row">
        {inSteam && <DialogButton className="al-btn primary" onClick={() => openInSteam(rec.appid)}>Play</DialogButton>}
        {!inSteam && <DialogButton className="al-btn primary" disabled={!!busy} onClick={() => run("Add to Steam", async () => {
          const a = await addToSteam(rec, true); if (a) toast(`${rec.title} added to Steam`);
        })}>{busy === "Add to Steam" ? "Adding…" : "Add to Steam"}</DialogButton>}
        {(rec.update || !rec.present) && <DialogButton className="al-btn" onClick={() => startInstall(id, !rec.present)}>
          {rec.present ? "Update" : "Reinstall"}</DialogButton>}
        <DialogButton className="al-btn" onClick={uninstall}>Uninstall</DialogButton>
      </Focusable>
    );
  } else {
    actions = (
      <Focusable className="al-row" flow-children="row">
        <DialogButton className="al-btn primary" onClick={() => startInstall(id)}>Install</DialogButton>
        <span style={{ fontSize: 12, color: C.text1 }}>Windows game · runs with Proton · installs to {s.settings?.root ?? "~/Games/amazon"}</span>
      </Focusable>
    );
  }

  const meta = game ? [game.developer, game.publisher !== game.developer ? game.publisher : "", game.released.slice(0, 4), ...game.genres.slice(0, 2)]
    .filter(Boolean).join(" · ") : "";
  return (
    <div className="al-page">
      <style>{PAGE_CSS}</style>
      {game?.background && <div className="al-hero" style={{ backgroundImage: `url("${game.background}")` }} />}
      <div className="al-inner">
        <div className="al-head">
          <span className="t">Amazon Library</span>
          <span className="s">{game?.title ?? ""}</span>
          <span className="grow" />
          <span className="tag">AMAZON GAMES</span>
        </div>
        {!game && !error ? <SteamSpinner background="transparent" /> : !game ? (
          <div className="al-msg err">{error}<div style={{ marginTop: 16 }}><DialogButton className="al-btn" onClick={() => Navigation.NavigateBack()}>Back</DialogButton></div></div>
        ) : (
          <div className="al-detail">
            <div className="cover">
              <div className="frame">{(game.cover || game.icon) && <img src={game.cover || game.icon} draggable={false} />}</div>
            </div>
            <Focusable className="info" flow-children="column">
              {game.logo ? <img src={game.logo} alt={game.title} style={{ maxWidth: 420, maxHeight: 120, objectFit: "contain", objectPosition: "left" }} />
                : <h1>{game.title}</h1>}
              {meta && <div className="by">{meta}</div>}
              {game.short && <div className="short">{game.short}</div>}
              <div className="al-panel">{actions}</div>
              {rec && !job && (
                <div className="al-panel">
                  {!rec.present && <div style={{ color: C.warn, fontSize: 13 }}>The game's folder is missing (SD card out, or deleted). Reinstall or uninstall it.</div>}
                  {rec.post_install > 0 && <div style={{ color: C.text1, fontSize: 12 }}>
                    Amazon lists {rec.post_install} setup step{rec.post_install > 1 ? "s" : ""} (usually Visual C++ or DirectX runtimes). Proton already includes these; if the game won't start, try another Proton version.</div>}
                  <div className="al-kv">
                    <span className="k">Version</span><span className="v">{rec.version || "?"}</span>
                    <span className="k">Runs</span><span className="v">{`Proton${s.settings?.tool ? ` (${s.settings.tool})` : ""}`}</span>
                    <span className="k">Folder</span><span className="v">{rec.dir}</span>
                    <span className="k">Size</span><span className="v">{fmtBytes(rec.size)}</span>
                  </div>
                  {rec.present && <><span className="k">Launch file</span><ExePicker rec={rec} /></>}
                  <Focusable className="al-row" flow-children="row">
                    {rec.present && <DialogButton className="al-btn" onClick={() => startInstall(id, true)}>Verify files</DialogButton>}
                    {inSteam && <DialogButton className="al-btn" disabled={!!busy} onClick={() => run("Artwork", async () => {
                      await applyArt(id, rec.appid, rec.title); toast("Artwork refreshed");
                    })}>{busy === "Artwork" ? "Drawing…" : "Redo artwork"}</DialogButton>}
                    {inSteam && <DialogButton className="al-btn" disabled={!!busy} onClick={() => run("Steam shortcut", async () => {
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
