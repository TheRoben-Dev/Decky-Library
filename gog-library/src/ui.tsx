/* Nightgrid look. Colours follow the Nightgrid theme's tokens when CSS Loader has it active,
 * and fall back to the NIGHTGRID palette otherwise (same values as nightgrid-theme). */
import { Platform } from "./backend";

export const C = {
  bg0: "var(--ng-bg-0, #07080B)",
  bg1: "var(--ng-bg-1, #0D0F14)",
  bg2: "var(--ng-bg-2, #141821)",
  line: "var(--ng-line, #1F2633)",
  text0: "var(--ng-text-0, #E6EDF3)",
  text1: "var(--ng-text-1, #8B98A9)",
  active: "var(--ng-active, #FF2A6D)",
  data: "var(--ng-data, #00E5FF)",
  accent: "var(--ng-accent, #F3E600)",
  ok: "var(--ng-ok, #2BFF88)",
  warn: "var(--ng-warn, #FF9F1C)",
};

export const MONO = "'JetBrains Mono', 'Fira Code', ui-monospace, monospace";

export const note = { fontSize: "12px", lineHeight: "16px", opacity: 0.75, whiteSpace: "normal" as const };
export const warn = { ...note, color: C.warn, opacity: 1 };

export function Bar({ value, color = C.data }: { value: number; color?: string }) {
  return (
    <div style={{ height: "4px", background: C.line, width: "100%" }}>
      <div style={{ height: "100%", width: `${Math.max(0, Math.min(100, value * 100))}%`, background: color,
        boxShadow: `0 0 8px ${color}`, transition: "width 200ms linear" }} />
    </div>
  );
}

export function Plats({ list }: { list: Platform[] }) {
  const names: Record<string, string> = { linux: "LINUX", windows: "WIN", mac: "MAC" };
  return <>{list.map((p) => <span key={p} className={`gl-plat ${p}`}>{names[p] ?? p}</span>)}</>;
}

