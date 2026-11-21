/*
 * Sign-in without typing: a QR code opens a one-time page on the handheld's own address. That page
 * links to GOG's sign-in; the address GOG lands on afterwards (it holds a one-time code) is pasted
 * back there and the handheld finishes signing in. Pasting the address here also works.
 */
import { DialogButton, Focusable, TextField } from "@decky/ui";
import qrcode from "qrcode-generator";
import { useEffect, useMemo, useState } from "react";
import { loadLibrary } from "./actions";
import { handoffStart, handoffStop, signIn } from "./backend";
import { changed, state } from "./state";

export function Qr({ text }: { text: string }) {
  const svg = useMemo(() => {
    const q = qrcode(0, "M");
    q.addData(text);
    q.make();
    return q.createSvgTag({ cellSize: 4, margin: 0, scalable: true });
  }, [text]);
  // Inline styles too, so it also renders inside modals (outside the page's stylesheet).
  return <div className="gl-qr" style={{ background: "#fff", padding: 14, lineHeight: 0, width: 240, height: 240, boxSizing: "content-box" }}
    dangerouslySetInnerHTML={{ __html: svg.replace("<svg ", '<svg style="width:240px;height:240px;display:block" ') }} />;
}

export function SignIn() {
  const [url, setUrl] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    handoffStart().then((r) => {
      if (!live) return;
      if (r.ok && r.url) setUrl(r.url); else setErr(r.error ?? "Couldn't open the phone sign-in page");
    }).catch((e) => live && setErr(String(e)));
    // The page closes itself once signed in; leaving this screen closes it too.
    return () => { live = false; handoffStop().catch(() => {}); };
  }, []);

  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await signIn(draft);
      setMsg(r.message);
      if (r.ok) { state.settings = r.settings; setDraft(""); changed(); await loadLibrary(true); }
    } finally { setBusy(false); }
  };

  return (
    <div className="gl-signin">
      <div style={{ display: "flex", flexDirection: "column", gap: "10px", alignItems: "center" }}>
        {url ? <Qr text={url} /> : <div className="gl-qr" style={{ width: 240, height: 240, background: "#0D0F14" }} />}
        <div className="gl-code" style={{ maxWidth: 270, textAlign: "center" }}>{url ?? err ?? "Opening…"}</div>
      </div>
      <div className="gl-steps">
        <div><b>Sign in with your phone</b></div>
        <ol>
          <li>Scan the code with your phone (same Wi-Fi as this handheld).</li>
          <li>Tap <b>Sign in to GOG</b> and sign in there as usual (your password manager works; it never reaches this handheld).</li>
          <li>GOG then shows a mostly empty page. Copy its address, go back to the first tab, paste it and press <b>Send to handheld</b>.
            This screen continues by itself.</li>
        </ol>
        <div style={{ color: "var(--ng-text-1, #8B98A9)", fontSize: 13 }}>
          The sign-in is GOG's own page, the same one GOG Galaxy and Heroic use. The handheld only keeps GOG's sign-in token, which it
          sends to gog.com and nowhere else.
        </div>
        <Focusable className="gl-row" flow-children="row">
          <DialogButton className="gl-btn" onClick={() => setTyping((v) => !v)}>{typing ? "Hide" : "Paste the address here instead"}</DialogButton>
        </Focusable>
        {typing && (
          <Focusable style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 520 }}>
            <TextField label="Address GOG showed after signing in (or just the code)" value={draft} onChange={(e) => setDraft(e.target.value)} />
            <DialogButton className="gl-btn primary" disabled={busy || draft.trim().length < 20} onClick={save}>
              {busy ? "Checking…" : "Sign in"}
            </DialogButton>
          </Focusable>
        )}
        {msg && <div style={{ color: "var(--ng-warn, #FF9F1C)", fontSize: 13 }}>{msg}</div>}
      </div>
    </div>
  );
}
