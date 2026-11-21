/*
 * Original Nightgrid UI sounds, synthesized in the browser with an OfflineAudioContext.
 * No audio files ship with the plugin: each pack is a handful of parameters applied to one
 * shared "score", rendered once (a few ms per sound) and kept as small WAV blob URLs.
 */

export type Cat =
  | "nav" | "select" | "open" | "close" | "tab" | "edge" | "toggleOn" | "toggleOff"
  | "sliderUp" | "sliderDown" | "notify" | "launch" | "type";

export const CATS: { id: Cat; name: string }[] = [
  { id: "nav", name: "Move focus" },
  { id: "select", name: "Select" },
  { id: "open", name: "Open page / menu" },
  { id: "close", name: "Back / close" },
  { id: "tab", name: "Switch tab" },
  { id: "edge", name: "End of list" },
  { id: "toggleOn", name: "Toggle on" },
  { id: "toggleOff", name: "Toggle off" },
  { id: "sliderUp", name: "Slider / volume up" },
  { id: "sliderDown", name: "Slider down" },
  { id: "notify", name: "Notifications" },
  { id: "launch", name: "Launch game" },
  { id: "type", name: "Keyboard" },
];

/** Steam sound file -> category. Order matters (first match wins). Unknown files stay Steam's. */
const MAP: [RegExp, Cat][] = [
  [/navigation|tile_scroll/, "nav"],
  [/default_activation|misc_\d+/, "select"],
  [/into_game_detail|show_modal|side_menu_fly_in/, "open"],
  [/out_of_game_detail|hide_modal|side_menu_fly_out/, "close"],
  [/tab_transition/, "tab"],
  [/bumper_end/, "edge"],
  [/toggle_on/, "toggleOn"],
  [/toggle_off/, "toggleOff"],
  [/slider_up|volume/, "sliderUp"],
  [/slider_down/, "sliderDown"],
  [/toast|pop_sound|notification|friend_join|friend_online|message|at_mention/, "notify"],
  [/launch_game/, "launch"],
  [/typing/, "type"],
];

export function categoryOf(url: string): Cat | null {
  const file = (url.split("?")[0].split("/").pop() ?? "").toLowerCase();
  for (const [re, cat] of MAP) if (re.test(file)) return cat;
  return null;
}

/*
 * Each pack is its own sound design: a function per sound that places voices (tones, filtered
 * noise, clicks) on a small builder, plus pack-wide effects (echo, speaker band, drive, bit crush).
 * Every rendered sound is normalised to a per-sound loudness, so packs sit at the same level and
 * quiet sounds (focus ticks, typing) stay quieter than big ones (notifications, launch).
 */

const RATE = 44100;
const hz = (semi: number) => 440 * Math.pow(2, semi / 12);   // semitones from A4

/** Bumped whenever the sound design changes, so cached files on disk are re-rendered. */
export const DESIGN_VERSION = "v2";

interface Tone {
  t?: number; d: number; f: number; f2?: number; type?: OscillatorType; g?: number; a?: number;
  lp?: number; lp2?: number; q?: number; fm?: [ratio: number, index: number]; detune?: number[];
}
interface Noise { t?: number; d: number; f: number; f2?: number; kind?: BiquadFilterType; q?: number; g?: number; a?: number }

class Builder {
  constructor(readonly ctx: OfflineAudioContext, readonly out: AudioNode) {}

  private env(p: AudioParam, t: number, d: number, g: number, a = 0.003) {
    const at = Math.min(a, d * 0.6);
    p.setValueAtTime(0.0001, t);
    p.exponentialRampToValueAtTime(Math.max(g, 0.0002), t + at);
    p.exponentialRampToValueAtTime(0.0001, t + d);
  }

