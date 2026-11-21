/*
 * The store-page half of the game page: screenshots, trailers, facts (rating, release, genres,
 * developer, publisher, features) and the full description. Details are fetched when the page
 * opens (the backend caches them for 3 days) and kept here for the session, so going back and
 * forth costs nothing. Every block is focusable, so the D-pad scrolls through the whole page.
 */
import { DialogButton, Focusable, ModalRoot, Navigation, showModal } from "@decky/ui";
import { useEffect, useState } from "react";
import { Details, getDetails, StoreItem } from "./backend";
import { C } from "./ui";

const cache = new Map<number, Details>();
const SHORT = 5;   // paragraphs shown before "Read more"

function fmtDate(iso: string) {
  const m = iso.match(/^(\d{4})[-.](\d{2})[-.](\d{2})/);
  if (!m) return iso;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function Viewer({ shots, start, closeModal }: { shots: { full: string; thumb: string }[]; start: number; closeModal?: () => void }) {
  const [i, setI] = useState(start);
  const go = (n: number) => setI((i + n + shots.length) % shots.length);
  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      <div style={{ display: "flex", flexDirection: "column", gap: 12, alignItems: "center" }}>
        <img src={shots[i].full} style={{ maxWidth: "100%", maxHeight: "62vh", objectFit: "contain", border: `1px solid ${C.line}` }}
          onError={(e) => { const t = e.currentTarget; if (t.src !== shots[i].thumb) t.src = shots[i].thumb; }} />
        <Focusable style={{ display: "flex", gap: 8, alignItems: "center" }} flow-children="row">
          <DialogButton style={{ minWidth: 0, width: "auto", padding: "6px 18px" }} onClick={() => go(-1)}>◀ Previous</DialogButton>
          <span style={{ fontFamily: "monospace", fontSize: 12, color: C.text1, padding: "0 8px" }}>{i + 1} / {shots.length}</span>
          <DialogButton style={{ minWidth: 0, width: "auto", padding: "6px 18px" }} onClick={() => go(1)}>Next ▶</DialogButton>
          <DialogButton style={{ minWidth: 0, width: "auto", padding: "6px 18px" }} onClick={() => closeModal?.()}>Close</DialogButton>
        </Focusable>
      </div>
    </ModalRoot>
  );
}

function Fact({ k, v }: { k: string; v?: string | null }) {
  if (!v) return null;
  return <><span className="k">{k}</span><span className="v">{v}</span></>;
}

export function StoreDetails({ id, item }: { id: number; item?: StoreItem }) {
  const [d, setD] = useState<Details | null>(() => cache.get(id) ?? null);
  const [err, setErr] = useState<string | null>(null);
  const [shot, setShot] = useState(0);
  const [more, setMore] = useState(false);

  useEffect(() => {
    let live = true;
    setShot(0); setMore(false);
    if (cache.has(id)) { setD(cache.get(id)!); return; }
    setD(null); setErr(null);
    getDetails(id).then((r) => {
      if (!live) return;
      if (!r.ok) { setErr(r.error); return; }
      cache.set(id, r);
      setD(r);
    }).catch((e) => live && setErr(String(e)));
    return () => { live = false; };
  }, [id]);

  if (!d) return <div className="gl-panel"><span className="k">{err ? `Store details unavailable: ${err}` : "Loading store page…"}</span></div>;

  const shots = d.screenshots;
  const rating = item?.rating ? `${(item.rating / 10).toFixed(1)} / 5${item.reviews ? ` · ${item.reviews.toLocaleString()} reviews` : ""}`
    : d.rating != null ? `${d.rating} / 100 (critics)` : "";
  const genres = (d.genres.length ? d.genres : item?.genres ?? []).slice(0, 5).join(", ");
  const features = (item?.features ?? []).join(", ");
  const paras = more ? d.description : d.description.slice(0, SHORT);

  return (
    <>
      {shots.length > 0 && (
        <div className="gl-panel gl-gallery">
          <div className="main">
            <img src={shots[Math.min(shot, shots.length - 1)].full} draggable={false}
              onError={(e) => { const s = shots[Math.min(shot, shots.length - 1)]; if (e.currentTarget.src !== s.thumb) e.currentTarget.src = s.thumb; }} />
          </div>
          <Focusable className="thumbs" flow-children="row">
            {shots.map((s, i) => (
              <Focusable key={s.full} className={`thumb${i === shot ? " on" : ""}`} focusClassName="gl-focus"
                onFocus={() => setShot(i)} onActivate={() => showModal(<Viewer shots={shots} start={i} />)}
                onOKActionDescription="View">
                <img src={s.thumb} loading="lazy" decoding="async" draggable={false}
                  onError={(e) => { if (e.currentTarget.src !== s.full) e.currentTarget.src = s.full; }} />
              </Focusable>
            ))}
          </Focusable>
        </div>
      )}
      <div className="gl-panel">
        <div className="gl-kv">
          <Fact k="Rating" v={rating} />
          <Fact k="Released" v={d.released ? fmtDate(d.released) : item?.released ? fmtDate(item.released) : ""} />
          <Fact k="Genres" v={genres} />
          <Fact k="Developer" v={d.developers.join(", ") || item?.developer} />
          <Fact k="Publisher" v={d.publishers.join(", ") || item?.publisher} />
          <Fact k="Modes" v={d.modes.join(", ")} />
          <Fact k="Features" v={features} />
          <Fact k="Languages" v={d.languages ? String(d.languages) : ""} />
          <Fact k="Tags" v={(item?.tags ?? []).slice(0, 6).join(", ") || d.themes.slice(0, 4).join(", ")} />
        </div>
        {d.videos.length > 0 && (
          <Focusable className="gl-row" flow-children="row">
            {d.videos.map((v, i) => (
              <DialogButton key={v.url} className="gl-btn" onClick={() => { Navigation.CloseSideMenus(); Navigation.NavigateToExternalWeb(v.url); }}>
                ▶ {v.name || (d.videos.length > 1 ? `Trailer ${i + 1}` : "Trailer")}
              </DialogButton>
            ))}
          </Focusable>
        )}
      </div>
      {d.description.length > 0 && (
        <div className="gl-panel gl-about">
          <span className="k">About this game</span>
          {paras.map((p, i) => (
            <Focusable key={i} noFocusRing className={`para${p.startsWith("• ") ? " li" : ""}`} focusClassName="on" onActivate={() => {}}>
              {p}
            </Focusable>
          ))}
          {d.description.length > SHORT && (
            <Focusable className="gl-row" flow-children="row">
              <DialogButton className="gl-btn" onClick={() => setMore((m) => !m)}>{more ? "Show less" : `Read more (${d.description.length - SHORT} more)`}</DialogButton>
            </Focusable>
          )}
        </div>
      )}
    </>
  );
}
