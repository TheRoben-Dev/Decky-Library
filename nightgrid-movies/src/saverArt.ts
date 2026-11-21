/*
 * Nightgrid screensaver art: drawn live on a canvas (960x540, scaled up), 30 fps max.
 * Same visual language as the startup movies (render/movies.html): grid, wordmark, static.
 * Everything that's visible for long drifts slowly, so nothing sits still on the panel.
 */
export type SaverStyle = "grid" | "signal" | "terminal" | "clock";
export const STYLES: { id: SaverStyle; name: string }[] = [
  { id: "grid", name: "Grid Run" },
  { id: "signal", name: "Signal" },
  { id: "terminal", name: "Terminal" },
  { id: "clock", name: "Clock" },
];

export const W = 960, H = 540;
const C = { bg0: "#07080B", bg1: "#0D0F14", line: "#1F2633", text0: "#E6EDF3", text1: "#8B98A9",
            active: "#FF2A6D", data: "#00E5FF", ok: "#2BFF88" };
const MONO = `"Nightgrid Mono", "JetBrains Mono", ui-monospace, monospace`;
const font = (px: number, w = 700) => `${w} ${px}px ${MONO}`;

function rng(seed: number) { let s = seed >>> 0 || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }

type Ctx = CanvasRenderingContext2D;

function grid(g: Ctx, a = 1, ox = 0, oy = 0) {
  g.save(); g.globalAlpha = a * .35; g.strokeStyle = C.line; g.lineWidth = 1;
  const sx = ((ox % 96) + 96) % 96, sy = ((oy % 96) + 96) % 96;
  for (let x = -sx; x <= W; x += 96) { g.beginPath(); g.moveTo(x + .5, 0); g.lineTo(x + .5, H); g.stroke(); }
  for (let y = -sy; y <= H; y += 96) { g.beginPath(); g.moveTo(0, y + .5); g.lineTo(W, y + .5); g.stroke(); }
  g.globalAlpha = a * .8; g.fillStyle = C.line;
  for (let y = 6 - (sy % 12); y < H; y += 12) for (let x = 6 - (sx % 12); x < W; x += 12) g.fillRect(x, y, 1.2, 1.2);
  g.restore();
}

function scanlines(g: Ctx, a = .2) { g.fillStyle = `rgba(0,0,0,${a})`; for (let y = 0; y < H; y += 3) g.fillRect(0, y, W, 1); }

function vignette(g: Ctx, a = .55) {
  const r = g.createRadialGradient(W / 2, H / 2, H * .35, W / 2, H / 2, H * .95);
  r.addColorStop(0, "rgba(0,0,0,0)"); r.addColorStop(1, `rgba(0,0,0,${a})`); g.fillStyle = r; g.fillRect(0, 0, W, H);
}

// 8 pre-made static frames (cheap to draw, built once)
let staticFrames: HTMLCanvasElement[] | null = null;
function statics(doc: Document) {
  if (staticFrames) return staticFrames;
  staticFrames = [];
  for (let k = 0; k < 8; k++) {
    const c = doc.createElement("canvas"); c.width = 320; c.height = 180;
    const x = c.getContext("2d")!, img = x.createImageData(320, 180), d = img.data, r = rng(k * 7919 + 13);
    for (let y = 0; y < 180; y++) {
      const gain = .55 + r() * .9; let run = 0, v = 0;
      for (let i = 0; i < 320; i++) {
        if (run-- <= 0) { v = r(); run = (r() * 5) | 0; }
        const lum = Math.min(255, (40 + v * 215) * gain), j = (y * 320 + i) * 4;
        d[j] = d[j + 1] = d[j + 2] = lum; d[j + 3] = 255;
      }
    }
    x.putImageData(img, 0, 0); staticFrames.push(c);
  }
  return staticFrames;
}

