/*
 * Sign-in without typing: a QR code opens a one-time page on the handheld's own address. On the
 * phone you sign in on Epic's own site and paste the one-time code Epic shows there. Typing the
 * code on the handheld works too.
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
  return <div className="ep-qr" style={{ background: "#fff", padding: 14, lineHeight: 0, width: 240, height: 240, boxSizing: "content-box" }}
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
    // The page closes itself once a key arrives; leaving this screen closes it too.
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
    <div className="ep-signin">
      <div style={{ display: "flex", flexDirection: "column", gap: "10px", alignItems: "center" }}>
        {url ? <Qr text={url} /> : <div className="ep-qr" style={{ width: 240, height: 240, background: "#0D0F14" }} />}
        <div className="ep-code" style={{ maxWidth: 270, textAlign: "center" }}>{url ?? err ?? "Opening…"}</div>
      </div>
      <div className="ep-steps">
        <div><b>Sign in to Epic with your phone</b></div>
        <ol>
          <li>Scan the code with your phone (same Wi-Fi as this handheld).</li>
          <li>On that page, tap <b>Epic Games sign-in</b> and sign in on Epic's own site.</li>
          <li>Epic shows a short text with an <b>authorizationCode</b>. Copy it, paste it on the page and press <b>Send to handheld</b>. This screen continues by itself.</li>
        </ol>
        <div style={{ color: "var(--ng-text-1, #8B98A9)", fontSize: 13 }}>
          Your password only goes to Epic. The code works once and only for a few minutes; the sign-in it creates stays on
          this handheld (in the plugin's settings folder) until you sign out.
        </div>
        <Focusable className="ep-row" flow-children="row">
          <DialogButton className="ep-btn" onClick={() => setTyping((v) => !v)}>{typing ? "Hide" : "Type the code instead"}</DialogButton>
        </Focusable>
        {typing && (
          <Focusable style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 520 }}>
            <div style={{ fontSize: 13, color: "var(--ng-text-1, #8B98A9)" }}>
              Open <span className="ep-code">epicgames.com/id/api/redirect?clientId=34a02cf8f4414e29b15921876da36f9a&amp;responseType=code</span> on
              any device where you're signed in to Epic and type the 32-character authorizationCode here.
            </div>
            <TextField label="Authorization code" value={draft} onChange={(e) => setDraft(e.target.value)} />
            <DialogButton className="ep-btn primary" disabled={busy || draft.trim().length < 32} onClick={save}>
              {busy ? "Checking…" : "Sign in"}
            </DialogButton>
          </Focusable>
        )}
        {msg && <div style={{ color: "var(--ng-warn, #FF9F1C)", fontSize: 13 }}>{msg}</div>}
      </div>
    </div>
  );
}
