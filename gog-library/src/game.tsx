/*
 * Game page: /gog-library/game/:id
 * Owned games: install (native Linux or Windows through Proton when there's a choice), Play, Update,
 * Cancel; for installed games the launch file, re-adding to Steam, fresh artwork and Uninstall (with
 * an opt-in to delete the Proton prefix, which holds Windows saves).
 * Store games you don't own: price, and buying them on GOG (Steam's browser or a QR for the phone).
 */
import { ConfirmModal, DialogButton, Dropdown, Focusable, ModalRoot, Navigation, showModal, SteamSpinner, useParams } from "@decky/ui";
import { ReactNode, useEffect, useState } from "react";
import { addToSteam, cancelJob, loadLibrary, refreshInstalled, removeGame, startInstall } from "./actions";
import { Qr } from "./signin";
import { StoreDetails } from "./details";
import { hintOf } from "./store";
import { Exe, Game, getExecutables, getGame, Installed, Option, setExe } from "./backend";
import { fmtBytes, jobFor, jobLine, state, useStore } from "./state";
import { applyArt, openInSteam, shortcutExists, toast } from "./steam";
import { Bar, C, PAGE_CSS, Plats } from "./ui";

const kindLabel = (k: string) => (k === "linux" ? "Native Linux" : "Windows · Proton");

function optionLabel(o: Option) {
  return [kindLabel(o.kind), o.size ? fmtBytes(o.size) : "", o.version ? `v${o.version.replace(/^v/i, "")}` : ""].filter(Boolean).join(" · ");
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

function BuyQr({ url, title, free, onBought, closeModal }: { url: string; title: string; free: boolean; onBought: () => void; closeModal?: () => void }) {
  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      <div style={{ display: "flex", gap: 24, alignItems: "center", flexWrap: "wrap" }}>
        <Qr text={url} />
        <div style={{ flex: 1, minWidth: 240, display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ fontSize: 18, fontWeight: 700 }}>{free ? "Get" : "Buy"} {title} on your phone</div>
          <div style={{ fontSize: 13, color: C.text1 }}>
            Scan to open the game's GOG page, {free ? "add it to your library" : "buy it"} there with your GOG account, then press
            {free ? " I added it" : " I bought it"}.</div>
          <div style={{ fontSize: 11, color: C.data, wordBreak: "break-all" }}>{url}</div>
          <Focusable className="gl-row" flow-children="row" style={{ display: "flex", gap: 8 }}>
            <DialogButton onClick={() => { closeModal?.(); onBought(); }}>{free ? "I added it" : "I bought it"}</DialogButton>
            <DialogButton onClick={() => closeModal?.()}>Close</DialogButton>
          </Focusable>
        </div>
      </div>
    </ModalRoot>
  );
}

