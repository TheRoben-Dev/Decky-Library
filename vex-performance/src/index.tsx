import {
  ButtonItem,
  DropdownItem,
  Field,
  PanelSection,
  PanelSectionRow,
  SliderField,
  ToggleField,
  Navigation,
  staticClasses,
} from "@decky/ui";
import { definePlugin, toaster } from "@decky/api";
import { useEffect, useReducer, useState } from "react";
import { lsfgInstall } from "./backend";

declare const SteamClient: any;
import { FaTachometerAlt } from "react-icons/fa";
import { controller } from "./controller";
import { getLimits, steamPerfAvailable } from "./steam";
import { matchRefresh, PRESETS, RESOLUTIONS } from "./presets";
import { GpuMode, PowerBackend, Profile } from "./types";
import { sectionFactory } from "./section";

const note = { fontSize: "12px", lineHeight: "16px", opacity: 0.75, whiteSpace: "normal" as const };
const warn = { ...note, color: "#ffb84d", opacity: 1 };

function useController() {
  const [, force] = useReducer((x: number) => x + 1, 0);
  useEffect(() => {
    const unsub = controller.subscribe(force);
    return () => { unsub(); };
  }, []);
  return controller;
}

function Note({ children, warning }: { children: any; warning?: boolean }) {
  return (
    <PanelSectionRow>
      <div style={warning ? warn : note}>{children}</div>
    </PanelSectionRow>
  );
}

const LS_APPID = 993090;

function openLosslessStore() {
  try {
    SteamClient.URL.ExecuteSteamURL(`steam://store/${LS_APPID}`);
  } catch {
    Navigation.NavigateToExternalWeb(`https://store.steampowered.com/app/${LS_APPID}/`);
  }
  Navigation.CloseSideMenus();
}

function openLosslessLibrary() {
  Navigation.Navigate(`/library/app/${LS_APPID}`);
  Navigation.CloseSideMenus();
}

/** Lossless Scaling + lsfg-vk layer status, with one-tap fixes. */
function FrameGenStatus() {
  const c = useController();
  const [busy, setBusy] = useState(false);
  const l = c.env?.lsfg;
  if (!l) return null;
  const ls = l.lossless;
  const install = async () => {
    setBusy(true);
    const r = await lsfgInstall(true).catch((e) => ({ ok: false, error: String(e) }));
    setBusy(false);
    toaster.toast({ title: "Vex: frame gen", body: r.ok ? `lsfg-vk ${l.bundledVersion} installed` : `Install failed: ${r.error}` });
    c.refreshEnv();
  };
  return (
    <>
      {!ls.installed ? (
        <>
          <Note warning>Frame gen needs Lossless Scaling (paid Steam app). Its frame-gen engine can't be bundled, so buy/install it once on Steam.</Note>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={openLosslessStore}>Get Lossless Scaling on Steam</ButtonItem>
          </PanelSectionRow>
        </>
      ) : !ls.dll ? (
        <>
          <Note warning>
            Lossless Scaling is installed{ls.branch ? ` (branch: ${ls.branch})` : ""}, but lsfg-vk.dll isn't there yet. Open it, then Properties → Game Versions & Betas → pick "lsfg-vk" and let it update.
          </Note>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={openLosslessLibrary}>Open Lossless Scaling</ButtonItem>
          </PanelSectionRow>
        </>
      ) : (
        <Note>Lossless Scaling found ✓</Note>
      )}
      {l.legacyV1 && <Note warning>An old lsfg-vk 1.x layer is installed. Vex installs 2.x alongside; remove the old one if games misbehave.</Note>}
      {l.installed ? (
        <Note>
          {l.ownedByVex ? `Using Vex's bundled lsfg-vk ${l.bundledVersion}.` : l.otherPlugin ? `Using lsfg-vk installed by ${l.otherPlugin}. Vex shares its config and won't touch its files.` : "Using the lsfg-vk already installed on this system."}
        </Note>
      ) : l.bundled ? (
        <>
          <Note>lsfg-vk {l.bundledVersion} is bundled. It installs automatically the first time you enable frame gen.</Note>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy} onClick={install}>{busy ? "Installing…" : "Install lsfg-vk now"}</ButtonItem>
          </PanelSectionRow>
        </>
      ) : (
        <Note warning>This build has no bundled lsfg-vk. Use the release zip, or install lsfg-vk another way.</Note>
      )}
    </>
  );
}

const Section = sectionFactory("vex-performance");

