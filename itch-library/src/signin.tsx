/*
 * Sign-in without typing: a QR code opens a one-time page on the handheld's own address; paste
 * the itch.io API key there on your phone. A key file from Desktop Mode or typing it also work.
 */
import { DialogButton, Focusable, TextField } from "@decky/ui";
import qrcode from "qrcode-generator";
import { useEffect, useMemo, useState } from "react";
import { loadLibrary, loadSettings } from "./actions";
import { handoffStart, handoffStatus, handoffStop, setKey, within } from "./backend";
import { changed, state } from "./state";

export function Qr({ text }: { text: string }) {
  const svg = useMemo(() => {
    const q = qrcode(0, "M");
    q.addData(text);
    q.make();
    return q.createSvgTag({ cellSize: 4, margin: 0, scalable: true });
  }, [text]);
  // Inline styles too, so it also renders inside modals (outside the page's stylesheet).
  return <div className="il-qr" style={{ background: "#fff", padding: 14, lineHeight: 0, width: 240, height: 240, boxSizing: "content-box" }}
    dangerouslySetInnerHTML={{ __html: svg.replace("<svg ", '<svg style="width:240px;height:240px;display:block" ') }} />;
}

export function SignIn() {
  const [url, setUrl] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [visited, setVisited] = useState(false);
  const [slow, setSlow] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    let poll = 0;
    setUrl(null); setErr(null); setVisited(false); setSlow(false);
    within(handoffStart(), 15000, "The phone sign-in page").then((r) => {
      if (!live) return;
      if (!r.ok || !r.url) { setErr(r.error ?? "Couldn't open the phone sign-in page"); return; }
      setUrl(r.url);
      // Backup for the sign-in event, and to notice when the phone never reaches the page.
      const started = Date.now();
      poll = window.setInterval(async () => {
        const st = await handoffStatus().catch(() => null);
        if (!live || !st) return;
        if (st.visited) setVisited(true);
        if (st.signedIn && !state.settings?.signedIn) { await loadSettings().catch(() => {}); await loadLibrary(true); }
        else if (!st.ok && !st.received) { setUrl(null); setErr("The phone sign-in page expired."); window.clearInterval(poll); }
        if (Date.now() - started > 25000) setSlow(true);
      }, 2500);
    }).catch((e) => live && setErr(e instanceof Error ? e.message : String(e)));
    // The page closes itself once a key arrives; leaving this screen closes it too.
    return () => { live = false; window.clearInterval(poll); handoffStop().catch(() => {}); };
  }, [attempt]);

  const recheck = async () => {
    setBusy(true); setMsg(null);
    try {
      const s = await loadSettings();
      if (s.signedIn) { state.games = null; changed(); await loadLibrary(true); }
      else setMsg(s.imported || "No key file found yet.");
    } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };

  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await within(setKey(draft), 45000, "itch.io sign-in");
      setMsg(r.message);
      if (r.ok) { state.settings = r.settings; setDraft(""); changed(); await loadLibrary(true); }
    } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };

  return (
    <div className="il-signin">
      <div style={{ display: "flex", flexDirection: "column", gap: "10px", alignItems: "center" }}>
        {url ? <Qr text={url} /> : <div className="il-qr" style={{ width: 240, height: 240, background: "#0D0F14" }} />}
        <div className="il-code" style={{ maxWidth: 270, textAlign: "center" }}>{url ?? err ?? "Opening…"}</div>
        {err && <DialogButton className="il-btn" style={{ width: "auto" }} onClick={() => setAttempt((n) => n + 1)}>Try again</DialogButton>}
        {url && visited && <div style={{ color: "var(--ng-ok, #2BFF88)", fontSize: 13 }}>Phone connected. Waiting for the key…</div>}
        {url && slow && !visited && (
          <div style={{ color: "var(--ng-warn, #FF9F1C)", fontSize: 13, maxWidth: 270, textAlign: "center" }}>
            Page not loading on your phone? Check it's on the same Wi-Fi (not mobile data or a guest network). If it still
            won't open, a firewall is blocking it: use the key file or type the key instead.
          </div>
        )}
      </div>
      <div className="il-steps">
        <div><b>Sign in with your phone</b></div>
        <ol>
          <li>Scan the code with your phone (same Wi-Fi as this handheld).</li>
          <li>On that page, open <b>itch.io → Settings → API keys</b>, press <b>Generate new API key</b> and copy it.</li>
          <li>Paste it and press <b>Send to handheld</b>. This screen continues by itself.</li>
        </ol>
        <div style={{ color: "var(--ng-text-1, #8B98A9)", fontSize: 13 }}>
          Or from Desktop Mode: save the key as <span className="il-code">~/Desktop/itch-key.txt</span>, come back and press
          Check for key file. The file is removed once it's read. The key stays on this device and is only sent to itch.io.
        </div>
        <Focusable className="il-row" flow-children="row">
          <DialogButton className="il-btn" disabled={busy} onClick={recheck}>Check for key file</DialogButton>
          <DialogButton className="il-btn" onClick={() => setTyping((v) => !v)}>{typing ? "Hide" : "Type the key instead"}</DialogButton>
        </Focusable>
        {typing && (
          <Focusable style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 520 }}>
            <TextField label="itch.io API key" bIsPassword value={draft} onChange={(e) => setDraft(e.target.value)} />
            <DialogButton className="il-btn primary" disabled={busy || draft.trim().length < 20} onClick={save}>
              {busy ? "Checking…" : "Sign in"}
            </DialogButton>
          </Focusable>
        )}
        {msg && <div style={{ color: "var(--ng-warn, #FF9F1C)", fontSize: 13 }}>{msg}</div>}
      </div>
    </div>
  );
}