  tone(o: Tone) {
    const { ctx } = this, t = o.t ?? 0;
    const amp = ctx.createGain(); this.env(amp.gain, t, o.d, o.g ?? 0.5, o.a);
    let dest: AudioNode = amp;
    if (o.lp) {
      const f = ctx.createBiquadFilter(); f.type = "lowpass"; f.Q.value = o.q ?? 0.8;
      f.frequency.setValueAtTime(o.lp, t);
      if (o.lp2) f.frequency.exponentialRampToValueAtTime(o.lp2, t + o.d);
      f.connect(amp); dest = f;
    }
    amp.connect(this.out);
    const dets = o.detune ?? [0];
    for (const cents of dets) {
      const osc = ctx.createOscillator(); osc.type = o.type ?? "sine"; osc.detune.value = cents;
      osc.frequency.setValueAtTime(o.f, t);
      if (o.f2) osc.frequency.exponentialRampToValueAtTime(o.f2, t + o.d);
      if (o.fm) {
        const m = ctx.createOscillator(); m.frequency.setValueAtTime(o.f * o.fm[0], t);
        if (o.f2) m.frequency.exponentialRampToValueAtTime(o.f2 * o.fm[0], t + o.d);
        const mg = ctx.createGain(); mg.gain.setValueAtTime(o.f * o.fm[1], t);
        mg.gain.exponentialRampToValueAtTime(Math.max(1, o.f * o.fm[1] * 0.1), t + o.d);   // FM brightness decays
        m.connect(mg).connect(osc.frequency); m.start(t); m.stop(t + o.d + 0.02);
      }
      const v = ctx.createGain(); v.gain.value = 1 / dets.length;
      osc.connect(v).connect(dest); osc.start(t); osc.stop(t + o.d + 0.02);
    }
  }

  noise(o: Noise) {
    const { ctx } = this, t = o.t ?? 0;
    const src = ctx.createBufferSource(); src.buffer = noiseBuffer(ctx); src.loop = true;
    const f = ctx.createBiquadFilter(); f.type = o.kind ?? "bandpass"; f.Q.value = o.q ?? 1;
    f.frequency.setValueAtTime(o.f, t);
    if (o.f2) f.frequency.exponentialRampToValueAtTime(o.f2, t + o.d);
    const amp = ctx.createGain(); this.env(amp.gain, t, o.d, o.g ?? 0.4, o.a ?? 0.001);
    src.connect(f).connect(amp).connect(this.out);
    src.start(t, (t * 7.3) % 0.4); src.stop(t + o.d + 0.02);
  }
}

let noiseBuf: AudioBuffer | null = null;
function noiseBuffer(ctx: BaseAudioContext): AudioBuffer {
  if (noiseBuf && noiseBuf.sampleRate === ctx.sampleRate) return noiseBuf;
  const b = ctx.createBuffer(1, Math.floor(ctx.sampleRate * 0.5), ctx.sampleRate);
  const ch = b.getChannelData(0);
  let seed = 0x9e3779b9;                     // deterministic, so a pack always sounds the same
  for (let i = 0; i < ch.length; i++) {
    seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5;
    ch[i] = ((seed >>> 0) / 0xffffffff) * 2 - 1;
  }
  return (noiseBuf = b);
}

interface Fx {
  echo?: { time: number; fb: number; mix: number };
  speaker?: [lo: number, hi: number];       // band-limit like a small CRT speaker
  drive?: number;                           // soft saturation amount (1 = none)
  crush?: number;                           // bit depth
  lp?: number;
}
type Design = (b: Builder) => void;
export interface Pack { id: string; name: string; about: string; fx: Fx; sounds: Record<Cat, Design> }

/* ---------- shared gestures ---------- */
const keyClack = (b: Builder, t = 0, g = 1) => {
  b.noise({ t, d: 0.005, f: 5000, kind: "highpass", g: 0.45 * g });                 // contact click
  b.noise({ t, d: 0.035, f: 1700, q: 1.6, g: 0.55 * g });                           // plastic body
  b.tone({ t, d: 0.045, f: 150, f2: 85, g: 0.45 * g, a: 0.001 });                  // key bottoming out
};
const relayTick = (b: Builder, t = 0, f = 3200, g = 1) => {
  b.noise({ t, d: 0.022, f, q: 14, g: 0.6 * g });                                   // ringing contact
  b.noise({ t, d: 0.004, f: 6500, kind: "highpass", g: 0.25 * g });
};
const termBeep = (b: Builder, t: number, f: number, d: number, g = 0.3) =>
  b.tone({ t, d, f, type: "square", lp: 2400, g, a: 0.002 });
