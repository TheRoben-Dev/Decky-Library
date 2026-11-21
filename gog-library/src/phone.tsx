/*
 * Phone sign-in link, shared by the store plugins (same file in each; only `prefix` differs).
 * Shows the QR code for the handheld's one-time sign-in page and says what's happening: waiting,
 * phone connected, expired (with a new code), or that the firewall blocks the page (with the
 * one command that fixes it). The backend picks a port the firewall allows when it can.
 */
import { DialogButton, Focusable } from "@decky/ui";
import qrcode from "qrcode-generator";
import { ReactNode, useEffect, useMemo, useState } from "react";

export interface LinkStatus {
  ok: boolean; url?: string; error?: string; expires?: number;
  received?: boolean; visited?: boolean; signedIn?: boolean;
  ip?: string; port?: number; firewall?: string; zone?: string; blocked?: boolean; fix?: string;
}

const C = { ok: "var(--ng-ok, #2BFF88)", warn: "var(--ng-warn, #FF9F1C)", dim: "var(--ng-text-1, #8B98A9)", data: "var(--ng-data, #00E5FF)" };

export function within<T>(p: Promise<T>, ms: number, what: string): Promise<T> {
  return new Promise<T>((ok, fail) => {
    const t = setTimeout(() => fail(new Error(`${what} didn't answer in ${Math.round(ms / 1000)} s. Restart Decky and try again.`)), ms);
    p.then((v) => { clearTimeout(t); ok(v); }, (e) => { clearTimeout(t); fail(e); });
  });
}

export function Qr({ text, prefix = "ng", size = 240 }: { text: string; prefix?: string; size?: number }) {
  const svg = useMemo(() => {
    const q = qrcode(0, "M");
    q.addData(text);
    q.make();
    return q.createSvgTag({ cellSize: 4, margin: 0, scalable: true });
  }, [text]);
  // Inline styles too, so it also renders inside modals (outside the page's stylesheet).
  return <div className={`${prefix}-qr`} style={{ background: "#fff", padding: 14, lineHeight: 0, width: size, height: size, boxSizing: "content-box" }}
    dangerouslySetInnerHTML={{ __html: svg.replace("<svg ", `<svg style="width:${size}px;height:${size}px;display:block" `) }} />;
}

function Note({ color, children }: { color: string; children: ReactNode }) {
  return <div style={{ color, fontSize: 13, maxWidth: 280, textAlign: "center", lineHeight: 1.4 }}>{children}</div>;
}

function Fix({ prefix, cmd }: { prefix: string; cmd: string }) {
  return <div className={`${prefix}-code`} style={{ fontSize: 11, maxWidth: 280, wordBreak: "break-all", userSelect: "text" }}>{cmd}</div>;
}

/**
 * start/status/stop: the plugin's handoff_* callables. onSignedIn runs when the backend reports a
 * sign-in that the screen hasn't seen yet (backup for the sign-in event). waitingFor names what the
 * phone sends ("the key", "the code").
 */
export function PhoneLink({ prefix, start, status, stop, signedIn, onSignedIn, waitingFor }: {
  prefix: string;
  start: () => Promise<LinkStatus>;
  status: () => Promise<LinkStatus>;
  stop: () => Promise<unknown>;
  signedIn: () => boolean;
  onSignedIn: () => Promise<unknown>;
  waitingFor: string;
}) {
  const [st, setSt] = useState<LinkStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [slow, setSlow] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    let poll = 0;
    setSt(null); setErr(null); setSlow(false);
    within(start(), 20000, "The phone sign-in page").then((r) => {
      if (!live) return;
      if (!r.ok || !r.url) { setErr(r.error || "Couldn't open the phone sign-in page."); return; }
      setSt(r);
      const began = Date.now();
      poll = window.setInterval(async () => {
        const s = await status().catch(() => null);
        if (!live || !s) return;
        if (s.signedIn && !signedIn()) { window.clearInterval(poll); await onSignedIn().catch(() => {}); return; }
        if (!s.ok && !s.received) { window.clearInterval(poll); setSt(null); setErr("The sign-in code expired."); return; }
        setSt((old) => ({ ...(old ?? {}), ...s, url: s.url || old?.url }));
        if (Date.now() - began > 25000) setSlow(true);
      }, 2500);
    }).catch((e) => live && setErr(e instanceof Error ? e.message : String(e)));
    // The page closes itself after a sign-in; leaving this screen closes it too.
    return () => { live = false; window.clearInterval(poll); stop().catch(() => {}); };
  }, [attempt]);

  const url = st?.url;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, alignItems: "center" }}>
      {url ? <Qr text={url} prefix={prefix} /> : <div className={`${prefix}-qr`} style={{ width: 240, height: 240, background: "#0D0F14" }} />}
      <div className={`${prefix}-code`} style={{ maxWidth: 280, textAlign: "center", wordBreak: "break-all" }}>{url ?? err ?? "Opening…"}</div>
      {err && (
        <Focusable flow-children="row">
          <DialogButton className={`${prefix}-btn`} style={{ width: "auto", minWidth: 0 }} onClick={() => setAttempt((n) => n + 1)}>New code</DialogButton>
        </Focusable>
      )}
      {url && st?.visited && <Note color={C.ok}>Phone connected. Waiting for {waitingFor}…</Note>}
      {url && !st?.visited && st?.blocked && (
        <>
          <Note color={C.warn}>
            This handheld's firewall blocks the page, so your phone can't open it. Use a way on the right, or allow it once
            in Desktop Mode (Konsole) with:
          </Note>
          <Fix prefix={prefix} cmd={st.fix || ""} />
        </>
      )}
      {url && !st?.visited && !st?.blocked && !slow && (
        <Note color={C.dim}>Scan with your phone's camera. It must be on the same Wi-Fi.</Note>
      )}
      {url && !st?.visited && !st?.blocked && slow && (
        <>
          <Note color={C.warn}>
            Page not opening on your phone? Make sure it's on the same Wi-Fi as this handheld (not mobile data or a guest
            network, which keeps devices apart).{st?.fix ? " If it still won't open, a firewall may be blocking it. Allow it once in Desktop Mode (Konsole) with:" : ""}
          </Note>
          {st?.fix && <Fix prefix={prefix} cmd={st.fix} />}
        </>
      )}
      {url && (
        <Note color={C.dim}>
          Your phone may label the page "Not secure". That's normal for a page on your own Wi-Fi: it comes straight from this
          handheld, never goes through the internet, and closes after you sign in.
        </Note>
      )}
    </div>
  );
}
