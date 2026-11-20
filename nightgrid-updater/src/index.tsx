import { ButtonItem, PanelSection, PanelSectionRow, Field, staticClasses } from "@decky/ui";
import { definePlugin, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { FaSyncAlt } from "react-icons/fa";
import { getStatus, installLatest, reloadCssLoader, Status } from "./backend";

const note = { fontSize: "12px", lineHeight: "16px", opacity: 0.75, whiteSpace: "normal" as const };
const warn = { ...note, color: "#FF9F1C", opacity: 1 };

function Content() {
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState<"check" | "install" | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const check = async () => {
    setBusy("check");
    setMsg(null);
    try { setStatus(await getStatus()); } finally { setBusy(null); }
  };

  const install = async () => {
    setBusy("install");
    setMsg(null);
    try {
      const r = await installLatest();
      if (!r.ok) { setMsg(`Update failed: ${r.error}`); return; }
      const reloaded = await reloadCssLoader();
      setMsg(reloaded
        ? `Nightgrid ${r.version} installed and CSS Loader reloaded.`
        : `Nightgrid ${r.version} installed. Open CSS Loader and press Refresh to apply it.`);
      setStatus(await getStatus());
    } finally { setBusy(null); }
  };

  useEffect(() => { check(); }, []);

  const s = status;
  const label = !s ? "Checking…"
    : s.updateAvailable ? (s.installed ? `Update to ${s.latest}` : `Install ${s.latest}`)
    : "Up to date";

  return (
    <PanelSection title="Nightgrid theme">
      <PanelSectionRow>
        <Field label="Installed" bottomSeparator="none">{s?.installed ?? (s ? "not installed" : "…")}</Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field label="Latest release" bottomSeparator="none">{s?.latest ?? (s?.error ? "unknown" : "…")}</Field>
      </PanelSectionRow>
      {s?.error && <PanelSectionRow><div style={warn}>{s.error}</div></PanelSectionRow>}
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={!s?.updateAvailable || busy !== null} onClick={install}>
          {busy === "install" ? "Installing…" : label}
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy !== null} onClick={check}>
          {busy === "check" ? "Checking…" : "Check for updates"}
        </ButtonItem>
      </PanelSectionRow>
      {msg && <PanelSectionRow><div style={note}>{msg}</div></PanelSectionRow>}
      <PanelSectionRow>
        <div style={note}>
          Downloads come only from TheRoben-Dev/Decky-Library releases over HTTPS and must match the
          published SHA-256. Your Nightgrid options are kept.
        </div>
      </PanelSectionRow>
    </PanelSection>
  );
}

export default definePlugin(() => {
  // One quiet check per boot: a toast only when there's something to install.
  setTimeout(async () => {
    try {
      const s = await getStatus();
      if (s.updateAvailable && s.installed) {
        toaster.toast({ title: "Nightgrid update", body: `${s.latest} is available (you have ${s.installed}).` });
      }
    } catch { /* offline: stay quiet */ }
  }, 15000);

  return {
    name: "Nightgrid Updater",
    titleView: <div className={staticClasses.Title}>Nightgrid Updater</div>,
    content: <Content />,
    icon: <FaSyncAlt />,
  };
});