export function GamePage() {
  const s = useStore();
  const id = Number(useParams<{ id: string }>().id);
  const seen = s.seen.get(id);
  const [game, setGame] = useState<Game | null>(() => s.games?.find((g) => g.id === id) ?? (seen ? hintOf(seen) as Game : null));
  const [options, setOptions] = useState<Option[] | null>(null);
  const [dlcs, setDlcs] = useState<{ id: number; title: string }[]>([]);
  const [pick, setPick] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [owned, setOwned] = useState(() => !!s.games?.some((g) => g.id === id));
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let live = true;
    getGame(id, seen ? hintOf(seen) : null).then((r) => {
      if (!live) return;
      if (r.game) setGame({ ...(seen ? hintOf(seen) : {}), ...r.game } as Game);
      setOwned(!!r.owned);
      if (r.installed) { s.installed[String(id)] = r.installed; }
      if (!r.ok) { setError(r.error); setOptions([]); return; }
      setOptions(r.options);
      setDlcs(r.dlcs);
      const prefer = r.installed?.kind ?? s.settings?.prefer ?? "linux";
      setPick(r.options.some((o) => o.kind === prefer) ? prefer : r.options[0]?.kind ?? "");
    }).catch((e) => live && setError(String(e)));
    return () => { live = false; };
  }, [id, reload]);

  const rec = s.installed[String(id)];
  const job = jobFor(id);
  const inSteam = !!rec && shortcutExists(rec.appid);

  const uninstall = () => {
    const prefix = rec?.kind === "windows" && rec.appid > 0;
    showModal(
      <ConfirmModal strTitle={`Uninstall ${rec!.title}?`}
        strDescription={prefix
          ? "Removes the game's files and its Steam shortcut. Windows games keep saves in their Proton prefix: keep it unless you're sure you don't need those saves."
          : "Removes the game's files and its Steam shortcut. Saves the game kept in its own folder are deleted too (most Linux games keep theirs in your home folder)."}
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
        <div className="gl-row" style={{ justifyContent: "space-between" }}>
          <span className="k">{job.action === "update" ? "Updating" : "Installing"}</span>
          <span className="v" style={{ fontFamily: "monospace" }}>{jobLine(job)}</span>
        </div>
        <Bar value={job.phase === "downloading" && job.total ? job.done / job.total : job.phase === "queued" ? 0 : 1}
          color={job.phase === "downloading" ? C.data : C.active} />
        <Focusable className="gl-row" flow-children="row">
          <DialogButton className="gl-btn" onClick={() => cancelJob(id)}>Cancel</DialogButton>
        </Focusable>
      </>
    );
  } else if (rec) {
    actions = (
      <Focusable className="gl-row" flow-children="row">
        {inSteam && <DialogButton className="gl-btn primary" onClick={() => openInSteam(rec.appid)}>Play</DialogButton>}
        {!inSteam && <DialogButton className="gl-btn primary" disabled={!!busy} onClick={() => run("Add to Steam", async () => {
          const a = await addToSteam(rec, true); if (a) toast(`${rec.title} added to Steam`);
        })}>{busy === "Add to Steam" ? "Adding…" : "Add to Steam"}</DialogButton>}
        {(rec.update || !rec.present) && <DialogButton className="gl-btn" onClick={() => startInstall(id, rec.kind)}>
          {rec.present ? `Update${rec.update_name ? ` · ${rec.update_name}` : ""}` : "Reinstall"}</DialogButton>}
        <DialogButton className="gl-btn" onClick={uninstall}>Uninstall</DialogButton>
      </Focusable>
    );
  } else if (options === null) {
    actions = <div className="v" style={{ color: C.text1 }}>Looking up downloads…</div>;
  } else if (!owned) {
    const url = game?.url ?? "";
    const free = !!game?.free;
    const bought = () => run("Refresh", async () => {
      await loadLibrary(true);
      setOptions(null); setReload((n) => n + 1);
    });
    actions = (
      <>
        <div className="gl-row" style={{ justifyContent: "space-between" }}>
          <span className="k">Price</span>
          <span className="v" style={{ fontFamily: "monospace", color: C.accent }}>
            {free ? "Free on GOG" : game?.price ? `${game.price} on GOG${game.sale ? ` (${game.sale})` : ""}` : "See GOG"}</span>
        </div>
        <Focusable className="gl-row" flow-children="row">
          <DialogButton className="gl-btn primary" disabled={!url} onClick={() => { Navigation.CloseSideMenus(); Navigation.NavigateToExternalWeb(url); }}>
            {free ? "Get it on GOG" : "Buy on GOG"}</DialogButton>
          <DialogButton className="gl-btn" disabled={!url} onClick={() => showModal(<BuyQr url={url} title={game?.title ?? ""} free={free} onBought={bought} />)}>
            {free ? "Get on phone" : "Buy on phone"}</DialogButton>
          <DialogButton className="gl-btn" disabled={!!busy} onClick={bought}>{busy === "Refresh" ? "Checking…" : free ? "I added it" : "I bought it"}</DialogButton>
        </Focusable>
        <div style={{ fontSize: 12, color: C.text1 }}>
          {free ? "GOG only lets you download games that are in your library, free ones included: add it on its GOG page (signed in with your GOG account), then press I added it."
            : "Buy it on the game's GOG page (sign in there with your GOG account), then press I bought it."} It moves to your library and installs like any other game.
        </div>
      </>
    );
  } else if (!options.length) {
    const mac = (game?.platforms ?? []).includes("mac");
    actions = <div className="v" style={{ color: C.warn }}>{error ?? (mac ? "Only a macOS version, nothing to install here." : "GOG has no Linux or Windows download of this game for your account.")}</div>;
  } else {
    const cur = options.find((o) => o.kind === pick) ?? options[0];
    actions = (
      <>
        {options.length > 1 && (
          <div className="gl-row">
            <span className="k" style={{ minWidth: 60 }}>Version</span>
            <div style={{ flex: 1, minWidth: 260 }}>
              <Dropdown selectedOption={cur.kind} menuLabel="Version" rgOptions={options.map((o) => ({ data: o.kind, label: optionLabel(o) }))}
                onChange={(o) => setPick(o.data)} />
            </div>
          </div>
        )}
        <Focusable className="gl-row" flow-children="row">
          <DialogButton className="gl-btn primary" onClick={() => startInstall(id, cur.kind)}>
            Install{cur.size ? ` · ${fmtBytes(cur.size)}` : ""}
          </DialogButton>
          <span style={{ fontSize: 12, color: C.text1 }}>
            {cur.kind === "linux" ? "Native Linux version" : "Windows version · runs with Proton, downloaded file by file like GOG Galaxy"}
          </span>
        </Focusable>
        {dlcs.length > 0 && <div style={{ fontSize: 12, color: C.text1 }}>
          Owned DLC{dlcs.length > 1 ? "s" : ""}: {dlcs.map((d) => d.title).join(", ")}.{" "}
          {cur.kind === "windows" ? "Installed with the game." : "Linux DLC installers aren't added automatically yet; the Windows version includes them."}</div>}
      </>
    );
  }

  return (
    <div className="gl-page">
      <style>{PAGE_CSS}</style>
      <div className="gl-inner">
        <div className="gl-head">
          <span className="t">GOG Library</span>
          <span className="s">{game?.title ?? ""}</span>
          <span className="grow" />
          {owned && <span className="tag" style={{ color: C.ok, borderColor: C.ok }}>OWNED</span>}
          <span className="tag">GOG</span>
        </div>
        {!game && !error ? <SteamSpinner background="transparent" /> : !game ? (
          <div className="gl-msg err">{error}<div style={{ marginTop: 16 }}><DialogButton className="gl-btn" onClick={() => Navigation.NavigateBack()}>Back</DialogButton></div></div>
        ) : (
          <div className="gl-detail" style={{ position: "relative" }}>
            {game.background && <div className="bg" style={{ backgroundImage: `url("${game.background}")` }} />}
            <div className="cover" style={{ position: "relative" }}>
              <div className="frame">{game.cover && <img src={game.cover} draggable={false} />}</div>
            </div>
            <Focusable className="info" flow-children="column" style={{ position: "relative" }}>
              <h1>{game.title}</h1>
              <div className="gl-row"><Plats list={game.platforms ?? []} />{game.developer && <span className="by">by {game.developer}</span>}
                {game.preorder && <span className="by" style={{ color: C.warn }}>Pre-order</span>}</div>
              {game.short && <div className="short">{game.short}</div>}
              <div className="gl-panel">{actions}</div>
              {rec && !job && (
                <div className="gl-panel">
                  {rec.installer && <div style={{ color: C.warn, fontSize: 13 }}>
                    This is GOG's Windows installer (innoextract isn't installed, so it couldn't be unpacked). Play runs it once through
                    Proton: install to the suggested folder, then pick the game's .exe below.</div>}
                  {!rec.present && <div style={{ color: C.warn, fontSize: 13 }}>The game's folder is missing (SD card out, or deleted). Reinstall or uninstall it.</div>}
                  <div className="gl-kv">
                    <span className="k">Version</span><span className="v">{rec.version || "—"}{rec.method === "galaxy" ? " · Galaxy build" : rec.method === "linux" ? " · Linux installer" : " · Windows installer"}</span>
                    <span className="k">Runs</span><span className="v">{rec.kind === "linux" ? "Native Linux" : `Proton${s.settings?.tool ? ` (${s.settings.tool})` : ""}`}</span>
                    <span className="k">Folder</span><span className="v">{rec.dir}</span>
                    <span className="k">Size</span><span className="v">{fmtBytes(rec.size)}</span>
                  </div>
                  {rec.present && <><span className="k">Launch file</span><ExePicker rec={rec} /></>}
                  <Focusable className="gl-row" flow-children="row">
                    {inSteam && <DialogButton className="gl-btn" disabled={!!busy} onClick={() => run("Artwork", async () => {
                      await applyArt(id, rec.appid, rec.title, s.settings?.art); toast("Artwork refreshed");
                    })}>{busy === "Artwork" ? "Drawing…" : "Redo artwork"}</DialogButton>}
                    {inSteam && <DialogButton className="gl-btn" disabled={!!busy} onClick={() => run("Steam shortcut", async () => {
                      await addToSteam(rec, false); await refreshInstalled(); toast("Steam shortcut refreshed");
                    })}>Fix Steam shortcut</DialogButton>}
                  </Focusable>
                </div>
              )}
              <StoreDetails id={id} item={seen} />
            </Focusable>
          </div>
        )}
      </div>
    </div>
  );
}
