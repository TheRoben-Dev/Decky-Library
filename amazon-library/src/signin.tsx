/*
 * Sign-in without typing: a QR code opens a one-time page on the handheld's own address. On the
 * phone you follow the Amazon sign-in link from that page, sign in, and paste the amazon.com
 * address you land on back into it. Pasting the address here works too (keyboard fallback).
 */
import { DialogButton, Focusable, TextField } from "@decky/ui";
import qrcode from "qrcode-generator";
import { useEffect, useMemo, useState } from "react";
import { loadLibrary } from "./actions";
import { handoffStart, handoffStop, setCode } from "./backend";
import { changed, state } from "./state";

export function Qr({ text }: { text: string }) {
  const svg = useMemo(() => {
    const q = qrcode(0, "M");
    q.addData(text);
    q.make();
    return q.createSvgTag({ cellSize: 4, margin: 0, scalable: true });
  }, [text]);
  // Inline styles too, so it also renders inside modals (outside the page's stylesheet).
  return <div className="al-qr" style={{ background: "#fff", padding: 14, lineHeight: 0, width: 240, height: 240, boxSizing: "content-box" }}
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
    // The page closes itself once a sign-in arrives; leaving this screen closes it too.
    return () => { live = false; handoffStop().catch(() => {}); };
  }, []);

  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await setCode(draft);
      setMsg(r.message);
      if (r.ok) { state.settings = r.settings; setDraft(""); changed(); await loadLibrary(true); }
    } finally { setBusy(false); }
  };

  return (
    <div className="al-signin">
      <div style={{ display: "flex", flexDirection: "column", gap: "10px", alignItems: "center" }}>
        {url ? <Qr text={url} /> : <div className="al-qr" style={{ width: 240, height: 240, background: "#0D0F14" }} />}
        <div className="al-code" style={{ maxWidth: 270, textAlign: "center" }}>{url ?? err ?? "Opening…"}</div>
      </div>
      <div className="al-steps">
        <div><b>Sign in with your phone</b></div>
        <ol>
          <li>Scan the code with your phone (same Wi-Fi as this handheld).</li>
          <li>Tap <b>Open Amazon sign-in</b> and sign in to the Amazon account your games are on.</li>
          <li>You land on the amazon.com home page: copy its <b>full address</b>, go back to the first tab, paste it and press <b>Send to handheld</b>.</li>
        </ol>
        <div style={{ color: "var(--ng-text-1, #8B98A9)", fontSize: 13 }}>
          This handheld is registered as an Amazon Games device, like the Windows app. Your password never touches it, and you can
          remove it any time under Amazon → Your devices. If the Amazon Shopping app grabs the link, long-press it and open it in the browser.
        </div>
        <Focusable className="al-row" flow-children="row">
          <DialogButton className="al-btn" onClick={() => setTyping((v) => !v)}>{typing ? "Hide" : "Paste the address here instead"}</DialogButton>
        </Focusable>
        {typing && (
          <Focusable style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 520 }}>
            <TextField label="amazon.com address after signing in" value={draft} onChange={(e) => setDraft(e.target.value)} />
            <DialogButton className="al-btn primary" disabled={busy || draft.trim().length < 10} onClick={save}>
              {busy ? "Checking…" : "Sign in"}
            </DialogButton>
          </Focusable>
        )}
        {msg && <div style={{ color: "var(--ng-warn, #FF9F1C)", fontSize: 13 }}>{msg}</div>}
      </div>
    </div>
  );
}
