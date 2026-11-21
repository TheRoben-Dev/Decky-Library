/*
 * Store-page pieces shared by the game page and the free-game page: a screenshot strip you can
 * open full screen (L1/R1 or the buttons to flip through), the description, and a details table.
 * Images come straight from Amazon's CDN; nothing is fetched until a page is opened. Modals render
 * outside the page's <style>, so the viewer is styled inline.
 */
import { DialogButton, Focusable, GamepadButton, ModalRoot, showModal } from "@decky/ui";
import { Fragment, useState } from "react";
import { Qr } from "./signin";
import { C } from "./ui";

function Viewer({ shots, start, closeModal }: { shots: string[]; start: number; closeModal?: () => void }) {
  const [i, setI] = useState(start);
  const go = (d: number) => setI((n) => (n + d + shots.length) % shots.length);
  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      <Focusable style={{ display: "flex", flexDirection: "column", gap: 12, alignItems: "center", background: "#07080b", padding: 12, margin: -12 }}
        onButtonDown={(e: any) => { const b = e?.detail?.button; if (b === GamepadButton.BUMPER_LEFT) go(-1); else if (b === GamepadButton.BUMPER_RIGHT) go(1); }}>
        <img src={shots[i]} draggable={false}
          style={{ maxWidth: "100%", maxHeight: "68vh", width: "auto", height: "auto", objectFit: "contain", display: "block", border: `1px solid ${C.data}`, background: "#000" }} />
        <Focusable className="al-row" flow-children="row" style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <DialogButton style={{ minWidth: 0, width: "auto" }} onClick={() => go(-1)} disabled={shots.length < 2}>Previous</DialogButton>
          <span style={{ fontFamily: "monospace", fontSize: 12, color: C.text1 }}>{i + 1} / {shots.length}</span>
          <DialogButton style={{ minWidth: 0, width: "auto" }} onClick={() => go(1)} disabled={shots.length < 2}>Next</DialogButton>
          <DialogButton style={{ minWidth: 0, width: "auto" }} onClick={() => closeModal?.()}>Close</DialogButton>
        </Focusable>
      </Focusable>
    </ModalRoot>
  );
}

export function Gallery({ shots }: { shots: string[] }) {
  if (!shots.length) return null;
  return (
    <div className="al-panel">
      <span className="k">Screenshots</span>
      <Focusable className="al-shots" flow-children="row">
        {shots.map((u, i) => (
          <Focusable key={u} className="al-shot" focusClassName="al-focus" onActivate={() => showModal(<Viewer shots={shots} start={i} />)}
            onClick={() => showModal(<Viewer shots={shots} start={i} />)} onOKActionDescription="View">
            <img src={u} decoding="async" draggable={false} />
          </Focusable>
        ))}
      </Focusable>
    </div>
  );
}

export function About({ text }: { text: string }) {
  const [more, setMore] = useState(false);
  if (!text) return null;
  const long = text.length > 420;
  return (
    <div className="al-panel">
      <span className="k">About this game</span>
      <div className="al-about">{long && !more ? `${text.slice(0, 400).replace(/\s+\S*$/, "")}…` : text}</div>
      {long && (
        <Focusable className="al-row" flow-children="row">
          <DialogButton className="al-btn" onClick={() => setMore((v) => !v)}>{more ? "Show less" : "Read more"}</DialogButton>
        </Focusable>
      )}
    </div>
  );
}

export interface Facts {
  developer?: string; publisher?: string; released?: string; genres?: string[]; modes?: string[]; rating?: string; website?: string;
}

function SiteQr({ url, closeModal }: { url: string; closeModal?: () => void }) {
  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      <div style={{ display: "flex", gap: 20, alignItems: "center", flexWrap: "wrap" }}>
        <Qr text={url} />
        <div style={{ fontSize: 12, color: C.data, wordBreak: "break-all", flex: 1, minWidth: 200 }}>{url}</div>
      </div>
    </ModalRoot>
  );
}

export function Details({ f }: { f: Facts }) {
  const rows: [string, string][] = [
    ["Developer", f.developer ?? ""],
    ["Publisher", f.publisher && f.publisher !== f.developer ? f.publisher : ""],
    ["Released", f.released ?? ""],
    ["Genre", (f.genres ?? []).join(", ")],
    ["Modes", (f.modes ?? []).join(", ")],
    ["Rating", f.rating ?? ""],
  ].filter((r) => r[1]) as [string, string][];
  if (!rows.length && !f.website) return null;
  return (
    <div className="al-panel">
      <span className="k">Details</span>
      <div className="al-kv">
        {rows.map(([k, v]) => <Fragment key={k}><span className="k">{k}</span><span className="v" style={{ wordBreak: "normal" }}>{v}</span></Fragment>)}
      </div>
      {f.website && (
        <Focusable className="al-row" flow-children="row">
          <DialogButton className="al-btn" onClick={() => showModal(<SiteQr url={f.website!} />)}>Official site on phone</DialogButton>
        </Focusable>
      )}
    </div>
  );
}
