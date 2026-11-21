import {
  ConfirmModal, DialogButton, DropdownItem, Field, Focusable, ModalRoot, PanelSectionRow, showModal,
  staticClasses, TextField, ToggleField,
} from "@decky/ui";
import { definePlugin, toaster, useQuickAccessVisible } from "@decky/api";
import { CSSProperties, ReactNode, useEffect, useRef, useState } from "react";
import { FaServer } from "react-icons/fa";
import * as api from "./backend";
import type { Host, Prefs, ProfileFile, ProfileMeta, Status } from "./backend";
import { sectionFactory } from "./section";

const Section = sectionFactory("nightgrid-control");

// Nightgrid tokens (the CSS Loader theme defines them; fallbacks are the NIGHTGRID palette).
const C = {
  data: "var(--ng-data, #00E5FF)", ok: "var(--ng-ok, #2BFF88)", warn: "var(--ng-warn, #FF9F1C)",
  danger: "var(--ng-danger, #FF003C)", active: "var(--ng-active, #FF2A6D)", dim: "var(--ng-text-1, #8B98A9)",
  line: "var(--ng-line, #1F2633)",
};
const note: CSSProperties = { fontSize: "12px", lineHeight: "16px", color: C.dim, whiteSpace: "normal" };
const mono: CSSProperties = { fontVariantNumeric: "tabular-nums", letterSpacing: "0.02em" };
const label: CSSProperties = { textTransform: "uppercase", letterSpacing: "0.06em", fontSize: "11px", fontWeight: 700 };

// ---------------------------------------------------------------- module state
// Steam remounts the panel each time Quick Access opens and after every modal, so the
// data lives here and components subscribe to it.

interface Model {
  loaded: boolean;
  profile: ProfileMeta;
  hosts: Host[];
  status: Record<number, Status>;
  prefs: Prefs;
  localAvailable: boolean;
  lastRefresh: number;
  refreshing: boolean;
  error: string | null;
  open: number | null; // expanded host
}

const M: Model = {
  loaded: false, profile: { source: null }, hosts: [], status: {}, prefs: { interval: 15, showClients: false },
  localAvailable: false, lastRefresh: 0, refreshing: false, error: null, open: null,
};
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((f) => f());

function useModel(): Model {
  const [, force] = useState(0);
  useEffect(() => {
    const f = () => force((n) => n + 1);
    listeners.add(f);
    return () => { listeners.delete(f); };
  }, []);
  return M;
}

function setStatus(list: Status[]) {
  const next: Record<number, Status> = {};
  for (const s of list) next[s.id] = s;
  M.status = next;
}

async function load() {
  const r = await api.getState();
  if (!r.ok) { M.error = r.error; emit(); return; }
  M.profile = r.profile; M.hosts = r.hosts; M.prefs = r.prefs; M.localAvailable = r.localAvailable;
  setStatus(r.status); M.loaded = true; M.error = r.profile.error ?? null;
  emit();
}

async function refreshNow(ids?: number[]) {
  if (!M.hosts.length) return;
  if (!ids) { M.refreshing = true; emit(); }
  try {
    const r = await api.refresh(ids ?? null);
    if (r.ok) { setStatus(r.status); if (!ids) M.lastRefresh = Date.now(); }
  } finally {
    if (!ids) M.refreshing = false;
    emit();
  }
}

// ---------------------------------------------------------------- formatting

const ONLINE = new Set(["ok"]);
const STATE: Record<string, { text: string; color: string }> = {
  ok: { text: "Online", color: C.ok }, offline: { text: "Offline", color: C.danger },
  auth: { text: "Login refused", color: C.warn }, hostkey: { text: "Key changed", color: C.danger },
  sleep: { text: "Asleep", color: C.dim }, away: { text: "Away", color: C.dim },
  error: { text: "Error", color: C.warn }, rebooting: { text: "Rebooting", color: C.data },
  stopping: { text: "Shutting down", color: C.data }, waking: { text: "Waking", color: C.data },
};

