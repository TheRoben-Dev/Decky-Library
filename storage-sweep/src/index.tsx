import { ButtonItem, ConfirmModal, Field, PanelSectionRow, Router, showModal, staticClasses } from "@decky/ui";
import { definePlugin, toaster } from "@decky/api";
import { useState } from "react";
import { FaBroom } from "react-icons/fa";
import { Entry, Kind, remove, scan } from "./backend";
import { sectionFactory } from "./section";

const Section = sectionFactory("storage-sweep");
const SHORTCUT = 0x40000000;
const note = { fontSize: "12px", lineHeight: "16px", opacity: 0.75, whiteSpace: "normal" as const };
const warn = { ...note, color: "var(--ng-warn, #FF9F1C)", opacity: 1 };
const data = { color: "var(--ng-data, #00E5FF)", fontVariantNumeric: "tabular-nums" as const };

function size(b: number): string {
  if (b < 1024 * 1024) return `${Math.max(0, Math.round(b / 1024))} KB`;
  if (b < 1024 ** 3) return `${(b / 1024 ** 2).toFixed(b < 10 * 1024 ** 2 ? 1 : 0)} MB`;
  return `${(b / 1024 ** 3).toFixed(2)} GB`;
}
const sum = (xs: Entry[]) => xs.reduce((a, e) => a + e.bytes, 0);

function nameOf(appid: number): string {
  try {
    const o = (window as any).appStore?.GetAppOverviewByAppID(appid);
    if (o?.display_name) return o.display_name;
  } catch { /* unknown app */ }
  return appid >= 2 ** 31 ? "Removed shortcut" : `App ${appid}`;
}

function shortcutIds(): number[] {
  try {
    const all: any[] = (window as any).collectionStore?.allAppsCollection?.allApps ?? [];
    return all.filter((a) => a?.app_type === SHORTCUT).map((a) => Number(a.appid));
  } catch { return []; }
}

const running = () => Number((Router.MainRunningApp as any)?.appid ?? 0);

// Module state: Steam remounts the panel on every open and after each modal.
let result: { entries: Entry[]; missing: string[]; at: number } | null = null;

const ORPHAN: Record<Kind, { title: string; about: string }> = {
  shadercache: { title: "Shader caches", about: "Compiled shaders of games you've uninstalled. Always safe; a game rebuilds them if you reinstall it." },
  workshop: { title: "Workshop files", about: "Downloaded mods of uninstalled games. Steam downloads them again if you reinstall." },
  compatdata: { title: "Proton prefixes", about: "The Windows folder of uninstalled games. It can hold save files that aren't in Steam Cloud, so check first." },
};

function confirm(title: string, body: string, ok: string, run: () => void) {
  showModal(<ConfirmModal strTitle={title} strDescription={body} strOKButtonText={ok} strCancelButtonText="Cancel" onOK={run} />);
}