const pluck = (b: Builder, t: number, semi: number, d = 0.25, g = 0.35, bright = 3200) =>
  b.tone({ t, d, f: hz(semi), type: "sawtooth", detune: [-9, 9], lp: bright, lp2: 280, q: 2.5, g, a: 0.004 });
const glass = (b: Builder, t: number, semi: number, d = 0.1, g = 0.35, fm = 0.5) =>
  b.tone({ t, d, f: hz(semi), fm: [2, fm], g, a: 0.002 });

export const PACKS: Pack[] = [
  {
    id: "nightgrid", name: "Nightgrid", about: "Glassy cyber-HUD chimes with a soft echo. Calm and clean.",
    fx: { echo: { time: 0.085, fb: 0.3, mix: 0.25 }, lp: 9000 },
    sounds: {
      nav: (b) => { b.tone({ d: 0.03, f: hz(31), g: 0.3, a: 0.002 }); b.noise({ d: 0.01, f: 7000, kind: "highpass", g: 0.05 }); },
      select: (b) => { glass(b, 0, 19, 0.08, 0.4); glass(b, 0.055, 26, 0.14, 0.35, 0.35); },
      open: (b) => { b.noise({ d: 0.17, f: 500, f2: 3800, q: 1.4, g: 0.22, a: 0.08 }); b.tone({ t: 0.02, d: 0.15, f: hz(14), f2: hz(26), g: 0.18, a: 0.03 }); },
      close: (b) => { b.noise({ d: 0.14, f: 3800, f2: 500, q: 1.4, g: 0.2, a: 0.01 }); b.tone({ d: 0.12, f: hz(26), f2: hz(14), g: 0.16, a: 0.005 }); },
      tab: (b) => { b.tone({ d: 0.05, f: hz(21), type: "triangle", g: 0.3 }); b.tone({ t: 0.04, d: 0.08, f: hz(28), type: "triangle", g: 0.24 }); },
      edge: (b) => { b.tone({ d: 0.12, f: hz(7), f2: hz(0), fm: [1.5, 0.9], g: 0.45, a: 0.002 }); },
      toggleOn: (b) => { glass(b, 0, 19, 0.05, 0.35); glass(b, 0.05, 31, 0.1, 0.3, 0.3); },
      toggleOff: (b) => { glass(b, 0, 31, 0.05, 0.3, 0.3); glass(b, 0.05, 19, 0.1, 0.35); },
      sliderUp: (b) => b.tone({ d: 0.025, f: hz(33), g: 0.22 }),
      sliderDown: (b) => b.tone({ d: 0.025, f: hz(28), g: 0.22 }),
      notify: (b) => { [19, 22, 26].forEach((s, i) => glass(b, i * 0.09, s, 0.28, 0.3, 0.3)); b.tone({ d: 0.5, f: hz(7), type: "triangle", g: 0.1, a: 0.06 }); },
      launch: (b) => {
        b.noise({ d: 0.7, f: 300, f2: 6000, q: 1.2, g: 0.18, a: 0.5 });
        [7, 14, 19, 26].forEach((s, i) => glass(b, 0.2 + i * 0.1, s, 0.35, 0.25, 0.4));
        b.tone({ t: 0.6, d: 0.6, f: hz(-24), g: 0.4, a: 0.01 });
      },
      type: (b) => { b.noise({ d: 0.018, f: 2600, q: 2, g: 0.35 }); b.tone({ d: 0.012, f: hz(38), g: 0.05 }); },
    },
  },
  {
    id: "terminal", name: "Phosphor Terminal",
    about: "Retro green-screen terminal: mechanical key clacks, relay ticks, chirpy speaker beeps, CRT power-up.",
    fx: { speaker: [380, 3800], drive: 1.8 },
    sounds: {
      nav: (b) => relayTick(b, 0, 3300, 0.8),
      select: (b) => { keyClack(b, 0, 0.7); termBeep(b, 0.025, 1180, 0.06); },
      open: (b) => { termBeep(b, 0, 880, 0.05); termBeep(b, 0.065, 1320, 0.07); },
      close: (b) => { termBeep(b, 0, 1320, 0.05); termBeep(b, 0.065, 880, 0.07); },
      tab: (b) => { relayTick(b, 0, 2900); relayTick(b, 0.045, 3500, 0.8); },
      edge: (b) => b.tone({ d: 0.1, f: 160, type: "square", lp: 900, g: 0.35 }),
      toggleOn: (b) => { keyClack(b, 0, 0.9); termBeep(b, 0.03, 1500, 0.035, 0.25); },
      toggleOff: (b) => { keyClack(b, 0, 0.9); termBeep(b, 0.03, 990, 0.035, 0.25); },
      sliderUp: (b) => relayTick(b, 0, 2900, 0.6),
      sliderDown: (b) => relayTick(b, 0, 2300, 0.6),
      notify: (b) => { termBeep(b, 0, 1568, 0.045); termBeep(b, 0.065, 1046, 0.045); termBeep(b, 0.13, 1568, 0.09); },
      launch: (b) => {
        b.tone({ d: 0.95, f: 60, g: 0.3, a: 0.12 }); b.tone({ d: 0.95, f: 120, g: 0.14, a: 0.12 });   // CRT hum
        b.tone({ t: 0.05, d: 0.5, f: 180, f2: 1500, type: "sawtooth", lp: 1600, g: 0.12, a: 0.25 });   // flyback whine up
        keyClack(b, 0.58, 1); relayTick(b, 0.62, 3000);
        termBeep(b, 0.7, 1180, 0.12, 0.28);
      },
      type: (b) => keyClack(b, 0, 1),
    },
  },
  {
    id: "neon", name: "Neon Pulse", about: "Warm synthwave plucks in A minor with a long echo. Musical.",
    fx: { echo: { time: 0.14, fb: 0.35, mix: 0.3 } },
    sounds: {
      nav: (b) => pluck(b, 0, 12, 0.09, 0.2, 2400),
      select: (b) => { pluck(b, 0, 7, 0.18); pluck(b, 0.06, 12, 0.22); },
      open: (b) => [0, 7, 12].forEach((s, i) => pluck(b, i * 0.03, s, 0.32, 0.22)),
      close: (b) => [12, 7, 0].forEach((s, i) => pluck(b, i * 0.03, s, 0.28, 0.22)),
      tab: (b) => pluck(b, 0, 10, 0.12, 0.3),
      edge: (b) => pluck(b, 0, -12, 0.2, 0.4, 1200),
      toggleOn: (b) => { pluck(b, 0, 7, 0.1); pluck(b, 0.05, 14, 0.16); },
      toggleOff: (b) => { pluck(b, 0, 14, 0.1); pluck(b, 0.05, 7, 0.16); },
      sliderUp: (b) => pluck(b, 0, 19, 0.05, 0.16, 2600),
      sliderDown: (b) => pluck(b, 0, 15, 0.05, 0.16, 2600),
      notify: (b) => [0, 3, 7, 12].forEach((s, i) => pluck(b, i * 0.07, s, 0.32, 0.26)),
      launch: (b) => {
        for (const s of [-12, -5, 0, 3]) b.tone({ d: 1.0, f: hz(s), type: "sawtooth", detune: [-12, 12], lp: 300, lp2: 4200, q: 3, g: 0.16, a: 0.35 });
        b.tone({ t: 0.35, d: 0.7, f: hz(-24), g: 0.4, a: 0.02 });
      },
      type: (b) => { pluck(b, 0, 24, 0.035, 0.12, 4000); b.noise({ d: 0.008, f: 4000, kind: "highpass", g: 0.08 }); },
    },
  },
  {
    id: "signal", name: "Ghost Signal", about: "Lo-fi data bleeps and radio static, like a hacked feed. Subtle.",
    fx: { crush: 7, echo: { time: 0.05, fb: 0.2, mix: 0.15 }, lp: 6500 },
    sounds: {
      nav: (b) => { b.noise({ d: 0.012, f: 5000, q: 4, g: 0.3 }); b.tone({ d: 0.012, f: 4200, g: 0.08 }); },
      select: (b) => { b.tone({ d: 0.03, f: 1760, type: "square", lp: 3000, g: 0.2 }); b.tone({ t: 0.04, d: 0.05, f: 2349, type: "square", lp: 3000, g: 0.2 }); },
      open: (b) => { b.noise({ d: 0.18, f: 800, f2: 4200, q: 3, g: 0.22, a: 0.02 }); b.tone({ d: 0.15, f: 600, f2: 1800, g: 0.12, a: 0.02 }); },
      close: (b) => { b.noise({ d: 0.16, f: 4200, f2: 800, q: 3, g: 0.2 }); b.tone({ d: 0.14, f: 1800, f2: 600, g: 0.12 }); },
      tab: (b) => [0, 0.022, 0.044].forEach((t, i) => b.noise({ t, d: 0.014, f: 3000 + i * 500, q: 6, g: 0.3 })),
      edge: (b) => { b.noise({ d: 0.1, f: 450, kind: "lowpass", g: 0.4 }); b.tone({ d: 0.09, f: 90, g: 0.3 }); },
      toggleOn: (b) => b.tone({ d: 0.07, f: 1200, f2: 2400, type: "triangle", g: 0.25 }),
      toggleOff: (b) => b.tone({ d: 0.07, f: 2400, f2: 1200, type: "triangle", g: 0.25 }),
      sliderUp: (b) => b.noise({ d: 0.012, f: 4200, q: 6, g: 0.3 }),
      sliderDown: (b) => b.noise({ d: 0.012, f: 3000, q: 6, g: 0.3 }),
      notify: (b) => { b.noise({ d: 0.12, f: 2000, q: 1, g: 0.16 }); b.tone({ t: 0.12, d: 0.12, f: 1318, type: "triangle", g: 0.25 }); b.tone({ t: 0.21, d: 0.18, f: 1760, type: "triangle", g: 0.25 }); },
      launch: (b) => { b.noise({ d: 0.65, f: 900, f2: 5000, q: 1.5, g: 0.22, a: 0.4 }); b.tone({ t: 0.45, d: 0.45, f: 220, f2: 880, type: "triangle", g: 0.22, a: 0.02 }); },
      type: (b) => b.noise({ d: 0.015, f: 3500, q: 3, g: 0.3 }),
    },
  },
];

