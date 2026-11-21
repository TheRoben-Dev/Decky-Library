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

interface Note { t?: number; d: number; s: number; s2?: number; g?: number }
interface Score { notes: Note[]; click?: number; swell?: number }

// Semitones relative to the pack's base pitch.
const SCORE: Record<Cat, Score> = {
  nav: { notes: [{ d: 0.032, s: 12, g: 0.45 }], click: 0.35 },
  select: { notes: [{ d: 0.05, s: 0, g: 0.75 }, { t: 0.05, d: 0.08, s: 7, g: 0.75 }] },
  open: { notes: [{ d: 0.13, s: -12, s2: 0, g: 0.55 }, { t: 0.09, d: 0.09, s: 7, g: 0.45 }] },
  close: { notes: [{ d: 0.13, s: 0, s2: -12, g: 0.55 }] },
  tab: { notes: [{ d: 0.08, s: -5, s2: 2, g: 0.55 }], click: 0.4 },
  edge: { notes: [{ d: 0.09, s: -24, g: 0.7 }, { t: 0.05, d: 0.06, s: -25, g: 0.4 }] },
  toggleOn: { notes: [{ d: 0.04, s: 0, g: 0.7 }, { t: 0.045, d: 0.07, s: 7, g: 0.7 }] },
  toggleOff: { notes: [{ d: 0.04, s: 7, g: 0.7 }, { t: 0.045, d: 0.07, s: 0, g: 0.7 }] },
  sliderUp: { notes: [{ d: 0.03, s: 10, g: 0.4 }] },
  sliderDown: { notes: [{ d: 0.03, s: 5, g: 0.4 }] },
  notify: { notes: [{ d: 0.12, s: 0, g: 0.6 }, { t: 0.08, d: 0.12, s: 4, g: 0.6 }, { t: 0.16, d: 0.26, s: 7, g: 0.6 }] },
  launch: {
    notes: [{ d: 0.42, s: -24, s2: 12, g: 0.45 }, { t: 0.3, d: 0.12, s: 0, g: 0.5 }, { t: 0.38, d: 0.12, s: 7, g: 0.5 },
      { t: 0.46, d: 0.42, s: 12, g: 0.55 }],
    swell: 0.35,
  },
  type: { notes: [{ d: 0.016, s: 19, g: 0.22 }], click: 0.8 },
};

export interface Pack {
  id: string; name: string; about: string;
  base: number;              // Hz for semitone 0
  wave: OscillatorType;
  lp: number;                // lowpass cutoff
  decay: number;             // multiplies note lengths
  gain: number;
  noise: number;             // click/static amount 0..1
  noiseHz: number;           // band centre for clicks
  detune?: number;           // cents, second detuned oscillator (0 = none)
  crush?: number;            // bit depth for a lo-fi edge (0 = off)
}

export const PACKS: Pack[] = [
  { id: "nightgrid", name: "Nightgrid", about: "Crisp terminal blips, cyan-bright.", base: 1318.5, wave: "square", lp: 6500, decay: 1, gain: 0.55, noise: 0.25, noiseHz: 4200 },
  { id: "pulse", name: "Grid Pulse", about: "Soft detuned synth, low and warm.", base: 659.25, wave: "sawtooth", lp: 2000, decay: 1.5, gain: 0.7, noise: 0, noiseHz: 2000, detune: 9 },
  { id: "static", name: "Data Static", about: "CRT clicks and lo-fi square tones.", base: 987.77, wave: "square", lp: 3200, decay: 0.85, gain: 0.5, noise: 0.7, noiseHz: 2600, crush: 6 },
  { id: "glass", name: "Ice Glass", about: "Pure sine chimes, quiet and clean.", base: 1760, wave: "sine", lp: 12000, decay: 1.8, gain: 0.8, noise: 0.08, noiseHz: 6000 },
];

const RATE = 44100;

function envelope(p: AudioParam, t: number, d: number, g: number) {
  p.setValueAtTime(0, t);
  p.linearRampToValueAtTime(g, t + Math.min(0.004, d / 4));
  p.exponentialRampToValueAtTime(0.0001, t + d);
}

let noiseBuf: AudioBuffer | null = null;
function noise(ctx: BaseAudioContext): AudioBuffer {
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

function burst(ctx: BaseAudioContext, out: AudioNode, t: number, d: number, g: number, hz: number) {
  const src = ctx.createBufferSource(); src.buffer = noise(ctx);
  const bp = ctx.createBiquadFilter(); bp.type = "bandpass"; bp.frequency.value = hz; bp.Q.value = 1.4;
  const amp = ctx.createGain(); envelope(amp.gain, t, d, g);
  src.connect(bp).connect(amp).connect(out);
  src.start(t); src.stop(t + d + 0.01);
}

/** Renders one category of a pack to a mono Float32 buffer (already including volume). */
export async function render(pack: Pack, cat: Cat, volume: number): Promise<Float32Array> {
  const sc = SCORE[cat];
  const notes = sc.notes.map((n) => ({ ...n, d: n.d * pack.decay }));
  const end = Math.max(0.03, ...notes.map((n) => (n.t ?? 0) + n.d), sc.swell ? 0.5 : 0) + 0.02;
  const ctx = new OfflineAudioContext(1, Math.ceil(end * RATE), RATE);
  const master = ctx.createGain(); master.gain.value = pack.gain * volume;
  const lp = ctx.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = pack.lp; lp.Q.value = 0.7;
  lp.connect(master).connect(ctx.destination);

  for (const n of notes) {
    const t = n.t ?? 0, g = n.g ?? 0.6;
    const f = pack.base * Math.pow(2, n.s / 12);
    const amp = ctx.createGain(); envelope(amp.gain, t, n.d, g);
    amp.connect(lp);
    for (const cents of pack.detune ? [-pack.detune, pack.detune] : [0]) {
      const o = ctx.createOscillator(); o.type = pack.wave; o.detune.value = cents;
      o.frequency.setValueAtTime(f, t);
      if (n.s2 !== undefined) o.frequency.exponentialRampToValueAtTime(pack.base * Math.pow(2, n.s2 / 12), t + n.d);
      const v = ctx.createGain(); v.gain.value = pack.detune ? 0.6 : 1;
      o.connect(v).connect(amp);
      o.start(t); o.stop(t + n.d + 0.01);
    }
  }
  const nz = pack.noise;
  // Key clicks always get a noise transient; other clicks scale with the pack's static amount.
  if (sc.click && (nz > 0 || cat === "type")) {
    burst(ctx, master, 0, 0.012 + 0.01 * nz, sc.click * (cat === "type" ? 1.6 : Math.max(nz, 0.3)), pack.noiseHz);
  }
  if (sc.swell && nz > 0) {
    const src = ctx.createBufferSource(); src.buffer = noise(ctx); src.loop = true;
    const hp = ctx.createBiquadFilter(); hp.type = "highpass"; hp.frequency.value = 1500;
    const amp = ctx.createGain();
    amp.gain.setValueAtTime(0.0001, 0); amp.gain.exponentialRampToValueAtTime(sc.swell * nz * 0.5, 0.35);
    amp.gain.exponentialRampToValueAtTime(0.0001, 0.5);
    src.connect(hp).connect(amp).connect(master); src.start(0); src.stop(0.5);
  }
  const buf = await ctx.startRendering();
  const data = buf.getChannelData(0);
  if (pack.crush) {
    const steps = Math.pow(2, pack.crush - 1);
    for (let i = 0; i < data.length; i++) data[i] = Math.round(data[i] * steps) / steps;
  }
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
