/*
 * Sign-in without typing: a QR code opens a one-time page on the handheld's own address. On the
 * phone you follow the Amazon sign-in link from that page, sign in, and paste the amazon.com
 * address you land on back into it. Pasting the address here works too (keyboard fallback).
 */
import { DialogButton, Focusable, TextField } from "@decky/ui";
import { useState } from "react";
import { loadLibrary, loadSettings } from "./actions";
import { handoffStart, handoffStatus, handoffStop, setCode } from "./backend";
import { PhoneLink, Qr as QrCode } from "./phone";
import { changed, state } from "./state";

export function Qr({ text }: { text: string }) {
  return <QrCode text={text} prefix="al" />;
}

export function SignIn() {
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
      <PhoneLink prefix="al" start={handoffStart} status={handoffStatus} stop={handoffStop} waitingFor="the address"
        signedIn={() => !!state.settings?.signedIn} onSignedIn={async () => { await loadSettings(); state.games = null; changed(); await loadLibrary(true); }} />
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