function wordmark(g: Ctx, x: number, y: number, s: number, split = 0, a = 1) {
  g.save(); g.globalAlpha = a; g.textAlign = "center"; g.textBaseline = "alphabetic";
  g.font = font(64 * s, 800); (g as any).letterSpacing = `${.14 * 64 * s}px`;
  const dx = .07 * 64 * s;
  if (split) { g.globalCompositeOperation = "lighter"; g.fillStyle = "rgba(0,229,255,.9)"; g.fillText("NIGHTGRID", x + dx - split, y);
    g.fillStyle = "rgba(255,42,109,.9)"; g.fillText("NIGHTGRID", x + dx + split, y); g.globalCompositeOperation = "source-over"; }
  g.shadowColor = "rgba(255,42,109,.35)"; g.shadowBlur = 14; g.fillStyle = C.text0; g.fillText("NIGHTGRID", x + dx, y); g.shadowBlur = 0;
  g.fillStyle = C.active; g.shadowColor = C.active; g.shadowBlur = 10; g.fillRect(x - 250 * s, y + 15 * s, 500 * s, 3 * s); g.shadowBlur = 0;
  g.restore();
}

function clockText(now: Date) {
  const hh = String(now.getHours()).padStart(2, "0"), mm = String(now.getMinutes()).padStart(2, "0");
  const date = now.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" }).toUpperCase();
  return { time: `${hh}:${mm}`, date };
}

function clockBlock(g: Ctx, x: number, y: number, now: Date, s = 1, align: CanvasTextAlign = "center") {
  const { time, date } = clockText(now);
  g.save(); g.textAlign = align; g.textBaseline = "alphabetic";
  g.font = font(54 * s, 700); (g as any).letterSpacing = `${.06 * 54 * s}px`; g.fillStyle = C.text0;
  g.shadowColor = "rgba(0,229,255,.25)"; g.shadowBlur = 12; g.fillText(time, x, y); g.shadowBlur = 0;
  g.font = font(15 * s, 500); (g as any).letterSpacing = `${.3 * 15 * s}px`;
  g.fillStyle = C.data; const pre = "// "; g.fillText(pre + date, x, y + 30 * s);
  g.restore();
}

// slow Lissajous drift so long-lived elements never sit still
const drift = (t: number, ax: number, ay: number) => ({ x: Math.sin(t / 23) * ax + Math.sin(t / 7.1) * ax * .15, y: Math.sin(t / 31 + 1) * ay });

const LOG = ["sync library", "check updates", "idle", "fan curve ok", "battery ok", "wifi link ok", "controller online",
             "shader cache ok", "cloud saves synced", "downloads idle", "thermal ok", "standing by"];