export const PAGE_CSS = `
.gl-page { position: absolute; inset: 0; padding-top: 40px; box-sizing: border-box; background: ${C.bg0};
  background-image: linear-gradient(${C.line} 1px, transparent 1px), linear-gradient(90deg, ${C.line} 1px, transparent 1px);
  background-size: 48px 48px; background-position: -1px -1px; color: ${C.text0}; }
.gl-page::before { content: ""; position: absolute; inset: 0; background: linear-gradient(180deg, transparent, ${C.bg0} 70%); pointer-events: none; }
.gl-inner { position: relative; height: 100%; display: flex; flex-direction: column; }
.gl-head { display: flex; align-items: center; gap: 12px; padding: 10px 24px 6px; font-family: ${MONO}; flex-wrap: wrap; }
.gl-head .t { font-size: 18px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
.gl-head .s { font-size: 12px; color: ${C.text1}; letter-spacing: .08em; text-transform: uppercase; }
.gl-head .tag { font-size: 11px; color: ${C.data}; border: 1px solid ${C.data}; padding: 1px 6px; letter-spacing: .1em; }
.gl-head .grow { flex: 1; }
.gl-tabs { flex: 1; min-height: 0; }
.gl-bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 0 0 10px; }
.gl-bar .lbl { font-family: ${MONO}; font-size: 11px; color: ${C.text1}; text-transform: uppercase; letter-spacing: .1em; }
.gl-btn.DialogButton { min-width: 0; width: auto; padding: 6px 14px; border-radius: 0; font-size: 13px; }
.gl-btn.primary.DialogButton { background: ${C.active}; color: ${C.bg0}; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
.gl-btn.primary.DialogButton.gpfocus, .gl-btn.primary.DialogButton:hover { background: ${C.text0}; }
.gl-grid { display: grid; gap: 12px; padding: 0 24px 32px; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
.gl-tile { position: relative; background: ${C.bg1}; border: 1px solid ${C.line}; overflow: hidden; cursor: pointer;
  transition: border-color 80ms linear, transform 80ms linear; display: flex; flex-direction: column; }
.gl-tile .art { position: relative; aspect-ratio: 16 / 9; background: ${C.bg2}; overflow: hidden; }
.gl-tile .art img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block; }
.gl-tile .art .none { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; padding: 10px;
  text-align: center; font-family: ${MONO}; font-size: 13px; color: ${C.text1}; text-transform: uppercase; letter-spacing: .06em; }
.gl-tile .name { padding: 6px 8px 2px; font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gl-tile .sub { padding: 0 8px 7px; display: flex; gap: 4px; align-items: center; min-height: 18px; font-family: ${MONO}; font-size: 10px; color: ${C.text1};
  white-space: nowrap; overflow: hidden; }
.gl-tile.gl-focus { border-color: ${C.active}; transform: scale(1.03); z-index: 2; box-shadow: 0 0 14px color-mix(in srgb, ${C.active} 45%, transparent); }
.gl-tile .badge { position: absolute; top: 0; right: 0; padding: 2px 6px; font-family: ${MONO}; font-size: 10px; font-weight: 700;
  letter-spacing: .08em; color: ${C.bg0}; background: ${C.ok}; }
.gl-tile .badge.upd { background: ${C.accent}; }
.gl-tile .badge.dl { background: ${C.data}; }
.gl-tile .prog { position: absolute; left: 0; right: 0; bottom: 0; }
.gl-plat { font-family: ${MONO}; font-size: 10px; letter-spacing: .06em; padding: 0 4px; border: 1px solid ${C.line}; color: ${C.text1}; }
.gl-plat.linux { color: ${C.ok}; border-color: color-mix(in srgb, ${C.ok} 50%, transparent); }
.gl-plat.windows { color: ${C.data}; border-color: color-mix(in srgb, ${C.data} 50%, transparent); }
.gl-plat.pad { color: ${C.accent}; border-color: color-mix(in srgb, ${C.accent} 50%, transparent); }
.gl-detail .bg { position: absolute; inset: 0; background-size: cover; background-position: center top; opacity: .18; filter: saturate(1.1); pointer-events: none;
  mask-image: linear-gradient(180deg, #000 0%, transparent 80%); }
.gl-msg { font-family: ${MONO}; font-size: 13px; color: ${C.text1}; padding: 24px; white-space: normal; line-height: 1.5; }
.gl-msg.err { color: ${C.warn}; }
.gl-detail { display: flex; gap: 28px; padding: 8px 24px 32px; overflow-y: auto; flex: 1; min-height: 0; }
.gl-detail .cover { flex: 0 0 380px; }
.gl-detail .cover .frame { aspect-ratio: 16 / 9; border: 1px solid ${C.data}; box-shadow: 0 0 18px color-mix(in srgb, ${C.data} 30%, transparent);
  background: ${C.bg1}; overflow: hidden; position: relative; }
.gl-detail .cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.gl-detail .info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 12px; }
.gl-detail h1 { margin: 0; font-family: ${MONO}; font-size: 26px; letter-spacing: .04em; text-transform: uppercase; line-height: 1.15; }
.gl-detail .by { color: ${C.text1}; font-size: 13px; }
.gl-detail .short { color: ${C.text0}; opacity: .85; font-size: 14px; line-height: 1.45; }
.gl-panel { border: 1px solid ${C.line}; background: color-mix(in srgb, ${C.bg1} 88%, transparent); padding: 12px 14px; display: flex; flex-direction: column; gap: 8px; }
.gl-panel .k { font-family: ${MONO}; font-size: 11px; color: ${C.text1}; text-transform: uppercase; letter-spacing: .1em; }
.gl-panel .v { font-size: 13px; word-break: break-all; }
.gl-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.gl-kv { display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; align-items: baseline; }
.gl-signin { display: flex; gap: 32px; padding: 16px 24px; align-items: flex-start; flex-wrap: wrap; overflow-y: auto; }
.gl-qr { background: #fff; padding: 14px; border: 2px solid ${C.data}; box-shadow: 0 0 22px color-mix(in srgb, ${C.data} 40%, transparent); line-height: 0; }
.gl-qr svg { width: 240px; height: 240px; display: block; }
.gl-steps { flex: 1; min-width: 300px; display: flex; flex-direction: column; gap: 12px; font-size: 14px; line-height: 1.5; }
.gl-steps ol { margin: 0; padding-left: 20px; color: ${C.text1}; }
.gl-steps b { color: ${C.text0}; }
.gl-code { font-family: ${MONO}; font-size: 12px; color: ${C.data}; word-break: break-all; }
`;