/** Target peak per sound (before the volume slider): small UI ticks stay quieter than big events. */
const LEVEL: Record<Cat, number> = {
  nav: 0.28, sliderUp: 0.26, sliderDown: 0.26, type: 0.3, tab: 0.38, edge: 0.42, select: 0.45,
  toggleOn: 0.42, toggleOff: 0.42, open: 0.42, close: 0.4, notify: 0.52, launch: 0.55,
};

function driveCurve(k: number): Float32Array {
  const c = new Float32Array(1024);
  for (let i = 0; i < c.length; i++) { const x = (i / (c.length - 1)) * 2 - 1; c[i] = Math.tanh(k * x) / Math.tanh(k); }
  return c;
}

/** Renders one sound of a pack to a mono Float32 buffer at the given volume (0..1). */
export async function render(pack: Pack, cat: Cat, volume: number): Promise<Float32Array> {
  const fx = pack.fx;
  // Generous length; trailing silence is trimmed after rendering.
  const len = cat === "launch" ? 1.6 : cat === "notify" ? 1.0 : 0.7;
  const ctx = new OfflineAudioContext(1, Math.ceil(len * RATE), RATE);
  const bus = ctx.createGain();
  let node: AudioNode = bus;
  const chain = (n: AudioNode) => { node.connect(n); node = n; };
  if (fx.speaker) {
    const hp = ctx.createBiquadFilter(); hp.type = "highpass"; hp.frequency.value = fx.speaker[0]; hp.Q.value = 0.7; chain(hp);
    const lp = ctx.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = fx.speaker[1]; lp.Q.value = 1.1; chain(lp);
  }
  if (fx.drive && fx.drive > 1) { const ws = ctx.createWaveShaper(); ws.curve = driveCurve(fx.drive) as any; ws.oversample = "2x"; chain(ws); }
  if (fx.lp) { const lp = ctx.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = fx.lp; chain(lp); }
  node.connect(ctx.destination);
  if (fx.echo) {
    const dl = ctx.createDelay(1); dl.delayTime.value = fx.echo.time;
    const fb = ctx.createGain(); fb.gain.value = fx.echo.fb;
    // Rapid-fire sounds (focus moves, sliders, typing) get only a hint of echo so scrolling stays crisp.
    const quick = cat === "nav" || cat === "sliderUp" || cat === "sliderDown" || cat === "type";
    const wet = ctx.createGain(); wet.gain.value = fx.echo.mix * (quick ? 0.3 : 1);
    if (quick) fb.gain.value = fx.echo.fb * 0.5;
    const damp = ctx.createBiquadFilter(); damp.type = "lowpass"; damp.frequency.value = 3500;
    node.connect(dl); dl.connect(damp).connect(fb).connect(dl); damp.connect(wet).connect(ctx.destination);
  }
  pack.sounds[cat](new Builder(ctx, bus));
  const buf = await ctx.startRendering();
  let data = buf.getChannelData(0);

  if (fx.crush) {
    const steps = Math.pow(2, fx.crush - 1);
    let peak0 = 0; for (const v of data) peak0 = Math.max(peak0, Math.abs(v));
    const k = peak0 > 0 ? 1 / peak0 : 1;
    for (let i = 0; i < data.length; i++) data[i] = (Math.round(data[i] * k * steps) / steps) / k;
  }
  // Trim the silent tail, then a 4 ms fade so nothing clicks at the end.
  let end = data.length;
  while (end > 1 && Math.abs(data[end - 1]) < 0.0008) end--;
  end = Math.min(data.length, end + Math.floor(0.004 * RATE));
  data = data.slice(0, Math.max(end, Math.floor(0.02 * RATE)));
  const fade = Math.min(data.length, Math.floor(0.004 * RATE));
  for (let i = 0; i < fade; i++) data[data.length - 1 - i] *= i / fade;
  // Normalise to this sound's level.
  let peak = 0; for (const v of data) peak = Math.max(peak, Math.abs(v));
  const gain = peak > 0 ? (LEVEL[cat] * volume) / peak : 0;
  for (let i = 0; i < data.length; i++) data[i] *= gain;
  return data;
}

/** 16-bit PCM mono WAV. */
export function wav(data: Float32Array, rate = RATE): Blob {
  const out = new DataView(new ArrayBuffer(44 + data.length * 2));
  const str = (o: number, s: string) => { for (let i = 0; i < s.length; i++) out.setUint8(o + i, s.charCodeAt(i)); };
  str(0, "RIFF"); out.setUint32(4, 36 + data.length * 2, true); str(8, "WAVE");
  str(12, "fmt "); out.setUint32(16, 16, true); out.setUint16(20, 1, true); out.setUint16(22, 1, true);
  out.setUint32(24, rate, true); out.setUint32(28, rate * 2, true); out.setUint16(32, 2, true); out.setUint16(34, 16, true);
  str(36, "data"); out.setUint32(40, data.length * 2, true);
  for (let i = 0; i < data.length; i++) {
    const v = Math.max(-1, Math.min(1, data[i]));
    out.setInt16(44 + i * 2, v < 0 ? v * 0x8000 : v * 0x7fff, true);
  }
  return new Blob([out.buffer], { type: "audio/wav" });
}

export const SILENT = () => wav(new Float32Array(441));
