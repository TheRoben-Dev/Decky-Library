/*
 * Store details for a game page: screenshots, itch.io's info panel, rating and description, from
 * the game's public itch.io page. Loaded after the page itself (one request, cached a day).
 */
import { DialogButton, Focusable, ModalRoot, Navigation, showModal } from "@decky/ui";
import { Fragment, useEffect, useState } from "react";
import { getStorePage, StorePage } from "./backend";
import { C, MONO } from "./ui";

export const DETAILS_CSS = `
.il-shots { flex-shrink: 0; position: relative; z-index: 1; display: flex; gap: 10px; overflow-x: auto; padding: 4px 2px 8px; scroll-snap-type: x mandatory; }
.il-shot { flex: 0 0 auto; height: 150px; aspect-ratio: 16 / 9; border: 1px solid ${C.line}; background: ${C.bg1}; scroll-snap-align: start; }
.il-shot img { width: 100%; height: 100%; object-fit: cover; display: block; }
.il-shot.il-focus, .il-shot.gpfocus { border-color: ${C.active}; box-shadow: 0 0 14px color-mix(in srgb, ${C.active} 45%, transparent); }
.il-desc { font-size: 14px; line-height: 1.55; color: ${C.text0}; display: flex; flex-direction: column; gap: 8px; }
.il-desc h3 { margin: 6px 0 0; font-family: ${MONO}; font-size: 14px; letter-spacing: .06em; text-transform: uppercase; color: ${C.data}; }
.il-desc p { margin: 0; opacity: .9; }
.il-desc li { margin-left: 18px; opacity: .9; }
.il-desc img { max-width: 100%; max-height: 360px; object-fit: contain; align-self: flex-start; }
.il-desc .fade { position: relative; max-height: 260px; overflow: hidden; }
.il-desc .fade::after { content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 60px; background: linear-gradient(transparent, ${C.bg1}); }
.il-viewer { display: flex; flex-direction: column; align-items: center; gap: 10px; background: ${C.bg0}; padding: 12px; position: relative; z-index: 10; }
.il-viewer img { max-width: 100%; max-height: 70vh; object-fit: contain; }
`;

function Viewer({ shots, start, closeModal }: { shots: string[]; start: number; closeModal?: () => void }) {
  const [i, setI] = useState(start);
  const go = (d: number) => setI((n) => (n + d + shots.length) % shots.length);
  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      {/* Modals render outside the page's stylesheet, so everything here is styled inline. */}
      <Focusable className="il-viewer" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10,
        background: C.bg0, padding: 12, position: "relative", zIndex: 10 }}>
        <img src={shots[i]} draggable={false}
          style={{ display: "block", maxWidth: "100%", maxHeight: "68vh", objectFit: "contain", background: "#000" }} />
        <div style={{ fontSize: 12, color: C.text1 }}>{i + 1} / {shots.length}</div>
        <Focusable flow-children="row" style={{ display: "flex", gap: 8 }}>
          <DialogButton className="il-btn" style={{ width: "auto", minWidth: 0, padding: "6px 16px" }} onClick={() => go(-1)}>Previous</DialogButton>
          <DialogButton className="il-btn" style={{ width: "auto", minWidth: 0, padding: "6px 16px" }} onClick={() => go(1)}>Next</DialogButton>
          <DialogButton className="il-btn" style={{ width: "auto", minWidth: 0, padding: "6px 16px" }} onClick={closeModal}>Close</DialogButton>
        </Focusable>
      </Focusable>
    </ModalRoot>
  );
}

export function StoreDetails({ gameId, url }: { gameId: number; url: string }) {
  const [p, setP] = useState<StorePage | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [more, setMore] = useState(false);

  useEffect(() => {
    let live = true;
    setP(null); setErr(null);
    getStorePage(gameId).then((r) => { if (live) r.ok ? setP(r) : setErr(r.error); }).catch((e) => live && setErr(String(e)));
    return () => { live = false; };
  }, [gameId]);

  if (err) return (
    <div className="il-panel" style={{ color: C.text1, fontSize: 13 }}>
      Store details couldn't be loaded: {err}
      {url && <Focusable flow-children="row"><DialogButton className="il-btn" style={{ width: "auto" }}
        onClick={() => Navigation.NavigateToExternalWeb(url)}>Open the page on itch.io</DialogButton></Focusable>}
    </div>
  );
  if (!p) return <div className="il-panel" style={{ color: C.text1, fontSize: 13 }}>Loading store details…</div>;

  const desc = p.description;
  const long = desc.length > 8;
  const shown = long && !more ? desc.slice(0, 8) : desc;
  return (
    <>
      {p.screenshots.length > 0 && (
        <Focusable className="il-shots" flow-children="row">
          {p.screenshots.map((src, i) => (
            <Focusable key={src} className="il-shot" focusClassName="il-focus" onActivate={() => showModal(<Viewer shots={p.screenshots} start={i} />)}
              onClick={() => showModal(<Viewer shots={p.screenshots} start={i} />)} onOKActionDescription="View">
              <img src={src} loading="lazy" decoding="async" draggable={false} />
            </Focusable>
          ))}
        </Focusable>
      )}
      {(p.info.length > 0 || p.rating.value) && (
        <div className="il-panel">
          <div className="il-kv">
            {p.rating.value ? <><span className="k">Rating</span><span className="v" style={{ wordBreak: "normal" }}>
              {"★".repeat(Math.round(p.rating.value))}{"☆".repeat(5 - Math.round(p.rating.value))} {p.rating.value.toFixed(1)}
              {p.rating.count ? ` (${p.rating.count})` : ""}</span></> : null}
            {p.info.filter(([k]) => k !== "Rating").map(([k, v]) => (
              <Fragment key={k}><span className="k">{k}</span><span className="v" style={{ wordBreak: "normal" }}>{v}</span></Fragment>
            ))}
          </div>
          {p.video && <Focusable flow-children="row"><DialogButton className="il-btn" style={{ width: "auto" }}
            onClick={() => Navigation.NavigateToExternalWeb(p.video)}>Watch trailer</DialogButton></Focusable>}
        </div>
      )}
      {desc.length > 0 && (
        <div className="il-panel il-desc">
          <div className={long && !more ? "fade" : ""}>
            {shown.map((b, i) => b.t === "img" ? <img key={i} src={b.src} loading="lazy" decoding="async" draggable={false} />
              : b.t === "h" ? <h3 key={i}>{b.text}</h3> : b.t === "li" ? <li key={i}>{b.text}</li> : <p key={i}>{b.text}</p>)}
          </div>
          {long && <Focusable flow-children="row"><DialogButton className="il-btn" style={{ width: "auto" }}
            onClick={() => setMore((v) => !v)}>{more ? "Show less" : "Read more"}</DialogButton></Focusable>}
        </div>
      )}
      {p.stale && <div style={{ color: C.text1, fontSize: 11 }}>Showing a saved copy; itch.io isn't answering right now.</div>}
    </>
  );
}
