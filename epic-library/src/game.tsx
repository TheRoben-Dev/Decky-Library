/*
 * Game page: /epic-library/game/:app   (a game you own)
 *   Install (with size), Play, Update, Cancel, resume or discard a paused download; for installed
 *   games: repair, cloud saves, re-adding to Steam, fresh artwork and Uninstall (with an opt-in to
 *   delete the Proton prefix, which holds most Windows saves).
 * Offer page: /epic-library/offer   (a store game you don't own)
 *   Price, Get/Buy on Epic in Steam's browser or on your phone, and "I got it" to refresh.
 */
import { ConfirmModal, DialogButton, Focusable, ModalRoot, Navigation, showModal, SteamSpinner, useParams } from "@decky/ui";
import { ReactNode, useEffect, useRef, useState } from "react";
import { addToSteam, cancelJob, loadLibrary, refreshInstalled, removeGame, startInstall } from "./actions";
import { discard, Game, getGame, installInfo, syncSaves } from "./backend";
import { Qr } from "./signin";
import { gamePath } from "./routes";
import { fmtBytes, jobFor, jobLine, ownedByNs, sized, useStore } from "./state";
import { applyArt, openInSteam, shortcutExists, toast } from "./steam";
import { Bar, C, Chip, PAGE_CSS } from "./ui";

function Shell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="ep-page">
      <style>{PAGE_CSS}</style>
      <div className="ep-inner">
        <div className="ep-head">
          <span className="t">Epic Library</span>
          <span className="s">{title}</span>
          <span className="grow" />
          <span className="tag">EPIC GAMES</span>
        </div>
        {children}
      </div>
    </div>
  );
}

function Cover({ url }: { url: string }) {
  return <div className="cover"><div className="frame">{url && <img src={sized(url, 600, 800)} draggable={false} />}</div></div>;
}

function BuyQr({ url, title, onBought, closeModal }: { url: string; title: string; onBought: () => void; closeModal?: () => void }) {
  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      <div style={{ display: "flex", gap: 24, alignItems: "center", flexWrap: "wrap" }}>
        <Qr text={url} />
        <div style={{ flex: 1, minWidth: 240, display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ fontSize: 18, fontWeight: 700 }}>Get {title} on your phone</div>
          <div style={{ fontSize: 13, color: C.text1 }}>Scan to open the game's Epic Games Store page, get or buy it there with your Epic account, then press I got it.</div>
          <div style={{ fontSize: 11, color: C.data, wordBreak: "break-all" }}>{url}</div>
          <Focusable className="ep-row" flow-children="row" style={{ display: "flex", gap: 8 }}>
            <DialogButton onClick={() => { closeModal?.(); onBought(); }}>I got it</DialogButton>
            <DialogButton onClick={() => closeModal?.()}>Close</DialogButton>
          </Focusable>
        </div>
      </div>
    </ModalRoot>
  );
}

