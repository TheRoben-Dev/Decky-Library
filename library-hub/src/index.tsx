import {
  ButtonItem, ConfirmModal, Field, Navigation, PanelSection, PanelSectionRow, showModal, staticClasses,
} from "@decky/ui";
import { definePlugin, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { FaBoxOpen } from "react-icons/fa";
import {
  Dep, getStatus, installPlugin, installStorePlugin, installTheme, Item, reloadCssLoader, Status,
  uninstallPlugin, uninstallTheme,
} from "./backend";

const note = { fontSize: "12px", lineHeight: "16px", opacity: 0.75, whiteSpace: "normal" as const };
const warn = { ...note, color: "#FF9F1C", opacity: 1 };
const ok = { ...note, color: "#2BFF88", opacity: 1 };

const LEGACY_UPDATER = "Nightgrid Updater";
const CSS_LOADER = "CSS Loader";

function confirm(title: string, body: string, okText: string): Promise<boolean> {
  return new Promise((resolve) => {
    showModal(
      <ConfirmModal strTitle={title} strDescription={body} strOKButtonText={okText}
        onOK={() => resolve(true)} onCancel={() => resolve(false)} />,
    );
  });
}

function openSteamStore(appid: number) {
  Navigation.CloseSideMenus();
  (window as any).SteamClient?.URL?.ExecuteSteamURL?.(`steam://store/${appid}`);
}

function DepRow({ d, busy, onInstallDecky }: { d: Dep; busy: boolean; onInstallDecky: (name: string) => void }) {
  if (d.installed) return <div style={ok}>✓ {d.name}</div>;
  return (
    <>
      <div style={warn}>Needs {d.name}{d.why ? ` (${d.why})` : ""}, which isn't installed.</div>
      {d.kind === "decky"
        ? <ButtonItem layout="below" disabled={busy} onClick={() => onInstallDecky(d.name)}>Install {d.name}</ButtonItem>
        : <ButtonItem layout="below" onClick={() => openSteamStore(d.appid!)}>Open {d.name} in the Steam store</ButtonItem>}
    </>
  );
}

function ItemRows({ it, busy, act }: { it: Item; busy: boolean; act: (fn: () => Promise<string | null>, done?: string) => void }) {
  const ver = it.installedVersion
    ? (it.updateAvailable ? `${it.installedVersion} → ${it.latest}` : `${it.installedVersion} · up to date`)
    : `not installed · ${it.latest}`;
  const mainLabel = !it.installed ? "Install" : it.updateAvailable ? `Update to ${it.latest}` : null;

  const install = () => it.kind === "theme"
    ? act(async () => {
      const r = await installTheme();
      if (!r.ok) return `Nightgrid: ${r.error}`;
      const reloaded = await reloadCssLoader();
      return reloaded ? null : `Nightgrid ${r.version} installed. Open CSS Loader and press Refresh to apply it.`;
    }, "Nightgrid installed.")
    : act(() => installPlugin(it.id), `Confirm the install in Decky's prompt.`);

  const remove = async () => {
    if (!(await confirm(`Uninstall ${it.name}?`, it.kind === "theme"
      ? "Removes the Nightgrid theme and its saved options from CSS Loader."
      : `Removes the ${it.name} plugin and its Decky settings.`, "Uninstall"))) return;
    act(async () => {
      if (it.kind === "theme") {
        const r = await uninstallTheme();
        if (!r.ok) return r.error ?? "failed";
        await reloadCssLoader();
        return null;
      }
      return uninstallPlugin(it.name);
    }, `${it.name} uninstalled.`);
  };

  return (
    <>
      <PanelSectionRow>
        <Field label={it.name} description={ver} bottomSeparator="none" />
      </PanelSectionRow>
      {it.deps.filter((d) => d.name !== CSS_LOADER).map((d) => (
        <PanelSectionRow key={d.name}>
          <DepRow d={d} busy={busy} onInstallDecky={(n) => act(() => installStorePlugin(n), `Confirm the ${n} install in Decky's prompt.`)} />
        </PanelSectionRow>
      ))}
      {mainLabel && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={install}>{mainLabel}</ButtonItem>
        </PanelSectionRow>
      )}
      {it.installed && !it.isSelf && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={remove}>Uninstall</ButtonItem>
        </PanelSectionRow>
      )}
    </>
  );
}

function Content() {
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; bad: boolean } | null>(null);

  const refresh = async () => { try { setStatus(await getStatus()); } catch (e) { setMsg({ text: String(e), bad: true }); } };
  const check = async () => { setBusy(true); setMsg(null); try { await refresh(); } finally { setBusy(false); } };

  // Runs one action; Decky installs finish in the background, so look again a little later too.
  const act = async (fn: () => Promise<string | null>, done?: string) => {
    setBusy(true);
    setMsg(null);
    try {
      const err = await fn();
      setMsg(err ? { text: err, bad: true } : done ? { text: done, bad: false } : null);
      await refresh();
      setTimeout(refresh, 4000);
      setTimeout(refresh, 12000);
    } finally { setBusy(false); }
  };

  useEffect(() => { check(); }, []);

  const s = status;
  const self = s?.items.find((i) => i.isSelf);
  const others = s?.items.filter((i) => !i.isSelf) ?? [];

  return (
    <>
      {s && !s.cssLoader && (
        <PanelSection title="CSS Loader">
          <PanelSectionRow>
            <div style={warn}>CSS Loader isn't installed. The Nightgrid theme needs it.</div>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy}
              onClick={() => act(() => installStorePlugin(CSS_LOADER), "Confirm the CSS Loader install in Decky's prompt.")}>
              Install CSS Loader
            </ButtonItem>
          </PanelSectionRow>
        </PanelSection>
      )}
      <PanelSection title="Library">
        {!s && <PanelSectionRow><div style={note}>Checking releases…</div></PanelSectionRow>}
        {s?.error && <PanelSectionRow><div style={warn}>{s.error}</div></PanelSectionRow>}
        {s && !s.error && others.length === 0 && (
          <PanelSectionRow><div style={note}>No releases published yet.</div></PanelSectionRow>
        )}
        {others.map((it) => <ItemRows key={it.id} it={it} busy={busy} act={act} />)}
        {msg && <PanelSectionRow><div style={msg.bad ? warn : note}>{msg.text}</div></PanelSectionRow>}
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={check}>{busy ? "Working…" : "Check for updates"}</ButtonItem>
        </PanelSectionRow>
      </PanelSection>
      <PanelSection title="Library Hub">
        {self && <ItemRows it={self} busy={busy} act={act} />}
        <PanelSectionRow>
          <div style={note}>
            Everything comes from TheRoben-Dev/Decky-Library releases over HTTPS and must match the
            published SHA-256. Plugins install through Decky's own installer; theme options are kept.
          </div>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}

export default definePlugin(() => {
  // One quiet check per boot: replace the old Nightgrid Updater, and toast when updates exist.
  setTimeout(async () => {
    try {
      const s = await getStatus();
      if (s.legacyUpdater) {
        const err = await uninstallPlugin(LEGACY_UPDATER);
        if (!err) toaster.toast({ title: "Library Hub", body: "Removed Nightgrid Updater; Library Hub replaces it." });
      }
      const n = s.items.filter((i) => i.updateAvailable).length;
      if (n) toaster.toast({ title: "Library Hub", body: `${n} update${n > 1 ? "s" : ""} available.` });
    } catch { /* offline: stay quiet */ }
  }, 15000);

  return {
    name: "Library Hub",
    titleView: <div className={staticClasses.Title}>Library Hub</div>,
    content: <Content />,
    icon: <FaBoxOpen />,
  };
});
