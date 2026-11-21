/*
 * Sign-in without typing. First choice: Epic's device code. The QR opens epicgames.com/activate
 * with the code filled in, you sign in there and approve, and this screen continues by itself; the
 * phone never talks to the handheld, so Wi-Fi and firewalls don't matter. Second choice: the
 * one-time page on the handheld's own address, where you paste the code Epic shows. Typing the code
 * on the handheld works too.
 */
import { DialogButton, Focusable, TextField } from "@decky/ui";
import { useEffect, useState } from "react";
import { loadLibrary, loadSettings } from "./actions";
import { DeviceStatus, deviceStart, deviceStatus, deviceStop, handoffStart, handoffStatus, handoffStop, signIn } from "./backend";
import { PhoneLink, Qr as QrCode, within } from "./phone";
import { changed, state } from "./state";

export function Qr({ text }: { text: string }) {
  return <QrCode text={text} prefix="ep" />;
}

const dim = { color: "var(--ng-text-1, #8B98A9)", fontSize: 13 } as const;
const warn = { color: "var(--ng-warn, #FF9F1C)", fontSize: 13 } as const;

async function afterSignIn() {
  await loadSettings(); state.games = null; changed(); await loadLibrary(true);
}

/** Epic's device-code sign-in: QR to epicgames.com/activate, polled until approved. */
function DeviceCode() {
  const [st, setSt] = useState<DeviceStatus | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    let poll = 0;
    setSt(null);
    within(deviceStart(), 25000, "Epic sign-in").then((r) => {
      if (!live) return;
      setSt(r);
      if (r.state !== "waiting") return;
      poll = window.setInterval(async () => {
        const s = await deviceStatus().catch(() => null);
        if (!live || !s) return;
        setSt(s);
        if (s.state === "done" || s.state === "error" || s.state === "expired") window.clearInterval(poll);
        if (s.state === "done" && !state.settings?.signedIn) await afterSignIn().catch(() => {});
      }, 2500);
    }).catch((e) => live && setSt({ ok: false, state: "error", code: "", url: "", expires: 0, error: e instanceof Error ? e.message : String(e), message: "" }));
    return () => { live = false; window.clearInterval(poll); deviceStop().catch(() => {}); };
  }, [attempt]);

  const failed = st && (st.state === "error" || st.state === "expired");
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, alignItems: "center" }}>
      {st?.url && !failed ? <Qr text={st.url} /> : <div className="ep-qr" style={{ width: 240, height: 240, background: "#0D0F14" }} />}
      {st?.code && !failed && (
        <div className="ep-code" style={{ fontSize: 22, letterSpacing: "0.18em", fontWeight: 700 }}>{st.code}</div>
      )}
      <div style={{ ...dim, maxWidth: 280, textAlign: "center" }}>
        {!st ? "Asking Epic for a code…"
          : st.state === "waiting" ? <>Scan with your phone, or open <b>epicgames.com/activate</b> on any device and enter the code. Any network works.</>
          : st.state === "finishing" ? "Approved. Signing in…"
          : st.state === "done" ? (st.message || "Signed in.")
          : null}
      </div>
      {failed && (
        <>
          <div style={{ ...warn, maxWidth: 280, textAlign: "center" }}>{st?.error || "That didn't work."}</div>
          <Focusable flow-children="row">
            <DialogButton className="ep-btn" style={{ width: "auto", minWidth: 0 }} onClick={() => setAttempt((n) => n + 1)}>New code</DialogButton>
          </Focusable>
        </>
      )}
    </div>
  );
}

export function SignIn() {
  const [mode, setMode] = useState<"device" | "page">("device");
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await within(signIn(draft), 75000, "Epic sign-in");
      setMsg(r.message);
      if (r.ok) { state.settings = r.settings; setDraft(""); changed(); await loadLibrary(true); }
    } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };

  return (
    <div className="ep-signin">
      {mode === "device" ? <DeviceCode /> : (
        <PhoneLink prefix="ep" start={handoffStart} status={handoffStatus} stop={handoffStop} waitingFor="the code"
          signedIn={() => !!state.settings?.signedIn} onSignedIn={afterSignIn} />
      )}
      <div className="ep-steps">
        <div><b>Sign in to Epic with your phone</b></div>
        {mode === "device" ? (
          <ol>
            <li>Scan the code with your phone. It opens Epic's own activation page with the code filled in.</li>
            <li>Sign in to Epic there and press <b>Confirm</b>.</li>
            <li>This screen continues by itself.</li>
          </ol>
        ) : (
          <ol>
            <li>Scan the code with your phone (same Wi-Fi as this handheld).</li>
            <li>On that page, tap <b>Epic Games sign-in</b> and sign in on Epic's own site.</li>
            <li>Epic shows a short text with an <b>authorizationCode</b>. Copy it, paste it on the page and press <b>Send to handheld</b>. This screen continues by itself.</li>
          </ol>
        )}
        <div style={dim}>
          Your password only goes to Epic. The sign-in stays on this handheld (in the plugin's settings folder) until you sign out.
        </div>
        <Focusable className="ep-row" flow-children="row">
          <DialogButton className="ep-btn" onClick={() => setMode((m) => (m === "device" ? "page" : "device"))}>
            {mode === "device" ? "Paste a code from my phone instead" : "Back to the activation code"}
          </DialogButton>
          <DialogButton className="ep-btn" onClick={() => setTyping((v) => !v)}>{typing ? "Hide" : "Type the code instead"}</DialogButton>
        </Focusable>
        {typing && (
          <Focusable style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 520 }}>
            <div style={dim}>
              Open <span className="ep-code">epicgames.com/id/api/redirect?clientId=34a02cf8f4414e29b15921876da36f9a&amp;responseType=code</span> on
              any device where you're signed in to Epic and type the 32-character authorizationCode here.
            </div>
            <TextField label="Authorization code" value={draft} onChange={(e) => setDraft(e.target.value)} />
            <DialogButton className="ep-btn primary" disabled={busy || draft.trim().length < 32} onClick={save}>
              {busy ? "Checking…" : "Sign in"}
            </DialogButton>
          </Focusable>
        )}
        {msg && <div style={warn}>{msg}</div>}
      </div>
    </div>
  );
}