export function GamePage() {
  const s = useStore();
  const app = decodeURIComponent(useParams<{ app: string }>().app);
  const [game, setGame] = useState<Game | null>(() => s.games?.find((g) => g.app === app) ?? null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [resume, setResume] = useState(false);
  const [size, setSize] = useState<{ disk: number; download: number } | null>(null);

  const reload = () => getGame(app).then((r) => {
    if (!r.ok) { setError(r.error); return; }
    setGame(r.game);
    setResume(r.resume);
    if (r.installed) s.installed[app] = r.installed; else delete s.installed[app];
  }).catch((e) => setError(String(e)));
  useEffect(() => { reload(); }, [app]);

  const rec = s.installed[app];
  const job = jobFor(app);
  const inSteam = !!rec && shortcutExists(rec.appid);

  // Install size needs the game's manifest from Epic: only fetched on this page, only if needed.
  useEffect(() => {
    if (rec || !game?.installable || size) return;
    let live = true;
    installInfo(app).then((r) => { if (live && r.ok) setSize({ disk: r.disk, download: r.download }); }).catch(() => {});
    return () => { live = false; };
  }, [app, !!rec, game?.installable]);
  // A finished job changes what's on disk (resume file, install record).
  const hadJob = useRef(!!job);
  useEffect(() => {
    if (hadJob.current && !job) reload();
    hadJob.current = !!job;
  }, [!!job]);

  const run = async (what: string, f: () => Promise<any>) => {
    setBusy(what);
    try { await f(); } catch (e: any) { toast(`${what} failed: ${e?.message ?? e}`); } finally { setBusy(null); }
  };

  const uninstall = () => {
    const prefix = rec!.appid > 0;
    showModal(
      <ConfirmModal strTitle={`Uninstall ${rec!.title}?`}
        strDescription={prefix
          ? "Removes the game's files and its Steam shortcut. Many games keep saves in their Proton prefix: keep it unless you're sure you don't need them (games with Epic cloud saves can get theirs back)."
          : "Removes the game's files and its Steam shortcut."}
        strOKButtonText="Uninstall" strCancelButtonText="Cancel"
        strMiddleButtonText={prefix ? "Uninstall + delete prefix" : undefined}
        onMiddleButton={prefix ? async () => { if (await removeGame(app, true)) toast(`${rec!.title} and its prefix removed`); } : undefined}
        onOK={async () => { if (await removeGame(app, false)) toast(`${rec!.title} uninstalled`); }} />,
    );
  };

  const saves = (direction: "download" | "upload") => {
    const go = () => run(direction === "download" ? "Download save" : "Upload save", async () => {
      const r = await syncSaves(app, direction);
      toast(r.ok ? r.message : r.error);
    });
    showModal(
      <ConfirmModal strTitle={direction === "download" ? "Download your cloud save?" : "Upload this save to Epic?"}
        strDescription={direction === "download"
          ? "Replaces the save on this handheld with the one in your Epic account."
          : "Replaces the save in your Epic account with the one on this handheld."}
        strOKButtonText={direction === "download" ? "Download" : "Upload"} strCancelButtonText="Cancel" onOK={go} />,
    );
  };

  let actions: ReactNode;
  if (job) {
    actions = (
      <>
        <div className="ep-row" style={{ justifyContent: "space-between" }}>
          <span className="k">{job.action === "update" ? "Updating" : job.action === "repair" ? "Repairing" : "Installing"}</span>
          <span className="v" style={{ fontFamily: "monospace" }}>{jobLine(job)}</span>
        </div>
        <Bar value={job.phase === "downloading" && job.total ? job.done / job.total : job.phase === "queued" ? 0 : 1}
          color={job.phase === "downloading" ? C.data : C.active} />
        <Focusable className="ep-row" flow-children="row">
          <DialogButton className="ep-btn" onClick={() => cancelJob(app)}>{job.phase === "queued" ? "Remove from queue" : "Pause"}</DialogButton>
        </Focusable>
        {job.phase !== "queued" && <div style={{ fontSize: 12, color: C.text1 }}>Pausing keeps what's downloaded; Install continues from there.</div>}
      </>
    );
  } else if (rec) {
    actions = (
      <Focusable className="ep-row" flow-children="row">
        {inSteam && rec.present && <DialogButton className="ep-btn primary" onClick={() => openInSteam(rec.appid)}>Play</DialogButton>}
        {!inSteam && rec.present && <DialogButton className="ep-btn primary" disabled={!!busy} onClick={() => run("Add to Steam", async () => {
          const a = await addToSteam(app, true); if (a) toast(`${rec.title} added to Steam`);
        })}>{busy === "Add to Steam" ? "Adding…" : "Add to Steam"}</DialogButton>}
        {rec.update && <DialogButton className="ep-btn" onClick={() => startInstall(app)}>Update{rec.latest ? ` · ${rec.latest}` : ""}</DialogButton>}
        {(!rec.present || rec.verify) && <DialogButton className="ep-btn" onClick={() => startInstall(app, true)}>Repair</DialogButton>}
        <DialogButton className="ep-btn" onClick={uninstall}>Uninstall</DialogButton>
      </Focusable>
    );
  } else if (!game) {
    actions = <div className="v" style={{ color: C.text1 }}>Loading…</div>;
  } else if (!game.installable) {
    actions = <div className="v" style={{ color: C.warn }}>{game.third_party
      ? `${game.title} is installed and launched through ${game.third_party}, which this plugin doesn't run.`
      : "Epic has no Windows build of this for your account (it may be a pre-order, a tool or a web-only game)."}</div>;
  } else {
    actions = (
      <>
        <Focusable className="ep-row" flow-children="row">
          <DialogButton className="ep-btn primary" onClick={() => startInstall(app)}>
            {resume ? "Resume install" : "Install"}{size?.disk ? ` · ${fmtBytes(size.disk)}` : ""}
          </DialogButton>
          {resume && <DialogButton className="ep-btn" disabled={!!busy} onClick={() => run("Discard", async () => {
            const r = await discard(app); if (!r.ok) toast(r.error); else { toast("Paused download removed"); setResume(false); }
          })}>Discard download</DialogButton>}
          <span style={{ fontSize: 12, color: C.text1 }}>
            Windows build · runs with Proton{size?.download ? ` · ${fmtBytes(size.download)} download` : ""}{s.settings?.dlcs && game.dlcs ? ` · includes your DLC` : ""}
          </span>
        </Focusable>
        <div style={{ fontSize: 12, color: C.text1 }}>Installs to {s.settings?.root}</div>
      </>
    );
  }

  return (
    <Shell title={game?.title ?? ""}>
      {!game && !error ? <SteamSpinner background="transparent" /> : !game ? (
        <div className="ep-msg err">{error}<div style={{ marginTop: 16 }}><DialogButton className="ep-btn" onClick={() => Navigation.NavigateBack()}>Back</DialogButton></div></div>
      ) : (
        <div className="ep-detail">
          <Cover url={game.tall || game.wide} />
          <Focusable className="info" flow-children="column">
            <h1>{game.title}</h1>
            <div className="ep-row">
              {game.developer && <span className="by">by {game.developer}</span>}
              {game.cloud_saves && <Chip color={C.data}>CLOUD SAVES</Chip>}
              {game.dlcs > 0 && <Chip>{`${game.dlcs} DLC`}</Chip>}
            </div>
            {game.description && <div className="short">{game.description}</div>}
            <div className="ep-panel">{actions}</div>
            {rec && !job && (
              <div className="ep-panel">
                {!rec.present && <div style={{ color: C.warn, fontSize: 13 }}>The game's folder is missing (SD card out, or deleted). Repair downloads it again, or uninstall it.</div>}
                {rec.verify && rec.present && <div style={{ color: C.warn, fontSize: 13 }}>Legendary flagged this install for a check. Repair verifies the files and fixes broken ones.</div>}
                <div className="ep-kv">
                  <span className="k">Version</span><span className="v">{rec.version}{rec.update ? ` → ${rec.latest}` : ""}</span>
                  <span className="k">Runs</span><span className="v">{`Proton${s.settings?.tool ? ` (${s.settings.tool})` : ""}${rec.offline ? " · can play offline" : ""}`}</span>
                  <span className="k">Folder</span><span className="v">{rec.dir}</span>
                  <span className="k">Size</span><span className="v">{fmtBytes(rec.size)}</span>
                </div>
                <Focusable className="ep-row" flow-children="row">
                  {inSteam && <DialogButton className="ep-btn" disabled={!!busy} onClick={() => run("Artwork", async () => {
                    await applyArt(game, rec.appid); toast("Artwork refreshed");
                  })}>{busy === "Artwork" ? "Drawing…" : "Redo artwork"}</DialogButton>}
                  {inSteam && <DialogButton className="ep-btn" disabled={!!busy} onClick={() => run("Steam shortcut", async () => {
                    await addToSteam(app, false); await refreshInstalled(); toast("Steam shortcut refreshed");
                  })}>Fix Steam shortcut</DialogButton>}
                  {rec.present && !rec.verify && <DialogButton className="ep-btn" onClick={() => startInstall(app, true)}>Verify files</DialogButton>}
                </Focusable>
                {game.cloud_saves && inSteam && (
                  <>
                    <span className="k">Epic cloud saves</span>
                    <Focusable className="ep-row" flow-children="row">
                      <DialogButton className="ep-btn" disabled={!!busy} onClick={() => saves("download")}>{busy === "Download save" ? "Downloading…" : "Download save"}</DialogButton>
                      <DialogButton className="ep-btn" disabled={!!busy} onClick={() => saves("upload")}>{busy === "Upload save" ? "Uploading…" : "Upload save"}</DialogButton>
                    </Focusable>
                    <div style={{ fontSize: 12, color: C.text1 }}>Bring your Epic save here before playing a game you started elsewhere, and upload after playing to continue on another PC.</div>
                  </>
                )}
              </div>
            )}
          </Focusable>
        </div>
      )}
    </Shell>
  );
}

export function OfferPage() {
  const s = useStore();
  const it = s.offer;
  const [busy, setBusy] = useState(false);
  if (!it) {
    return <Shell title=""><div className="ep-msg">Nothing selected.<div style={{ marginTop: 16 }}>
      <DialogButton className="ep-btn" onClick={() => Navigation.NavigateBack()}>Back</DialogButton></div></div></Shell>;
  }
  const mine = ownedByNs(it.ns);
  const got = async () => {
    setBusy(true);
    try {
      await loadLibrary(true);
      const g = ownedByNs(it.ns);
      if (g) { toast(`${g.title} is in your library`); Navigation.Navigate(gamePath(g.app)); }
      else toast(`${it.title} isn't in your Epic library yet. It can take a minute after claiming.`);
    } finally { setBusy(false); }
  };
  const verb = it.free ? "Get" : "Buy";
  const claimable = !!it.free && !!it.checkout;
  const openWeb = (url: string) => { Navigation.CloseSideMenus(); Navigation.NavigateToExternalWeb(url); };
  return (
    <Shell title={it.title}>
      <div className="ep-detail">
        <Cover url={it.tall || it.wide} />
        <Focusable className="info" flow-children="column">
          <h1>{it.title}</h1>
          <div className="ep-row">
            {it.seller && <span className="by">by {it.seller}</span>}
            {it.controller && <Chip color={C.data}>CONTROLLER SUPPORT</Chip>}
            {it.released && <Chip>{it.released.slice(0, 4)}</Chip>}
          </div>
          {it.description && <div className="short">{it.description}</div>}
          <div className="ep-panel">
            {mine ? (
              <Focusable className="ep-row" flow-children="row">
                <DialogButton className="ep-btn primary" onClick={() => Navigation.Navigate(gamePath(mine.app))}>Open in library</DialogButton>
              </Focusable>
            ) : (
              <>
                <div className="ep-row" style={{ justifyContent: "space-between" }}>
                  <span className="k">Price</span>
                  <span className="v" style={{ fontFamily: "monospace", color: it.free ? C.ok : C.accent }}>
                    {it.price || "See store"}{it.sale > 0 && it.original ? `  (was ${it.original}, -${it.sale}%)` : ""}{it.until ? ` until ${it.until}` : ""}
                  </span>
                </div>
                <Focusable className="ep-row" flow-children="row">
                  {claimable ? <>
                    <DialogButton className="ep-btn primary" onClick={() => openWeb(it.checkout)}>Claim free</DialogButton>
                    <DialogButton className="ep-btn" onClick={() => showModal(<BuyQr url={it.checkout} title={it.title} onBought={got} />)}>Claim on phone</DialogButton>
                    <DialogButton className="ep-btn" onClick={() => openWeb(it.url)}>Store page</DialogButton>
                  </> : <>
                    <DialogButton className="ep-btn primary" onClick={() => openWeb(it.url)}>{verb} on Epic</DialogButton>
                    <DialogButton className="ep-btn" onClick={() => showModal(<BuyQr url={it.url} title={it.title} onBought={got} />)}>{verb} on phone</DialogButton>
                  </>}
                  <DialogButton className="ep-btn" disabled={busy} onClick={got}>{busy ? "Checking…" : "I got it"}</DialogButton>
                </Focusable>
                <div style={{ fontSize: 12, color: C.text1 }}>
                  {claimable
                    ? "Claim free opens Epic's checkout for this game in Steam's browser: sign in to Epic there once and press Place Order (it's free, nothing is charged). Epic may ask you to solve a captcha. "
                    : it.free ? "Free games still have to be claimed on Epic's store page (sign in there with your Epic account). " : "Buy it on the game's Epic store page with your Epic account. "}
                  Then press I got it: it moves to your library and installs from there.
                </div>
              </>
            )}
          </div>
        </Focusable>
      </div>
    </Shell>
  );
}