const BACKEND_LABEL: Record<string, string> = {
  steam: "Steam's TDP slider", powerstation: "PowerStation", hhd: "Handheld Daemon (legacy)",
  sysfs: "Direct (asus-armoury)", off: "Off",
};

function Content() {
  const c = useController();
  useEffect(() => { c.refreshEnv(); }, []);
  const app = c.app;
  const key = c.profileKeyFor(app?.appid);
  const p = c.activeProfile();
  const isGame = key !== "default";
  const limits = getLimits();
  const env = c.env;
  const backend = c.resolvedBackend();
  const edit = (m: (p: Profile) => void) => c.editActive(m);
  const tdpMin = limits.tdpMax > 0 ? limits.tdpMin : env?.power.tdpMin ?? 5;
  const tdpMax = limits.tdpMax > 0 ? limits.tdpMax : env?.power.tdpMax ?? 30;
  const gpuRange = env?.powerstation.gpuRange ?? env?.power.gpuRange ?? [800, 2700];
  const autoHz = matchRefresh(p.frame.fps, limits.refreshMin, limits.refreshMax);
  const tdpPlugins = env?.conflicts.plugins.filter((x) => /TDP/.test(x.controls)) ?? [];

  const powerSummary = backend === "off" ? "Off"
    : [p.power.tdpEnabled ? `${p.power.tdp} W` : "TDP not set",
       p.power.gpuMode === "auto" ? "GPU auto" : `GPU ${p.power.gpuMode === "range" ? `${p.power.gpuMin}–` : p.power.gpuMode === "max" ? "≤" : ""}${p.power.gpuMax} MHz`].join(" · ");
  const frameSummary = !p.frame.enabled ? "Not managed"
    : `${p.frame.fps || "No"} fps cap${limits.refreshAvailable ? ` @ ${p.frame.refresh > 0 ? p.frame.refresh : autoHz} Hz` : ""}`;
  const scaleSummary = !p.scaling.enabled ? "Not managed"
    : `${p.scaling.fsr ? `FSR, sharpness ${p.scaling.sharpness}` : "Linear"}${p.scaling.resolution ? ` · ${p.scaling.resolution}` : ""}`;
  const fgSummary = !isGame ? "Per game only" : p.fg.enabled ? `${p.fg.multiplier}x, flow ${Math.round(p.fg.flowScale * 100)}%` : "Off";

  return (
    <>
      {/* 1. Status: which game, which profile, what got applied */}
      <PanelSection title={app ? app.name : "No game running"}>
        <Note>
          {app
            ? isGame ? "Using and editing this game's own profile." : "Using the Default profile."
            : "Editing the Default profile. Launch a game to give it its own profile."}
        </Note>
        {c.lastApplied && <Note>Applied: {c.lastApplied}</Note>}
        {!steamPerfAvailable() && <Note warning>Steam's performance API wasn't found. FSR, frame cap and refresh can't be set on this Steam build.</Note>}
        {app && !isGame && (
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => c.createGameProfile()}>Create profile for this game</ButtonItem>
          </PanelSectionRow>
        )}
        {app && (
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => c.applyCurrent(true)}>Apply now</ButtonItem>
          </PanelSectionRow>
        )}
      </PanelSection>

      {/* 2. Main controls, most-used first */}
      <Section id="power" title="Power (TDP / GPU)" summary={powerSummary} defaultOpen>
        <Note>
          TDP via <b>{BACKEND_LABEL[backend]}</b>
          {backend !== "off" && <> · GPU via <b>{env?.powerstation.running ? "PowerStation" : backend === "hhd" ? "Handheld Daemon" : "amdgpu sysfs"}</b></>}
        </Note>
        {tdpPlugins.length > 0 && (
          <Note warning>{tdpPlugins.map((x) => x.name).join(", ")} also controls TDP. Auto mode stays off to avoid fighting it. Pick a path in Settings to override.</Note>
        )}
        {env?.hhd.running && c.settings.powerBackend === "auto" && backend === "off" && (
          <Note warning>Handheld Daemon (retired in Bazzite 44) is still running, so auto mode leaves TDP alone. Update Bazzite, or pick "Handheld Daemon (legacy)" in Settings.</Note>
        )}
        {c.settings.powerBackend === "auto" && backend !== "steam" && env?.powerstation.running && (
          <Note>Steam's TDP slider isn't showing, so Vex talks to PowerStation directly. Turn on the TDP slider in Steam's Performance settings if you'd rather Steam own it.</Note>
        )}
        {backend !== "off" && (
          <>
            <PanelSectionRow>
              <ToggleField label="Set TDP" checked={p.power.tdpEnabled}
                onChange={(v) => edit((x) => { x.power.tdpEnabled = v; })} />
            </PanelSectionRow>
            {p.power.tdpEnabled && (
              <PanelSectionRow>
                <SliderField label="TDP" value={p.power.tdp} min={tdpMin} max={tdpMax} step={1} showValue valueSuffix=" W"
                  onChange={(v) => edit((x) => { x.power.tdp = v; })} />
              </PanelSectionRow>
            )}
            <PanelSectionRow>
              <DropdownItem label="GPU clock"
                rgOptions={[{ data: "auto", label: "Auto" }, { data: "max", label: "Max limit" }, { data: "fixed", label: "Fixed" }, { data: "range", label: "Range" }]}
                selectedOption={p.power.gpuMode}
                onChange={(o) => edit((x) => { x.power.gpuMode = o.data as GpuMode; })} />
            </PanelSectionRow>
            {p.power.gpuMode === "range" && (
              <PanelSectionRow>
                <SliderField label="GPU min" value={p.power.gpuMin} min={gpuRange[0]} max={gpuRange[1]} step={100} showValue valueSuffix=" MHz"
                  onChange={(v) => edit((x) => { x.power.gpuMin = Math.min(v, x.power.gpuMax); })} />
              </PanelSectionRow>
            )}
            {p.power.gpuMode !== "auto" && (
              <PanelSectionRow>
                <SliderField label={p.power.gpuMode === "fixed" ? "GPU clock" : "GPU max"} value={p.power.gpuMax} min={gpuRange[0]} max={gpuRange[1]} step={100} showValue valueSuffix=" MHz"
                  onChange={(v) => edit((x) => { x.power.gpuMax = Math.max(v, x.power.gpuMode === "range" ? x.power.gpuMin : 0); })} />
              </PanelSectionRow>
            )}
          </>
        )}
      </Section>

      <Section id="frame" title="Frame cap + refresh" summary={frameSummary} defaultOpen>
        <PanelSectionRow>
          <ToggleField label="Manage frame cap" checked={p.frame.enabled}
            onChange={(v) => edit((x) => { x.frame.enabled = v; })} />
        </PanelSectionRow>
        {p.frame.enabled && (
          <>
            <PanelSectionRow>
              <SliderField label="Frame cap" value={p.frame.fps} min={0} max={limits.refreshMax} step={5} showValue
                valueSuffix={p.frame.fps === 0 ? " (off)" : " fps"}
                onChange={(v) => edit((x) => { x.frame.fps = v; })} />
            </PanelSectionRow>
            {limits.refreshAvailable ? (
              <>
                <PanelSectionRow>
                  <ToggleField label="Match refresh to cap" description={`Uses ${autoHz} Hz`} checked={p.frame.refresh === 0}
                    onChange={(v) => edit((x) => { x.frame.refresh = v ? 0 : autoHz; })} />
                </PanelSectionRow>
                {p.frame.refresh !== 0 && (
                  <PanelSectionRow>
                    <SliderField label="Refresh rate" value={p.frame.refresh} min={limits.refreshMin} max={limits.refreshMax} step={1} showValue valueSuffix=" Hz"
                      onChange={(v) => edit((x) => { x.frame.refresh = v; })} />
                  </PanelSectionRow>
                )}
              </>
            ) : (
              <Note>Steam reports no manual refresh control on this display, so only the frame cap is set.</Note>
            )}
          </>
        )}
      </Section>

      {/* 3. Secondary groups */}
      <Section id="scaling" title="Upscaling (gamescope FSR)" summary={scaleSummary}>
        <PanelSectionRow>
          <ToggleField label="Manage scaling" checked={p.scaling.enabled}
            onChange={(v) => edit((x) => { x.scaling.enabled = v; })} />
        </PanelSectionRow>
        {p.scaling.enabled && (
          <>
            <PanelSectionRow>
              <ToggleField label="FSR upscaling" description="Off = plain linear scaling" checked={p.scaling.fsr}
                onChange={(v) => edit((x) => { x.scaling.fsr = v; })} />
            </PanelSectionRow>
            {p.scaling.fsr && (
              <PanelSectionRow>
                <SliderField label="Sharpness" description="Same scale as Steam's FSR sharpness slider" value={p.scaling.sharpness}
                  min={limits.fsrMin} max={limits.fsrMax} step={1} showValue
                  onChange={(v) => edit((x) => { x.scaling.sharpness = v; })} />
              </PanelSectionRow>
            )}
            <PanelSectionRow>
              <DropdownItem label="Render resolution" description="Applies on next game launch"
                rgOptions={RESOLUTIONS.map((r) => ({ data: r.value, label: r.label }))}
                selectedOption={p.scaling.resolution}
                onChange={(o) => edit((x) => { x.scaling.resolution = o.data; })} />
            </PanelSectionRow>
            <Note>FSR only kicks in when the game renders below 1080p. If a game ignores the override, pick a lower resolution in its own settings menu.</Note>
          </>
        )}
      
      </Section>

      <Section id="framegen" title="Frame generation (lsfg-vk)" summary={fgSummary}>
        {!isGame ? (
          <Note>Frame gen is set per game. Create a game profile at the top to enable it.</Note>
        ) : (
          <>
            <PanelSectionRow>
              <ToggleField label="Enable frame gen" description="Applies on next game launch" checked={p.fg.enabled}
                onChange={(v) => edit((x) => { x.fg.enabled = v; })} />
            </PanelSectionRow>
            {p.fg.enabled && (
              <>
                {p.frame.enabled && p.frame.fps > 0 && p.frame.fps < 40 && (
                  <Note warning>Base frame cap is under 40 fps. Expect noticeable latency and artifacts.</Note>
                )}
                <PanelSectionRow>
                  <SliderField label="Multiplier" value={p.fg.multiplier} min={2} max={4} step={1} showValue valueSuffix="x"
                    onChange={(v) => edit((x) => { x.fg.multiplier = v; })} />
                </PanelSectionRow>
                <PanelSectionRow>
                  <SliderField label="Flow scale" value={Math.round(p.fg.flowScale * 100)} min={25} max={100} step={5} showValue valueSuffix="%"
                    onChange={(v) => edit((x) => { x.fg.flowScale = v / 100; })} />
                </PanelSectionRow>
                <PanelSectionRow>
                  <ToggleField label="Performance mode" description="Lighter model, recommended on the 780M" checked={p.fg.perfMode}
                    onChange={(v) => edit((x) => { x.fg.perfMode = v; })} />
                </PanelSectionRow>
                <PanelSectionRow>
                  <ToggleField label="Gamescope WSI fix" description="Vex adds ENABLE_GAMESCOPE_WSI=0 to the launch options and removes it when you turn frame gen off" checked={p.fg.wsiWorkaround}
                    onChange={(v) => edit((x) => { x.fg.wsiWorkaround = v; })} />
                </PanelSectionRow>
              </>
            )}
          </>
        )}
        <FrameGenStatus />
      </Section>

      <Section id="presets" title="Quick presets" summary="One tap sets FSR, frame cap and power together">
        {PRESETS.map((pr) => (
          <PanelSectionRow key={pr.label}>
            <ButtonItem layout="below" onClick={() => edit(pr.apply)}>{pr.label}</ButtonItem>
          </PanelSectionRow>
        ))}
      </Section>

      {/* 4. Plugin behaviour */}
      <Section id="settings" title="Settings" summary={`${c.settings.autoApply ? "Auto-apply on" : "Auto-apply off"} · ${Object.keys(c.settings.profiles).length - 1} game profiles`}>
        <PanelSectionRow>
          <ToggleField label="Auto-apply on game launch" checked={c.settings.autoApply}
            onChange={(v) => c.updateSettings({ autoApply: v })} />
        </PanelSectionRow>
        <PanelSectionRow>
          <DropdownItem label="Power control path"
            rgOptions={[
              { data: "auto", label: "Auto (recommended)" },
              { data: "steam", label: "Steam TDP slider" },
              { data: "powerstation", label: "PowerStation" },
              { data: "sysfs", label: "Direct sysfs" },
              { data: "hhd", label: "Handheld Daemon (legacy)" },
              { data: "off", label: "Off" },
            ]}
            selectedOption={c.settings.powerBackend}
            onChange={(o) => c.updateSettings({ powerBackend: o.data as PowerBackend })} />
        </PanelSectionRow>
        {app && isGame && (
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => c.deleteGameProfile()}>Remove this game's profile (use Default)</ButtonItem>
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <Field label="Game profiles saved" bottomSeparator="none">{Object.keys(c.settings.profiles).length - 1}</Field>
        </PanelSectionRow>
      </Section>
    </>
  );
}

export default definePlugin(() => {
  controller.start();
  return {
    name: "Vex Performance",
    titleView: <div className={staticClasses.Title}>Vex Performance</div>,
    content: <Content />,
    icon: <FaTachometerAlt />,
    onDismount() {
      controller.stop();
    },
  };
});
