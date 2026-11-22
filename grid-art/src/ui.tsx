/* Nightgrid look for the full-screen browser. Colours follow the Nightgrid theme's tokens
 * when CSS Loader has it active, and fall back to the NIGHTGRID palette otherwise. */
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

/** Scoped stylesheet for the browser page (tiles, focus ring, scan-line header). */
export const PAGE_CSS = `
.ga-page { position: absolute; inset: 0; padding-top: 40px; box-sizing: border-box; background: ${C.bg0};
  background-image: linear-gradient(${C.line} 1px, transparent 1px), linear-gradient(90deg, ${C.line} 1px, transparent 1px);
  background-size: 48px 48px; background-position: -1px -1px; color: ${C.text0}; }
.ga-page::before { content: ""; position: absolute; inset: 0; background: linear-gradient(180deg, transparent, ${C.bg0} 70%); pointer-events: none; }
.ga-inner { position: relative; height: 100%; display: flex; flex-direction: column; }
.ga-head { display: flex; align-items: baseline; gap: 12px; padding: 10px 24px 6px; font-family: ${MONO}; }
.ga-head .t { font-size: 18px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
.ga-head .s { font-size: 12px; color: ${C.text1}; letter-spacing: .08em; text-transform: uppercase; }
.ga-head .as { font-size: 12px; color: ${C.text1}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.ga-head .as b { color: ${C.accent}; font-weight: 600; }
.ga-head .tag { margin-left: auto; font-size: 11px; color: ${C.data}; border: 1px solid ${C.data}; padding: 1px 6px; letter-spacing: .1em; }
.ga-tabs { flex: 1; min-height: 0; }
.ga-bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 0 0 10px; }
.ga-bar .lbl { font-family: ${MONO}; font-size: 11px; color: ${C.text1}; text-transform: uppercase; letter-spacing: .1em; }
.ga-btn.DialogButton { min-width: 0; width: auto; padding: 6px 14px; border-radius: 0; font-size: 13px; }
.ga-grid { display: grid; gap: 10px; padding-bottom: 24px; }
.ga-tile { position: relative; background: ${C.bg1}; border: 1px solid ${C.line}; overflow: hidden; cursor: pointer;
  transition: border-color 80ms linear, transform 80ms linear; }
.ga-tile img, .ga-tile video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block; }
.ga-tile.contain img, .ga-tile.contain video { object-fit: contain; padding: 8%; box-sizing: border-box;
  background: repeating-conic-gradient(${C.bg2} 0% 25%, ${C.bg1} 0% 50%) 50% / 16px 16px; }
.ga-tile.ga-focus { border-color: ${C.active}; transform: scale(1.03); z-index: 2; box-shadow: 0 0 14px color-mix(in srgb, ${C.active} 45%, transparent); }
.ga-tile .meta { position: absolute; left: 0; right: 0; bottom: 0; padding: 3px 6px; font-family: ${MONO}; font-size: 10px;
  color: ${C.text0}; background: color-mix(in srgb, ${C.bg0} 82%, transparent); opacity: 0; transition: opacity 80ms linear;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ga-tile.ga-focus .meta { opacity: 1; }
.ga-tile .mark { position: absolute; top: 0; right: 0; padding: 2px 6px; font-family: ${MONO}; font-size: 10px; font-weight: 700;
  color: ${C.bg0}; background: ${C.ok}; letter-spacing: .08em; }
.ga-tile .busy { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-family: ${MONO};
  font-size: 11px; letter-spacing: .1em; color: ${C.data}; background: color-mix(in srgb, ${C.bg0} 70%, transparent); }
.ga-msg { font-family: ${MONO}; font-size: 13px; color: ${C.text1}; padding: 24px 0; white-space: normal; }
.ga-msg.err { color: ${C.warn}; }
`;