function Content() {
  const [, force] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const r = result;

  const doScan = async () => {
    setBusy("scan"); setErr(null);
    try {
      const res = await scan(shortcutIds(), running());
      if (!res.ok) { setErr(res.error); return; }
      result = { entries: res.entries, missing: res.missing, at: Date.now() };
    } catch (e) { setErr(String(e)); } finally { setBusy(null); force((n) => n + 1); }
  };

  const doDelete = async (entries: Entry[], label: string) => {
    setBusy(label); setErr(null);
    try {
      const res = await remove(entries.map((e) => e.path), running());
      if (!res.ok) { setErr(res.error); return; }
      const gone = new Set(res.deleted);
      if (result) result = { ...result, entries: result.entries.filter((e) => !gone.has(e.path)) };
      toaster.toast({ title: "Storage Sweep", body: `Freed ${size(res.freed)}${res.failed.length ? ` · ${res.failed.length} couldn't be removed` : ""}` });
      if (res.failed.length) setErr(res.failed.map((f) => f.error).filter((v, i, a) => a.indexOf(v) === i).join("; "));
    } catch (e) { setErr(String(e)); } finally { setBusy(null); force((n) => n + 1); }
  };

  const orphans = (k: Kind) => r?.entries.filter((e) => e.kind === k && e.orphan) ?? [];
  const reclaim = r ? sum(r.entries.filter((e) => e.orphan && e.kind !== "compatdata")) : 0;
  const caches = r?.entries.filter((e) => e.kind === "shadercache" && !e.orphan) ?? [];

  return (
    <>
      <Section id="status" title="Storage" collapsible={false}>
        <PanelSectionRow>
          <Field label="Left behind by removed games" bottomSeparator="none">
            <span style={data}>{r ? size(reclaim) : "—"}</span>
          </Field>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={!!busy} onClick={doScan}>
            {busy === "scan" ? "Scanning…" : r ? "Scan again" : "Scan"}
          </ButtonItem>
        </PanelSectionRow>
        {r && r.missing.length > 0 && <PanelSectionRow><div style={warn}>
          {r.missing.length === 1 ? "A library folder isn't reachable" : `${r.missing.length} library folders aren't reachable`} (SD card out?), so Proton prefixes aren't offered for cleanup.
        </div></PanelSectionRow>}
        {err && <PanelSectionRow><div style={warn}>{err}</div></PanelSectionRow>}
      </Section>

      {r && (
        <Section id="orphans" title="Removed games" defaultOpen summary={size(sum(r.entries.filter((e) => e.orphan)))}>
          {(["shadercache", "workshop", "compatdata"] as Kind[]).map((k) => {
            const list = orphans(k);
            if (!list.length) return null;
            const label = `${ORPHAN[k].title}: ${size(sum(list))}`;
            const body = `${ORPHAN[k].about}\n\n${list.slice(0, 8).map((e) => `${nameOf(e.appid)} · ${size(e.bytes)}`).join("\n")}${list.length > 8 ? `\n…and ${list.length - 8} more` : ""}`;
            return (
              <PanelSectionRow key={k}>
                <ButtonItem layout="below" disabled={!!busy} description={`${list.length} folder${list.length > 1 ? "s" : ""}`}
                  onClick={() => confirm(`Delete ${ORPHAN[k].title.toLowerCase()}?`, body, `Delete ${size(sum(list))}`, () => doDelete(list, k))}>
                  {busy === k ? "Deleting…" : label}
                </ButtonItem>
              </PanelSectionRow>
            );
          })}
          {!r.entries.some((e) => e.orphan) && <PanelSectionRow><div style={note}>Nothing left behind. Clean.</div></PanelSectionRow>}
        </Section>
      )}

      {r && caches.length > 0 && (
        <Section id="caches" title="Shader caches" summary={`${size(sum(caches))} in ${caches.length} games`}>
          <PanelSectionRow><div style={note}>Resetting a game's cache fixes stutter or glitches after driver/Proton updates. It rebuilds while you play, so the first minutes may stutter.</div></PanelSectionRow>
          {caches.slice(0, 15).map((e) => (
            <PanelSectionRow key={e.path}>
              <ButtonItem layout="below" disabled={!!busy} description={size(e.bytes)}
                onClick={() => confirm(`Reset shader cache?`, `${nameOf(e.appid)} · ${size(e.bytes)}. Steam rebuilds it the next time the game runs.`, "Reset", () => doDelete([e], e.path))}>
                {busy === e.path ? "Deleting…" : nameOf(e.appid)}
              </ButtonItem>
            </PanelSectionRow>
          ))}
        </Section>
      )}

      <Section id="about" title="About" summary="Scans only when you press Scan">
        <PanelSectionRow>
          <div style={note}>
            Looks in every Steam library (internal, SD card, external) for shader caches, workshop files and Proton
            prefixes whose game is no longer installed. Games on an SD card that's out count as installed. The running
            game and non-Steam shortcut prefixes are never touched. Nothing runs in the background.
          </div>
        </PanelSectionRow>
      </Section>
    </>
  );
}

export default definePlugin(() => ({
  name: "Storage Sweep",
  titleView: <div className={staticClasses.Title}>Storage Sweep</div>,
  content: <Content />,
  icon: <FaBroom />,
}));
