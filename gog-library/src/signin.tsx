/*
 * Sign-in without typing: a QR code opens a one-time page on the handheld's own address. That page
 * links to GOG's sign-in; the address GOG lands on afterwards (it holds a one-time code) is pasted
 * back there and the handheld finishes signing in. Pasting the address here also works.
 */
import { DialogButton, Focusable, TextField } from "@decky/ui";
import { useState } from "react";
import { loadLibrary, loadSettings } from "./actions";
import { handoffStart, handoffStatus, handoffStop, signIn } from "./backend";
import { PhoneLink, Qr as QrCode } from "./phone";
import { changed, state } from "./state";

export function Qr({ text }: { text: string }) {
  return <QrCode text={text} prefix="gl" />;
}

export function SignIn() {
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
      <PhoneLink prefix="gl" start={handoffStart} status={handoffStatus} stop={handoffStop} waitingFor="the address"
        signedIn={() => !!state.settings?.signedIn} onSignedIn={async () => { await loadSettings(); state.games = null; changed(); await loadLibrary(true); }} />
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
