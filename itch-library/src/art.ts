/*
 * Steam artwork from an itch.io cover (630×500-ish), drawn on a canvas in the Nightgrid look:
 * near-black grid, the cover blurred behind itself, cyan/magenta accents, mono uppercase title.
 * The cover arrives as base64 from the backend, so the canvas is never tainted.
 */
const BG = "#07080B", LINE = "#1F2633", TEXT = "#E6EDF3", DATA = "#00E5FF", ACTIVE = "#FF2A6D";
const FONT = `"JetBrains Mono", "Fira Code", ui-monospace, monospace`;

function load(b64: string, ext: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Couldn't read the cover image"));
    img.src = `data:image/${ext === "jpeg" ? "jpeg" : ext};base64,${b64}`;
  });
}

function canvas(w: number, h: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  return [c, c.getContext("2d")!];
}

function fit(img: HTMLImageElement, w: number, h: number, cover: boolean) {
  const s = cover ? Math.max(w / img.width, h / img.height) : Math.min(w / img.width, h / img.height);
  return { w: img.width * s, h: img.height * s };
}

function draw(ctx: CanvasRenderingContext2D, img: HTMLImageElement, x: number, y: number, w: number, h: number, cover: boolean) {
  const f = fit(img, w, h, cover);
  ctx.save();
  ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip();
  ctx.drawImage(img, x + (w - f.w) / 2, y + (h - f.h) / 2, f.w, f.h);
  ctx.restore();
  return { x: x + (w - Math.min(w, f.w)) / 2, y: y + (h - Math.min(h, f.h)) / 2, w: Math.min(w, f.w), h: Math.min(h, f.h) };
}

function backdrop(ctx: CanvasRenderingContext2D, img: HTMLImageElement, w: number, h: number, dim = 0.42) {
  ctx.fillStyle = BG; ctx.fillRect(0, 0, w, h);
  ctx.save();
  ctx.filter = `blur(${Math.round(Math.max(w, h) / 40)}px) brightness(${dim}) saturate(1.2)`;
  draw(ctx, img, -w * 0.05, -h * 0.05, w * 1.1, h * 1.1, true);
  ctx.restore();
  ctx.strokeStyle = LINE; ctx.globalAlpha = 0.55; ctx.lineWidth = 1;
  const step = Math.round(Math.max(w, h) / 24);
  ctx.beginPath();
  for (let x = 0.5; x < w; x += step) { ctx.moveTo(x, 0); ctx.lineTo(x, h); }
  for (let y = 0.5; y < h; y += step) { ctx.moveTo(0, y); ctx.lineTo(w, y); }
  ctx.stroke();
  ctx.globalAlpha = 1;
  const g = ctx.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, "rgba(7,8,11,0)"); g.addColorStop(1, "rgba(7,8,11,0.85)");
  ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
}

function frame(ctx: CanvasRenderingContext2D, r: { x: number; y: number; w: number; h: number }, color = DATA) {
  ctx.save();
  ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.shadowColor = color; ctx.shadowBlur = 14;
  ctx.strokeRect(r.x - 1, r.y - 1, r.w + 2, r.h + 2);
  ctx.restore();
}

function wrap(ctx: CanvasRenderingContext2D, text: string, maxW: number, maxLines: number): string[] {
  const words = text.toUpperCase().split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    const t = cur ? `${cur} ${w}` : w;
    if (ctx.measureText(t).width <= maxW || !cur) cur = t;
    else { lines.push(cur); cur = w; }
  }
  if (cur) lines.push(cur);
  if (lines.length > maxLines) {
    const keep = lines.slice(0, maxLines);
    keep[maxLines - 1] = keep[maxLines - 1].replace(/.{0,2}$/, "…");
    return keep;
  }
  return lines;
}

function title(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, maxW: number, size: number, maxLines: number) {
  ctx.font = `700 ${size}px ${FONT}`;
  let lines = wrap(ctx, text, maxW, maxLines);
  while (size > 18 && lines.some((l) => ctx.measureText(l).width > maxW)) {
    size -= 2; ctx.font = `700 ${size}px ${FONT}`; lines = wrap(ctx, text, maxW, maxLines);
  }
  ctx.fillStyle = TEXT; ctx.textBaseline = "top";
  ctx.shadowColor = "rgba(0,229,255,0.35)"; ctx.shadowBlur = 10;
  lines.forEach((l, i) => ctx.fillText(l, x, y + i * size * 1.18, maxW));
  ctx.shadowBlur = 0;
  return y + lines.length * size * 1.18;
}

function tag(ctx: CanvasRenderingContext2D, x: number, y: number, size: number) {
  ctx.font = `600 ${size}px ${FONT}`;
  const t = "ITCH.IO";
  const w = ctx.measureText(t).width + size;
  ctx.strokeStyle = DATA; ctx.lineWidth = 1.5; ctx.strokeRect(x, y, w, size * 1.6);
  ctx.fillStyle = DATA; ctx.textBaseline = "middle"; ctx.fillText(t, x + size / 2, y + size * 0.82);
}

const png = (c: HTMLCanvasElement) => c.toDataURL("image/png").split(",")[1];

export async function composeArt(b64: string, ext: string, name: string) {
  const img = await load(b64, ext);

  // Capsule 600×900: cover framed in the upper half, title underneath.
  const [cap, a] = canvas(600, 900);
  backdrop(a, img, 600, 900);
  tag(a, 36, 40, 18);
  const r = draw(a, img, 36, 110, 528, 440, false);
  frame(a, r);
  a.fillStyle = ACTIVE; a.fillRect(36, r.y + r.h + 28, 64, 4);
  title(a, name, 36, r.y + r.h + 52, 528, 46, 4);

  // Wide capsule 920×430: cover large and centred.
  const [wide, b] = canvas(920, 430);
  backdrop(b, img, 920, 430, 0.5);
  frame(b, draw(b, img, 40, 30, 840, 370, false));

  // Hero 1920×620: blurred backdrop with the cover on the right; Steam puts the logo bottom-left.
  const [hero, c] = canvas(1920, 620);
  backdrop(c, img, 1920, 620, 0.55);
  const hr = draw(c, img, 1060, 60, 800, 500, false);
  frame(c, hr, ACTIVE);

  // Logo 1280×400, transparent: the title in Nightgrid type.
  const [logo, d] = canvas(1280, 400);
  d.font = `800 96px ${FONT}`;
  let size = 96;
  const lines = () => wrap(d, name, 1240, 2);
  while (size > 40 && (lines().length > 2 || lines().some((l) => d.measureText(l).width > 1240))) { size -= 4; d.font = `800 ${size}px ${FONT}`; }
  const ls = lines();
  d.textBaseline = "bottom";
  ls.forEach((l, i) => {
    const y = 400 - (ls.length - 1 - i) * size * 1.1 - 12;
    d.fillStyle = ACTIVE; d.globalAlpha = 0.55; d.fillText(l, 23, y + 3);
    d.fillStyle = DATA; d.globalAlpha = 0.55; d.fillText(l, 17, y - 3);
    d.globalAlpha = 1; d.fillStyle = TEXT; d.shadowColor = "rgba(0,0,0,0.8)"; d.shadowBlur = 16; d.fillText(l, 20, y); d.shadowBlur = 0;
  });

  // Icon 256×256: centre crop.
  const [icon, e] = canvas(256, 256);
  e.fillStyle = BG; e.fillRect(0, 0, 256, 256);
  draw(e, img, 0, 0, 256, 256, true);

  return { capsule: png(cap), wide: png(wide), hero: png(hero), logo: png(logo), icon: png(icon) };
}