function tone(v: number | null | undefined, warn: number, bad: number): string {
  if (v == null) return C.dim;
  return v >= bad ? C.danger : v >= warn ? C.warn : C.data;
}

function uptime(s?: number | null): string | null {
  if (s == null) return null;
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return d > 0 ? `${d}d ${h}h` : h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function ago(ts: number): string {
  const s = Math.max(0, Math.round((Date.now() - ts) / 1000));
  return s < 5 ? "just now" : s < 60 ? `${s}s ago` : `${Math.round(s / 60)} min ago`;
}

function date(ts?: number): string {
  if (!ts) return "?";
  return new Date(ts * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** Problems worth flagging, in Nightgrid's spirit (warn 80 %, critical 90 %). */
function hot(s?: Status): boolean {
  if (!s || s.state !== "ok") return false;
  return (s.cpu ?? 0) >= 90 || (s.mem ?? 0) >= 90 || (s.disk ?? 0) >= 90 || (s.temp ?? 0) >= 85;
}

function Metric({ k, v, unit = "%", warn = 80, bad = 90 }: { k: string; v?: number | null; unit?: string; warn?: number; bad?: number }) {
  if (v == null) return null;
  return (
    <span style={{ marginRight: "8px", whiteSpace: "nowrap" }}>
      <span style={{ color: C.dim }}>{k} </span>
      <span style={{ ...mono, color: tone(v, warn, bad) }}>{Math.round(v)}{unit}</span>
    </span>
  );
}

function Dot({ color }: { color: string }) {
  return <span style={{ display: "inline-block", width: "8px", height: "8px", background: color, marginRight: "8px", boxShadow: `0 0 6px ${color}`, flexShrink: 0 }} />;
}

// ---------------------------------------------------------------- actions

function confirmPower(h: Host, action: "reboot" | "shutdown") {
  const verb = action === "reboot" ? "Reboot" : "Shut down";
  const body = action === "reboot"
    ? `${h.name} (${h.hostname}) restarts now. Everything running on it stops until it's back up.`
    : `${h.name} (${h.hostname}) powers off now.${h.mac ? " You can wake it from here again." : " It has no MAC address in the profile, so it can't be woken from here."}`;
  showModal(
    <ConfirmModal strTitle={`${verb} ${h.name}?`} strDescription={body} strOKButtonText={verb}
      strCancelButtonText="Cancel" bDestructiveWarning
      onOK={async () => {
        const r = await api.power(h.id, action);
        if (r.ok) toaster.toast({ title: "Nightgrid", body: `${verb} sent to ${h.name}` });
        else toaster.toast({ title: `${verb} failed`, body: r.error });
        await load();
      }} />,
  );
}

async function doWake(h: Host) {
  const r = await api.wake(h.id);
  if (r.ok) toaster.toast({ title: "Nightgrid", body: `Wake sent to ${h.name}${r.relay ? ` (also via ${r.relay})` : ""}` });
  else toaster.toast({ title: "Wake failed", body: r.error });
  await load();
}

// ---------------------------------------------------------------- import

function PassphraseModal({ file, closeModal }: { file: ProfileFile; closeModal?: () => void }) {
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const go = async () => {
    if (!pw || busy) return;
    setBusy(true); setErr(null);
    const r = await api.importProfile(file.path, pw);
    setBusy(false);
    if (!r.ok) { setErr(r.error); return; }
    toaster.toast({ title: "Nightgrid profile imported", body: `${r.hosts} hosts${r.passwords ? `, ${r.passwords} with saved passwords` : ""}` });
    closeModal?.();
    M.open = null;
    await load();
    refreshNow();
  };
  return (
    <ModalRoot closeModal={closeModal}>
      <div className={staticClasses.Title} style={{ marginBottom: "8px" }}>Unlock {file.name}</div>
      <div style={{ ...note, marginBottom: "12px" }}>
        The passphrase you chose when exporting from Nightgrid. Press A on the field for the keyboard. It's used once and never stored.
      </div>
      <TextField label="Passphrase" bIsPassword value={pw} disabled={busy}
        onChange={(e) => setPw(e.target.value)} />
      {err && <div style={{ ...note, color: C.danger, marginTop: "8px" }}>{err}</div>}
      <Focusable style={{ display: "flex", gap: "8px", marginTop: "16px" }} flow-children="horizontal">
        <DialogButton disabled={!pw || busy} onClick={go}>{busy ? "Decrypting…" : "Import"}</DialogButton>
        <DialogButton onClick={() => closeModal?.()}>Cancel</DialogButton>
      </Focusable>
    </ModalRoot>
  );
}

function PickerModal({ closeModal }: { closeModal?: () => void }) {
  const [files, setFiles] = useState<ProfileFile[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api.findProfiles().then((r) => (r.ok ? setFiles(r.files) : setErr(r.error)));
  }, []);
  const pick = (f: ProfileFile) => { closeModal?.(); showModal(<PassphraseModal file={f} />); };
  return (
    <ModalRoot closeModal={closeModal}>
      <div className={staticClasses.Title} style={{ marginBottom: "8px" }}>Import a Nightgrid profile</div>
      <div style={{ ...note, marginBottom: "12px" }}>
        In Nightgrid, use Export profile… (tick "Include saved passwords" if reboot and shutdown need sudo), then put the
        .age file in Downloads, Documents, a synced folder, or on an SD card or USB stick.
      </div>
      {err && <div style={{ ...note, color: C.danger }}>{err}</div>}
      {!files && !err && <div style={note}>Looking for profiles…</div>}
      {files && !files.length && <div style={{ ...note, color: C.warn }}>No profile files found yet.</div>}
      <Focusable style={{ display: "flex", flexDirection: "column", gap: "6px", maxHeight: "50vh", overflowY: "auto" }}>
        {files?.map((f) => (
          <DialogButton key={f.path} onClick={() => pick(f)} style={{ textAlign: "left", padding: "8px 12px" }}>
            <div>{f.name}</div>
            <div style={{ ...note, fontSize: "11px" }}>{f.path.replace(/\/[^/]*$/, "")} · {new Date(f.mtime * 1000).toLocaleString()}</div>
          </DialogButton>
        ))}
      </Focusable>
      <Focusable style={{ display: "flex", gap: "8px", marginTop: "16px" }} flow-children="horizontal">
        <DialogButton onClick={() => { setFiles(null); api.findProfiles().then((r) => (r.ok ? setFiles(r.files) : setErr(r.error))); }}>Look again</DialogButton>
        <DialogButton onClick={() => closeModal?.()}>Close</DialogButton>
      </Focusable>
    </ModalRoot>
  );
}

const openPicker = () => showModal(<PickerModal />);

// ---------------------------------------------------------------- host row

function Btn({ children, onClick, color }: { children: ReactNode; onClick: () => void; color?: string }) {
  return (
    <DialogButton onClick={onClick} style={{ minWidth: 0, flex: 1, padding: "6px 4px", fontSize: "12px", ...label, color: color ?? undefined }}>
      {children}
    </DialogButton>
  );
}

function HostRow({ h, s }: { h: Host; s?: Status }) {
  const open = M.open === h.id;
  const st = STATE[s?.state ?? ""] ?? { text: M.refreshing ? "Checking" : "Unknown", color: C.dim };
  const toggle = () => { M.open = open ? null : h.id; emit(); };
  const up = s?.state === "ok";
  const desc = up ? (
    <span style={{ fontSize: "12px" }}>
      <Metric k="CPU" v={s?.cpu} /><Metric k="MEM" v={s?.mem} /><Metric k="DSK" v={s?.disk} />
      <Metric k="" v={s?.temp} unit="°" warn={75} bad={85} />
    </span>
  ) : (
    <span style={{ fontSize: "12px", color: C.dim }}>{s?.error && !open ? s.error : h.group ?? h.hostname}</span>
  );
  return (
    <>
      <PanelSectionRow>
        <Field
          label={<span style={{ display: "flex", alignItems: "center" }}><Dot color={st.color} />{h.name}</span>}
          description={desc} focusable highlightOnFocus onActivate={toggle} onClick={toggle}
          bottomSeparator={open ? "none" : "standard"}
        >
          <span style={{ ...label, color: st.color }}>{st.text}</span>
        </Field>
      </PanelSectionRow>
      {open && (
        <PanelSectionRow>
          <div style={{ borderLeft: `2px solid ${C.active}`, paddingLeft: "10px", marginBottom: "10px" }}>
            <div style={{ ...note, marginBottom: "8px" }}>
              <span style={mono}>{h.username ? `${h.username}@` : ""}{h.hostname}{h.port !== 22 ? `:${h.port}` : ""}</span>
              {s?.via === "tailnet" && <span style={{ color: C.data }}> · via tailnet</span>}
              {up && uptime(s?.uptime) && <> · up {uptime(s?.uptime)}</>}
              {up && s?.load != null && <> · load {s.load.toFixed(2)}</>}
              {up && s?.mount && s.mount !== "/" && <> · fullest {s.mount}</>}
              {!up && s?.error && <div style={{ color: C.warn }}>{s.error}</div>}
              {s?.state === "auth" && <div>This device needs its own login: Profile → This device's key.</div>}
            </div>
            <Focusable style={{ display: "flex", gap: "6px" }} flow-children="horizontal">
              {h.mac && !up && <Btn onClick={() => doWake(h)} color={C.ok}>Wake</Btn>}
              {up && <Btn onClick={() => confirmPower(h, "reboot")} color={C.warn}>Reboot</Btn>}
              {up && <Btn onClick={() => confirmPower(h, "shutdown")} color={C.danger}>Shut down</Btn>}
              <Btn onClick={() => refreshNow([h.id])}>Check</Btn>
            </Focusable>
          </div>
        </PanelSectionRow>
      )}
    </>
  );
}

// ---------------------------------------------------------------- panel

function KeyArea() {
  const [k, setK] = useState<{ exists: boolean; fingerprint?: string; exported?: string | null } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.deviceKey(false).then((r) => r.ok && setK(r)); }, []);
  const withPw = M.hosts.filter((h) => h.hasPassword).length;
  const create = async () => {
    setBusy(true);
    const r = await api.deviceKey(true);
    setBusy(false);
    if (!r.ok) { toaster.toast({ title: "Key not created", body: r.error }); return; }
    setK(r);
  };
  const install = async () => {
    setBusy(true);
    const r = await api.installKey();
    setBusy(false);
    if (!r.ok) { toaster.toast({ title: "Key not added", body: r.error }); return; }
    toaster.toast({ title: "Device key", body: `Added on ${r.done.length} host(s)${r.failed.length ? `, ${r.failed.length} failed: ${r.failed.map((f) => f.name).join(", ")}` : ""}` });
    refreshNow();
  };
  return (
    <>
      <PanelSectionRow>
        <Field label="This device's key" description={
          <span style={note}>
            {k?.exists
              ? <>Hosts let this device in with it. <span style={mono}>{k.fingerprint}</span>{k.exported ? <><br />Public key saved to {k.exported}: add it in Nightgrid under Settings → Connections → SSH keys.</> : null}</>
              : "For hosts that only accept your computer's key. A new key for this device; Nightgrid can then add it to every host."}
          </span>} />
      </PanelSectionRow>
      {!k?.exists && (
        <PanelSectionRow>
          <DialogButton disabled={busy} onClick={create}>{busy ? "Creating…" : "Create key for this device"}</DialogButton>
        </PanelSectionRow>
      )}
      {k?.exists && withPw > 0 && (
        <PanelSectionRow>
          <DialogButton disabled={busy} onClick={install}>{busy ? "Adding…" : `Add it to ${withPw} host(s) with saved passwords`}</DialogButton>
        </PanelSectionRow>
      )}
    </>
  );
}

function Content() {
  const m = useModel();
  const visible = useQuickAccessVisible();
  const [, tick] = useState(0);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => { load(); }, []);

  // Refresh only while the panel is on screen; nothing runs once Quick Access closes.
  useEffect(() => {
    if (!visible || !m.loaded || !m.hosts.length) return;
    let stop = false;
    const loop = async () => {
      if (stop) return;
      if (Date.now() - M.lastRefresh > 3000) await refreshNow();
      if (!stop) timer.current = window.setTimeout(loop, M.prefs.interval * 1000);
    };
    loop();
    const clock = window.setInterval(() => tick((n) => n + 1), 5000);
    return () => { stop = true; window.clearTimeout(timer.current); window.clearInterval(clock); };
  }, [visible, m.loaded, m.hosts.length, m.prefs.interval, m.profile.file]);

  const shown = m.hosts.filter((h) => m.prefs.showClients || h.role !== "client");
  const statuses = shown.map((h) => m.status[h.id]);
  const online = statuses.filter((s) => s && ONLINE.has(s.state)).length;
  const attention = shown.filter((h) => {
    const s = m.status[h.id];
    return hot(s) || (s && ["offline", "auth", "hostkey", "error"].includes(s.state));
  }).length;
  const groups = Array.from(new Set(shown.map((h) => h.group ?? "")));
  const grouped = groups.length > 1;

  const srcSummary = m.profile.source === "file" ? `Profile file · ${m.hosts.length} hosts`
    : m.profile.source === "local" ? `Nightgrid on this device · ${m.hosts.length} hosts` : "Not set up";

  if (!m.loaded) {
    return <Section id="status" title="Nightgrid" collapsible={false}><PanelSectionRow><div style={note}>{m.error ?? "Loading…"}</div></PanelSectionRow></Section>;
  }

  return (
    <>
      <Section id="status" title="Fleet" collapsible={false}>
        {m.profile.source ? (
          <PanelSectionRow>
            <Field
              label={<span style={{ ...mono, color: C.data, fontSize: "18px" }}>{online}<span style={{ color: C.dim }}> / {shown.length}</span> <span style={{ ...label, color: C.dim }}>online</span></span>}
              description={<span style={{ fontSize: "12px" }}>
                {attention ? <span style={{ color: C.warn }}>{attention} need{attention === 1 ? "s" : ""} attention · </span> : null}
                {m.refreshing ? "Checking…" : m.lastRefresh ? `Updated ${ago(m.lastRefresh)}` : "Not checked yet"}
              </span>}
              focusable highlightOnFocus onActivate={() => refreshNow()} onClick={() => refreshNow()}
            >
              <span style={{ ...label, color: C.dim }}>Refresh</span>
            </Field>
          </PanelSectionRow>
        ) : (
          <>
            <PanelSectionRow>
              <div style={note}>
                Shows your Nightgrid hosts with Wake, Reboot and Shut down. It uses your existing Nightgrid profile as it is.
                Import the profile you exported from Nightgrid, or install Nightgrid on this device and its hosts appear here by themselves.
              </div>
            </PanelSectionRow>
            <PanelSectionRow>
              <DialogButton onClick={openPicker}>Import Nightgrid profile…</DialogButton>
            </PanelSectionRow>
          </>
        )}
        {m.error && <PanelSectionRow><div style={{ ...note, color: C.danger }}>{m.error}</div></PanelSectionRow>}
      </Section>

      {m.profile.source && (
        <Section id="hosts" title="Hosts" collapsible={false}>
          {!shown.length && <PanelSectionRow><div style={note}>No hosts in this profile{m.hosts.length ? " (client devices are hidden in Settings)" : ""}.</div></PanelSectionRow>}
          {groups.map((g) => (
            <div key={g || "-"}>
              {grouped && <PanelSectionRow><div style={{ ...label, color: C.dim, borderBottom: `1px solid ${C.line}`, padding: "6px 0 2px" }}>{g || "Ungrouped"}</div></PanelSectionRow>}
              {shown.filter((h) => (h.group ?? "") === g).map((h) => <HostRow key={h.id} h={h} s={m.status[h.id]} />)}
            </div>
          ))}
        </Section>
      )}

      <Section id="profile" title="Profile" summary={srcSummary}>
        <PanelSectionRow>
          <Field label={m.profile.source === "file" ? "Imported profile" : m.profile.source === "local" ? "Nightgrid on this device" : "No profile"}
            description={<span style={note}>
              {m.profile.source === "file" && <>{m.profile.file?.split("/").pop()} · exported {date(m.profile.createdAt)}{m.profile.appVersion ? ` from Nightgrid ${m.profile.appVersion}` : ""} · {m.profile.passwords ? `${m.profile.passwords} host(s) with saved passwords` : "no saved passwords"}</>}
              {m.profile.source === "local" && <>Read straight from Nightgrid's database. Hosts you add there show up here. Saved passwords stay in Nightgrid's keychain, so reboot and shut down need sudo without a password on those hosts.</>}
              {!m.profile.source && <>Import a profile exported from Nightgrid.</>}
            </span>} />
        </PanelSectionRow>
        <PanelSectionRow>
          <DialogButton onClick={openPicker}>{m.profile.source === "file" ? "Import a newer profile…" : "Import Nightgrid profile…"}</DialogButton>
        </PanelSectionRow>
        {m.profile.source === "file" && (
          <PanelSectionRow>
            <DialogButton onClick={() => showModal(
              <ConfirmModal strTitle="Forget the imported profile?" strOKButtonText="Forget" strCancelButtonText="Cancel"
                strDescription={m.localAvailable ? "The hosts and saved passwords from the file are removed from this device. Nightgrid on this device is used instead." : "The hosts and saved passwords from the file are removed from this device."}
                onOK={async () => { await api.forgetProfile(); M.status = {}; await load(); }} />)}>
              Forget imported profile
            </DialogButton>
          </PanelSectionRow>
        )}
        {m.profile.source && <KeyArea />}
      </Section>

      <Section id="settings" title="Settings" summary={`Every ${m.prefs.interval} s while open${m.prefs.showClients ? " · clients shown" : ""}`}>
        <PanelSectionRow>
          <DropdownItem label="Refresh while open" selectedOption={m.prefs.interval}
            rgOptions={[10, 15, 30, 60].map((s) => ({ data: s, label: `Every ${s} s` }))}
            onChange={async (o) => { const r = await api.setPrefs({ interval: o.data }); if (r.ok) { M.prefs = r.prefs; emit(); } }} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField label="Show client devices" description="Laptops and handhelds marked as clients in Nightgrid."
            checked={m.prefs.showClients}
            onChange={async (v) => { const r = await api.setPrefs({ showClients: v }); if (r.ok) { M.prefs = r.prefs; emit(); } }} />
        </PanelSectionRow>
      </Section>

      <Section id="about" title="About">
        <PanelSectionRow>
          <div style={note}>
            Nightgrid Control talks to your hosts the way Nightgrid does: over SSH, nothing installed on them. Hosts are only
            contacted while this panel is open, one shared connection each. Reboot and shut down use sudo (the saved password
            from the profile, or none if the host allows that) and always ask first. Wake uses the MAC address and wake relay
            from Nightgrid.
          </div>
        </PanelSectionRow>
      </Section>
    </>
  );
}

export default definePlugin(() => ({
  name: "Nightgrid Control",
  titleView: <div className={staticClasses.Title}>Nightgrid</div>,
  content: <Content />,
  icon: <FaServer />,
  onDismount() { listeners.clear(); },
}));