export function drawSaver(g: Ctx, style: SaverStyle, t: number, frame: number, now: Date) {
  g.fillStyle = C.bg0; g.fillRect(0, 0, W, H);
  if (style === "grid") {
    const hz = H * .6;
    g.save(); g.beginPath(); g.rect(0, 0, W, hz); g.clip(); grid(g, .6, t * 4, 0); g.restore();
    const sky = g.createLinearGradient(0, hz - 130, 0, hz); sky.addColorStop(0, "rgba(255,42,109,0)"); sky.addColorStop(1, "rgba(255,42,109,.16)");
    g.fillStyle = sky; g.fillRect(0, hz - 130, W, 130);
    g.save(); g.beginPath(); g.rect(0, hz, W, H - hz); g.clip(); g.fillStyle = C.bg1; g.fillRect(0, hz, W, H - hz);
    g.strokeStyle = C.active; g.lineWidth = 1.2; g.globalAlpha = .9;
    const sway = Math.sin(t / 9) * 60;
    for (let i = -24; i <= 24; i++) { g.beginPath(); g.moveTo(W / 2 + i * 20, hz); g.lineTo(W / 2 + sway + i * 210, H); g.stroke(); }
    const ph = (t * .5) % 1;
    for (let k = 0; k < 14; k++) { const z = k + 1 - ph, yy = hz + (H - hz) * (1 / z) * .9; if (yy > H || yy < hz) continue;
      g.globalAlpha = .9 * Math.min(1, (yy - hz) / 60); g.beginPath(); g.moveTo(0, yy); g.lineTo(W, yy); g.stroke(); }
    g.restore();
    g.fillStyle = C.data; g.shadowColor = C.data; g.shadowBlur = 16; g.fillRect(0, hz - 1, W, 2); g.shadowBlur = 0;
    const d = drift(t, 120, 18);
    wordmark(g, W / 2 + d.x, hz - 110 + d.y, 1, (frame % 240 < 4) ? 5 : 0);
    clockBlock(g, W / 2 + d.x, hz - 40 + d.y, now, .7);
    scanlines(g, .14); vignette(g, .6);
  } else if (style === "signal") {
    grid(g, .7, 0, t * 2);
    const d = drift(t, 220, 120), glitch = frame % 300 < 6;
    wordmark(g, W / 2 + d.x, H / 2 - 20 + d.y, 1.1, glitch ? 8 : 0);
    clockBlock(g, W / 2 + d.x, H / 2 + 60 + d.y, now, .75);
    const fr = statics(g.canvas.ownerDocument!);
    g.save(); g.imageSmoothingEnabled = false; g.globalAlpha = glitch ? .5 : .07 + .03 * Math.sin(t * 3);
    g.drawImage(fr[frame % 8], 0, 0, W, H); g.restore();
    const by = ((t * 60) % (H + 80)) - 40; g.fillStyle = "rgba(230,237,243,.05)"; g.fillRect(0, by, W, 26);
    scanlines(g, .2); vignette(g, .6);
  } else if (style === "terminal") {
    grid(g, .5);
    const d = drift(t, 40, 20), x0 = 60 + d.x, y0 = 70 + d.y;
    g.textAlign = "left"; g.font = font(15, 500); (g as any).letterSpacing = "0px";
    const step = 1.4, n = Math.floor(t / step), rows = 18;
    for (let i = Math.max(0, n - rows); i <= n; i++) {
      const r = rng(Math.imul(i + 1, 2654435761) >>> 0); r(); const msg = LOG[(r() * LOG.length) | 0], when = new Date(now.getTime() - (n - i) * step * 1000);
      const yy = y0 + (i - Math.max(0, n - rows)) * 22, ts = when.toTimeString().slice(0, 8);
      const typed = i === n ? Math.floor(((t % step) / step) * 40) : 99;
      g.fillStyle = C.text1; g.fillText(`[${ts}]`, x0, yy);
      g.fillStyle = r() < .2 ? C.data : C.text0; g.globalAlpha = i === n ? 1 : .75;
      const line = `nightgrid: ${msg}`.slice(0, typed); g.fillText(line, x0 + 110, yy); g.globalAlpha = 1;
      if (i === n && Math.floor(t * 2) % 2 === 0) { g.fillStyle = C.active; g.fillRect(x0 + 112 + g.measureText(line).width, yy - 12, 8, 15); }
    }
    clockBlock(g, W - 70 + d.x * .5, H - 90 + d.y, now, .9, "right");
    g.save(); g.textAlign = "right"; g.font = font(14, 600); (g as any).letterSpacing = `${.14 * 14}px`; g.fillStyle = C.text1;
    g.fillText("NIGHTGRID // STANDBY", W - 70 + d.x * .5, 50 + d.y); g.restore();
    scanlines(g, .18); vignette(g, .55);
  } else {
    grid(g, .45);
    const d = drift(t, 260, 120);
    clockBlock(g, W / 2 + d.x, H / 2 + 10 + d.y, now, 1.6);
    g.save(); g.textAlign = "center"; g.font = font(13, 600); (g as any).letterSpacing = `${.3 * 13}px`; g.fillStyle = C.text1;
    g.fillText("NIGHTGRID", W / 2 + d.x, H / 2 - 80 + d.y); g.restore();
    scanlines(g, .12); vignette(g, .5);
  }
}
