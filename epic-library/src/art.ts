/*
 * Steam artwork from the game's own Epic images (tall box art, wide key art, logo), finished in the
 * Nightgrid look: square cyan frame, EPIC tag, grid backdrop where an image has to be letterboxed.
 * Images arrive as base64 from the backend, so the canvas is never tainted.
 */
const BG = "#07080B", LINE = "#1F2633", TEXT = "#E6EDF3", DATA = "#00E5FF", ACTIVE = "#FF2A6D";
const FONT = `"JetBrains Mono", "Fira Code", ui-monospace, monospace`;

function load(b64: string, ext: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Couldn't read the game's image"));
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
  const t = "EPIC";
  const w = ctx.measureText(t).width + size;
  ctx.strokeStyle = DATA; ctx.lineWidth = 1.5; ctx.strokeRect(x, y, w, size * 1.6);
  ctx.fillStyle = DATA; ctx.textBaseline = "middle"; ctx.fillText(t, x + size / 2, y + size * 0.82);
}

const png = (c: HTMLCanvasElement) => c.toDataURL("image/png").split(",")[1];

export interface Img { data: string; ext: string }

function shade(ctx: CanvasRenderingContext2D, w: number, h: number, from: number, alpha: number) {
  const g = ctx.createLinearGradient(0, h * from, 0, h);
  g.addColorStop(0, "rgba(7,8,11,0)"); g.addColorStop(1, `rgba(7,8,11,${alpha})`);
  ctx.fillStyle = g; ctx.fillRect(0, h * from, w, h * (1 - from));
}

function inset(ctx: CanvasRenderingContext2D, w: number, h: number, pad: number, color = DATA) {
  ctx.save();
  ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.shadowColor = color; ctx.shadowBlur = 10;
  ctx.strokeRect(pad, pad, w - pad * 2, h - pad * 2);
  ctx.restore();
}

/** Capsule, wide capsule, hero, logo and icon. Any of the three source images may be missing. */
export async function composeArt(src: { tall?: Img; wide?: Img; logo?: Img }, name: string) {
  const tall = src.tall ? await load(src.tall.data, src.tall.ext).catch(() => null) : null;
  const wideImg = src.wide ? await load(src.wide.data, src.wide.ext).catch(() => null) : null;
  const logoImg = src.logo ? await load(src.logo.data, src.logo.ext).catch(() => null) : null;
  const any = tall ?? wideImg;
  if (!any) throw new Error("No artwork for this game");
  const wideSrc = wideImg ?? any;

  // Capsule 600×900: the box art full-bleed; letterboxed over a grid when only key art exists.
  const [cap, a] = canvas(600, 900);
  if (tall) {
    a.fillStyle = BG; a.fillRect(0, 0, 600, 900);
    draw(a, tall, 0, 0, 600, 900, true);
    shade(a, 600, 900, 0.72, 0.55);
  } else {
    backdrop(a, wideSrc, 600, 900);
    const r = draw(a, wideSrc, 30, 250, 540, 400, false);
    frame(a, r);
    title(a, name, 36, r.y + r.h + 40, 528, 40, 3);
  }
  inset(a, 600, 900, 10);
  tag(a, 26, 846, 16);

  // Wide capsule 920×430 and hero 1920×620: the key art, framed; Steam lays the logo over the hero.
  const [wide, b] = canvas(920, 430);
  b.fillStyle = BG; b.fillRect(0, 0, 920, 430);
  if (wideImg) draw(b, wideImg, 0, 0, 920, 430, true);
  else { backdrop(b, any, 920, 430, 0.5); frame(b, draw(b, any, 40, 30, 840, 370, false)); }
  inset(b, 920, 430, 8);

  const [hero, c] = canvas(1920, 620);
  c.fillStyle = BG; c.fillRect(0, 0, 1920, 620);
  if (wideImg) {
    draw(c, wideImg, 0, 0, 1920, 620, true);
    shade(c, 1920, 620, 0.45, 0.6);
  } else {
    backdrop(c, any, 1920, 620, 0.55);
    frame(c, draw(c, any, 1060, 60, 800, 500, false), ACTIVE);
  }

  // Logo 1280×400, transparent: Epic's own logo when there is one, else the title in Nightgrid type.
  const [logo, d] = canvas(1280, 400);
  if (logoImg) {
    draw(d, logoImg, 0, 0, 1280, 400, false);
  } else {
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
  }

  // Icon 256×256: centre crop of the box art.
  const [icon, e] = canvas(256, 256);
  e.fillStyle = BG; e.fillRect(0, 0, 256, 256);
  draw(e, tall ?? any, 0, 0, 256, 256, true);

  return { capsule: png(cap), wide: png(wide), hero: png(hero), logo: png(logo), icon: png(icon) };
}
