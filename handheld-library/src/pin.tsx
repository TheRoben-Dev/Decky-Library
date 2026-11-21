/*
 * PIN lock for the Hidden games tab. A privacy lock, not security: the hash lives in the backend
 * (salted PBKDF2), and hidden games are still visible in Steam's own Hidden library tab unless that
 * tab is hidden too.
 */
import { DialogButton, Focusable, ModalRoot, showModal } from "@decky/ui";
import { useEffect, useState } from "react";
import { pinSet, pinStatus, pinVerify, pinClear, PinResult } from "./backend";

export const RELOCK_MS = 15 * 60 * 1000;
let unlockedAt = 0;
let pinIsSet: boolean | null = null;

export function isUnlocked(): boolean { return unlockedAt > 0 && Date.now() - unlockedAt < RELOCK_MS; }
export function lock() { unlockedAt = 0; }
function markUnlocked() { unlockedAt = Date.now(); }

/*
 * Re-lock when the device sleeps. Primary: Steam's own suspend notification
 * (SteamClient.User.RegisterForPrepareForSystemSuspendProgress, used by Steam's power code, Nov 2026).
 * Backup: JS timers stop while suspended, so a heartbeat that sees a big wall-clock jump means we slept.
 */
let suspendReg: any = null;
let heartbeat: number | undefined;
let lastBeat = 0;
const BEAT_MS = 10_000;
const SLEPT_MS = 60_000;

export function startSleepWatch() {
  try {
    suspendReg = (window as any).SteamClient?.User?.RegisterForPrepareForSystemSuspendProgress?.(() => lock()) ?? null;
  } catch (e) {
    console.warn("[Handheld Library] suspend hook unavailable; using the clock check only", e);
  }
  lastBeat = Date.now();
  heartbeat = window.setInterval(() => {
    const now = Date.now();
    if (now - lastBeat > SLEPT_MS) lock();
    lastBeat = now;
  }, BEAT_MS) as unknown as number;
}

export function stopSleepWatch() {
  try { suspendReg?.unregister?.(); } catch { /* ignore */ }
  suspendReg = null;
  if (heartbeat !== undefined) clearInterval(heartbeat);
  heartbeat = undefined;
}

export async function refreshPinSet(): Promise<boolean> {
  try { pinIsSet = (await pinStatus()).set; } catch { pinIsSet = false; }
  return pinIsSet;
}
export function knownPinSet(): boolean | null { return pinIsSet; }

const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫", "0", "OK"];

/** Controller-friendly numeric pad. Calls onSubmit with 4–8 digits. */
export function PinPad({ title, hint, error, busy, onSubmit }: {
  title: string; hint?: string; error?: string; busy?: boolean; onSubmit: (pin: string) => void;
}) {
  const [pin, setPin] = useState("");
  useEffect(() => { if (error) setPin(""); }, [error]);
  const press = (k: string) => {
    if (busy) return;
    if (k === "⌫") setPin(pin.slice(0, -1));
    else if (k === "OK") { if (pin.length >= 4) onSubmit(pin); }
    else if (pin.length < 8) setPin(pin + k);
  };
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "10px", padding: "8px 0" }}>
      <div style={{ fontSize: "15px", fontWeight: 600 }}>{title}</div>
      <div style={{ fontSize: "22px", letterSpacing: "8px", minHeight: "28px" }}>
        {pin.length ? "●".repeat(pin.length) : <span style={{ opacity: 0.4, letterSpacing: "normal", fontSize: "13px" }}>4–8 digits</span>}
      </div>
      {error && <div style={{ color: "#FF6B6B", fontSize: "12px", textAlign: "center" }}>{error}</div>}
      {hint && !error && <div style={{ fontSize: "12px", opacity: 0.7, textAlign: "center" }}>{hint}</div>}
      <Focusable style={{ display: "grid", gridTemplateColumns: "repeat(3, 64px)", gap: "6px" }} flow-children="grid">
        {KEYS.map((k) => (
          <DialogButton key={k} disabled={busy || (k === "OK" && pin.length < 4)}
            style={{ minWidth: 0, height: "44px", padding: 0, fontSize: k === "OK" ? "14px" : "18px" }}
            onClick={() => press(k)}>{k}</DialogButton>
        ))}
      </Focusable>
    </div>
  );
}

function errorFor(r: PinResult, fallback: string): string {
  if (r.retryIn) return `Too many wrong tries. Try again in ${r.retryIn} s.`;
  return r.error ?? fallback;
}

/** Lock screen used inside the Hidden games tab. */
export function LockScreen({ onUnlock }: { onUnlock: () => void }) {
  const [err, setErr] = useState<string>();
  const [busy, setBusy] = useState(false);
  return (
    <PinPad title="Hidden games are locked" hint="Enter your PIN" error={err} busy={busy}
      onSubmit={async (p) => {
        setErr(undefined);   // so the same "Wrong PIN" twice still clears the pad
        setBusy(true);
        try {
          const r = await pinVerify(p);
          if (r.ok) { markUnlocked(); onUnlock(); } else setErr(errorFor(r, "Wrong PIN."));
        } catch (e) { setErr(String(e)); }
        setBusy(false);
      }} />
  );
}

type Step = "current" | "new" | "confirm";

function PinFlow({ mode, closeModal, onDone }: { mode: "set" | "change" | "remove"; closeModal?: () => void; onDone: (msg: string) => void }) {
  const [step, setStep] = useState<Step>(mode === "set" ? "new" : "current");
  const [current, setCurrent] = useState("");
  const [first, setFirst] = useState("");
  const [err, setErr] = useState<string>();
  const [busy, setBusy] = useState(false);
  const finish = (msg: string) => { closeModal?.(); onDone(msg); };

  const submit = async (p: string) => {
    setErr(undefined);
    try {
      if (step === "current") {
        setBusy(true);
        const r = mode === "remove" ? await pinClear(p) : await pinVerify(p);
        setBusy(false);
        if (!r.ok) { setErr(errorFor(r, "Wrong PIN.")); return; }
        if (mode === "remove") { pinIsSet = false; lock(); finish("PIN removed. The Hidden games tab is unlocked."); return; }
        setCurrent(p); setStep("new");
      } else if (step === "new") {
        setFirst(p); setStep("confirm");
      } else {
        if (p !== first) { setErr("PINs didn't match. Enter the new PIN again."); setStep("new"); return; }
        setBusy(true);
        const r = await pinSet(p, current);
        setBusy(false);
        if (!r.ok) { setErr(errorFor(r, "Couldn't save the PIN.")); setStep(mode === "set" ? "new" : "current"); return; }
        pinIsSet = true; lock();
        finish(mode === "set" ? "PIN set. The Hidden games tab is locked." : "PIN changed.");
      }
    } catch (e) {
      setBusy(false);
      setErr(`Couldn't reach the plugin backend: ${e}`);
    }
  };

  const title = step === "current" ? "Enter your current PIN" : step === "new" ? "Choose a new PIN" : "Enter the new PIN again";
  return (
    <ModalRoot closeModal={closeModal}>
      <PinPad key={step} title={title} error={err} busy={busy} onSubmit={submit} />
    </ModalRoot>
  );
}

export function openPinFlow(mode: "set" | "change" | "remove", onDone: (msg: string) => void) {
  showModal(<PinFlow mode={mode} onDone={onDone} />);
}
