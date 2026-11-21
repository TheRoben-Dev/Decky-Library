/*
 * Sign-in without typing: a QR code opens a one-time page on the handheld's own address; paste
 * the itch.io API key there on your phone. A key file from Desktop Mode or typing it also work.
 */
import { DialogButton, Focusable, TextField } from "@decky/ui";
import { useState } from "react";
import { loadLibrary, loadSettings } from "./actions";
import { handoffStart, handoffStatus, handoffStop, setKey, within } from "./backend";
import { PhoneLink, Qr as QrCode } from "./phone";
import { changed, state } from "./state";

export function Qr({ text }: { text: string }) {
  return <QrCode text={text} prefix="il" />;
}

export function SignIn() {
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
      <PhoneLink prefix="il" start={handoffStart} status={handoffStatus} stop={handoffStop} waitingFor="the key"
        signedIn={() => !!state.settings?.signedIn} onSignedIn={async () => { await loadSettings(); state.games = null; changed(); await loadLibrary(true); }} />
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
