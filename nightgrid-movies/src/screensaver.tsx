/*
 * Idle screensaver.
 * - Input from any source counts as activity: controller buttons/sticks/triggers (SteamClient.Input),
 *   and touch / keyboard / mouse in the Game Mode window. Inputs in Quick Access go through the
 *   controller callbacks too.
 * - After `minutes` with no input, and only while no game is running, a fullscreen layer with a
 *   Nightgrid animation covers the UI. Any input removes it.
 * - The layer is a Decky global component, so it lives in the Game Mode window above the UI.
 */
import { Router } from "@decky/ui";
import { CSSProperties, useEffect, useRef, useState } from "react";
import { drawSaver, H, SaverStyle, STYLES, W } from "./saverArt";

export interface SaverConfig { enabled: boolean; minutes: number; style: SaverStyle | "random" }
export const DEFAULT_SAVER: SaverConfig = { enabled: true, minutes: 5, style: "random" };

let cfg: SaverConfig = { ...DEFAULT_SAVER };
let lastInput = Date.now();
let ignoreUntil = 0;       // after "Preview", ignore the button release that started it
let previewAsked = false;
const subs = new Set<() => void>();
const notify = () => subs.forEach((f) => f());

export function setSaverConfig(c: SaverConfig) { cfg = { ...DEFAULT_SAVER, ...c }; lastInput = Date.now(); notify(); }
export function previewSaver() { ignoreUntil = Date.now() + 1500; previewAsked = true; notify(); }
export function noteInput() {
  if (Date.now() < ignoreUntil) return;
  lastInput = Date.now();
  notify();
}

/** true when a game (or any app) is running: the saver never covers a game. */
function appRunning(): boolean {
  try {
    const r = Router as any;
    return !!r.MainRunningApp || (Array.isArray(r.RunningApps) && r.RunningApps.length > 0);
  } catch { return false; }
}

/** Registers the controller callbacks; returns an unregister function. */
export function watchController(): () => void {
  const regs: ({ unregister: () => void } | undefined)[] = [];
  const input = (window as any).SteamClient?.Input;
  try { regs.push(input?.RegisterForControllerInputMessages?.(() => noteInput())); } catch { /* not available */ }
  // Button bits are compared with the last packet (some bits may be held high all the time);
  // sticks and triggers count past a deadzone.
  const lastButtons = new Map<number, number>();
  try {
    regs.push(input?.RegisterForControllerStateChanges?.((changes: any[]) => {
      for (const c of changes ?? []) {
        const idx = c.unControllerIndex ?? 0, prev = lastButtons.get(idx);
        lastButtons.set(idx, c.ulButtons ?? 0);
        if ((prev !== undefined && prev !== (c.ulButtons ?? 0)) || Math.abs(c.sLeftStickX ?? 0) > 6000 || Math.abs(c.sLeftStickY ?? 0) > 6000
          || Math.abs(c.sRightStickX ?? 0) > 6000 || Math.abs(c.sRightStickY ?? 0) > 6000
          || (c.sTriggerL ?? 0) > 4000 || (c.sTriggerR ?? 0) > 4000) { noteInput(); return; }
      }
    }));
  } catch { /* not available */ }
  return () => regs.forEach((r) => { try { r?.unregister(); } catch { /* ignore */ } });
}

const pickStyle = (): SaverStyle => cfg.style !== "random" ? cfg.style
  : STYLES[Math.floor(Math.random() * STYLES.length)].id;

function Layer({ style, onWake }: { style: SaverStyle; onWake: () => void }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const cv = ref.current; if (!cv) return;
    const win = cv.ownerDocument.defaultView ?? window, g = cv.getContext("2d")!;
    const t0 = performance.now(); let last = 0, frame = 0, raf = 0;
    const loop = (now: number) => {
      raf = win.requestAnimationFrame(loop);
      if (now - last < 33) return;            // ~30 fps is plenty
      last = now;
      drawSaver(g, style, (now - t0) / 1000, frame++, new Date());
    };
    raf = win.requestAnimationFrame(loop);
    const fade = win.setTimeout(() => setShown(true), 30);
    return () => { win.cancelAnimationFrame(raf); win.clearTimeout(fade); };
  }, [style]);
  const box: CSSProperties = {
    position: "fixed", inset: 0, zIndex: 2147483000, background: "#07080B", cursor: "none",
    opacity: shown ? 1 : 0, transition: "opacity 600ms ease",
  };
  return (
    <div style={box} onPointerDown={onWake} onTouchStart={onWake}>
      <canvas ref={ref} width={W} height={H} style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
    </div>
  );
}

/** Always mounted (global component); shows the layer when idle. */
export function ScreensaverHost() {
  const anchor = useRef<HTMLDivElement>(null);
  const [style, setStyle] = useState<SaverStyle | null>(null);
  const shownAt = useRef(0);

  useEffect(() => {
    const show = () => { shownAt.current = Date.now(); setStyle(pickStyle()); };
    const hide = () => setStyle(null);
    const onChange = () => {
      if (previewAsked) { previewAsked = false; show(); return; }
      if (lastInput > shownAt.current) hide();
    };
    subs.add(onChange);
    const tick = window.setInterval(() => {
      if (!cfg.enabled || shownAt.current > lastInput) return;   // off, or already showing
      if (Date.now() - lastInput >= cfg.minutes * 60_000 && !appRunning()) show();
    }, 1000);

    // touch / keys / mouse in the Game Mode window itself
    const win = anchor.current?.ownerDocument.defaultView;
    const evs = ["pointerdown", "touchstart", "keydown", "wheel", "mousemove"];
    const onDom = () => noteInput();
    evs.forEach((e) => win?.addEventListener(e, onDom, { capture: true, passive: true }));
    return () => {
      subs.delete(onChange); window.clearInterval(tick);
      evs.forEach((e) => win?.removeEventListener(e, onDom, { capture: true }));
    };
  }, []);

  return (
    <>
      <div ref={anchor} style={{ display: "none" }} />
      {style && <Layer style={style} onWake={() => noteInput()} />}
    </>
  );
}
