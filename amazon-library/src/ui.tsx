/* Nightgrid look. Colours follow the Nightgrid theme's tokens when CSS Loader has it active,
 * and fall back to the NIGHTGRID palette otherwise (same values as nightgrid-theme). */

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

export const PAGE_CSS = `
.al-page { position: absolute; inset: 0; padding-top: 40px; box-sizing: border-box; background: ${C.bg0};
  background-image: linear-gradient(${C.line} 1px, transparent 1px), linear-gradient(90deg, ${C.line} 1px, transparent 1px);
  background-size: 48px 48px; background-position: -1px -1px; color: ${C.text0}; }
.al-page::before { content: ""; position: absolute; inset: 0; background: linear-gradient(180deg, transparent, ${C.bg0} 70%); pointer-events: none; }
.al-inner { position: relative; height: 100%; display: flex; flex-direction: column; }
.al-head { display: flex; align-items: center; gap: 12px; padding: 10px 24px 6px; font-family: ${MONO}; flex-wrap: wrap; }
.al-head .t { font-size: 18px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
.al-head .s { font-size: 12px; color: ${C.text1}; letter-spacing: .08em; text-transform: uppercase; }
.al-head .tag { font-size: 11px; color: ${C.data}; border: 1px solid ${C.data}; padding: 1px 6px; letter-spacing: .1em; }
.al-head .grow { flex: 1; }
.al-tabs { flex: 1; min-height: 0; }
.al-bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 0 0 10px; }
.al-bar .lbl { font-family: ${MONO}; font-size: 11px; color: ${C.text1}; text-transform: uppercase; letter-spacing: .1em; }
.al-btn.DialogButton { min-width: 0; width: auto; padding: 6px 14px; border-radius: 0; font-size: 13px; }
.al-btn.primary.DialogButton { background: ${C.active}; color: ${C.bg0}; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
.al-btn.primary.DialogButton.gpfocus, .al-btn.primary.DialogButton:hover { background: ${C.text0}; }
.al-grid { display: grid; gap: 12px; padding: 0 24px 32px; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); }
.al-tile { position: relative; background: ${C.bg1}; border: 1px solid ${C.line}; overflow: hidden; cursor: pointer;
  transition: border-color 80ms linear, transform 80ms linear; display: flex; flex-direction: column; }
.al-tile .art { position: relative; aspect-ratio: 3 / 4; background: ${C.bg2}; overflow: hidden; }
.al-tile .art img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block; }
.al-tile .art .none { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; padding: 10px;
  text-align: center; font-family: ${MONO}; font-size: 13px; color: ${C.text1}; text-transform: uppercase; letter-spacing: .06em; }
.al-tile .name { padding: 6px 8px 2px; font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.al-tile .sub { padding: 0 8px 7px; display: flex; gap: 4px; align-items: center; min-height: 18px; font-family: ${MONO}; font-size: 10px; color: ${C.text1};
  white-space: nowrap; overflow: hidden; }
.al-tile.al-focus { border-color: ${C.active}; transform: scale(1.03); z-index: 2; box-shadow: 0 0 14px color-mix(in srgb, ${C.active} 45%, transparent); }
.al-tile .badge { position: absolute; top: 0; right: 0; padding: 2px 6px; font-family: ${MONO}; font-size: 10px; font-weight: 700;
  letter-spacing: .08em; color: ${C.bg0}; background: ${C.ok}; }
.al-tile .badge.upd { background: ${C.accent}; }
.al-tile .badge.dl { background: ${C.data}; }
.al-tile .prog { position: absolute; left: 0; right: 0; bottom: 0; }
.al-msg { font-family: ${MONO}; font-size: 13px; color: ${C.text1}; padding: 24px; white-space: normal; line-height: 1.5; }
.al-msg.err { color: ${C.warn}; }
.al-detail { display: flex; align-items: flex-start; gap: 28px; padding: 8px 24px 32px; overflow-y: auto; flex: 1; min-height: 0; }
.al-detail .cover { flex: 0 0 300px; }
.al-detail .cover .frame { aspect-ratio: 3 / 4; border: 1px solid ${C.data}; box-shadow: 0 0 18px color-mix(in srgb, ${C.data} 30%, transparent);
  background: ${C.bg1}; overflow: hidden; position: relative; }
.al-detail .cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.al-detail .info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 12px; }
.al-detail .info > * { flex-shrink: 0; }
.al-detail h1 { margin: 0; font-family: ${MONO}; font-size: 26px; letter-spacing: .04em; text-transform: uppercase; line-height: 1.15; }
.al-detail .by { color: ${C.text1}; font-size: 13px; }
.al-detail .short { color: ${C.text0}; opacity: .85; font-size: 14px; line-height: 1.45; }
.al-panel { border: 1px solid ${C.line}; background: color-mix(in srgb, ${C.bg1} 88%, transparent); padding: 12px 14px; display: flex; flex-direction: column; gap: 8px; }
.al-panel .k { font-family: ${MONO}; font-size: 11px; color: ${C.text1}; text-transform: uppercase; letter-spacing: .1em; }
.al-panel .v { font-size: 13px; word-break: break-all; }
.al-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.al-kv { display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; align-items: baseline; }
.al-signin { display: flex; gap: 32px; padding: 16px 24px; align-items: flex-start; flex-wrap: wrap; overflow-y: auto; }
.al-qr { background: #fff; padding: 14px; border: 2px solid ${C.data}; box-shadow: 0 0 22px color-mix(in srgb, ${C.data} 40%, transparent); line-height: 0; }
.al-qr svg { width: 240px; height: 240px; display: block; }
.al-steps { flex: 1; min-width: 300px; display: flex; flex-direction: column; gap: 12px; font-size: 14px; line-height: 1.5; }
.al-steps ol { margin: 0; padding-left: 20px; color: ${C.text1}; }
.al-steps b { color: ${C.text0}; }
.al-code { font-family: ${MONO}; font-size: 12px; color: ${C.data}; word-break: break-all; }

.al-hero { position: absolute; inset: 0; background-size: cover; background-position: center; opacity: .22; filter: saturate(1.1); pointer-events: none;
  mask-image: linear-gradient(180deg, #000 0%, transparent 75%); -webkit-mask-image: linear-gradient(180deg, #000 0%, transparent 75%); }
.al-chip { font-family: ${MONO}; font-size: 10px; letter-spacing: .06em; padding: 0 4px; border: 1px solid ${C.line}; color: ${C.text1}; text-transform: uppercase; }
.al-chip.free { color: ${C.ok}; border-color: color-mix(in srgb, ${C.ok} 50%, transparent); }
.al-chip.code { color: ${C.data}; border-color: color-mix(in srgb, ${C.data} 50%, transparent); }
.al-chip.done { color: ${C.accent}; border-color: color-mix(in srgb, ${C.accent} 50%, transparent); }
.al-shots { display: flex; gap: 10px; overflow-x: auto; overflow-y: hidden; padding: 6px 6px 10px; flex-shrink: 0; scroll-behavior: smooth; }
.al-shot { flex: 0 0 auto; width: 260px; height: 146px; aspect-ratio: 16 / 9; background: ${C.bg2}; border: 1px solid ${C.line}; overflow: hidden;
  transition: border-color 80ms linear, transform 80ms linear; }
.al-shot img { width: 100%; height: 100%; object-fit: cover; display: block; }
.al-shot.al-focus { border-color: ${C.active}; transform: scale(1.03); box-shadow: 0 0 14px color-mix(in srgb, ${C.active} 45%, transparent); }
.al-about { font-size: 14px; line-height: 1.55; color: ${C.text0}; opacity: .9; white-space: pre-line; }
`;
