import {
  ButtonItem,
  DropdownItem,
  Field,
  PanelSection,
  PanelSectionRow,
  SliderField,
  ToggleField,
  staticClasses,
} from "@decky/ui";
import { definePlugin } from "@decky/api";
import { useEffect, useReducer } from "react";
import { FaTachometerAlt } from "react-icons/fa";
import { controller } from "./controller";
import { getLimits, steamPerfAvailable } from "./steam";
import { matchRefresh, PRESETS, RESOLUTIONS } from "./presets";
import { GpuMode, PowerBackend, Profile } from "./types";

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
  const gpuRange = env?.power.gpuRange ?? [800, 2700];
  const autoHz = matchRefresh(p.frame.fps, limits.refreshMin, limits.refreshMax);
  const tdpPlugins = env?.conflicts.plugins.filter((x) => /TDP/.test(x.controls)) ?? [];

  return (
    <>
      <PanelSection title={app ? app.name : "No game running"}>
        <Note>
          {app
            ? isGame ? "Editing this game's own profile." : "This game uses the Default profile."
            : "Editing the Default profile. Launch a game to give it its own profile."}
        </Note>
        {app && !isGame && (
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => c.createGameProfile()}>Create profile for this game</ButtonItem>
          </PanelSectionRow>
        )}
        {app && isGame && (
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => c.deleteGameProfile()}>Remove game profile (use Default)</ButtonItem>
          </PanelSectionRow>
        )}
        {c.lastApplied && <Note>Applied: {c.lastApplied}</Note>}
        {!steamPerfAvailable() && <Note warning>Steam's performance API wasn't found. FSR, frame cap and refresh can't be set on this Steam build.</Note>}
      </PanelSection>

      <PanelSection title="Presets">
        {PRESETS.map((pr) => (
          <PanelSectionRow key={pr.label}>
            <ButtonItem layout="below" onClick={() => edit(pr.apply)}>{pr.label}</ButtonItem>
          </PanelSectionRow>
        ))}
      </PanelSection>

      <PanelSection title="Upscaling (gamescope FSR)">
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
      </PanelSection>

      <PanelSection title="Frame cap + refresh">
        <PanelSectionRow>
          <ToggleField label="Manage frame cap" checked={p.frame.enabled}
            onChange={(v) => edit((x) => { x.frame.enabled = v; })} />
        </PanelSectionRow>
        {p.frame.enabled && (
          <>
            <PanelSectionRow>
              <SliderField label="Frame cap" value={p.frame.fps} min={0} max={limits.refreshMax} step={5} showValue
                valueSuffix={p.frame.fps ? " fps" : " (off)"}
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
      </PanelSection>

      <PanelSection title="Power (TDP / GPU)">
        <Note>
          Path: <b>{backend === "steam" ? "Steam TDP slider (Handheld Daemon follows it)" : backend === "hhd" ? "Handheld Daemon API" : backend === "sysfs" ? "Direct (asus-armoury)" : "Off"}</b>
        </Note>
        {tdpPlugins.length > 0 && (
          <Note warning>{tdpPlugins.map((x) => x.name).join(", ")} also controls TDP. Auto mode stays off to avoid fighting it. Pick a path below to override.</Note>
        )}
        {env?.hhd.running && !env.hhd.tdpEnabled && backend !== "steam" && (
          <Note warning>Handheld Daemon is running with its TDP controls off. Turn on "TDP Controls" in HHD to let Vex set TDP.</Note>
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
      </PanelSection>

      <PanelSection title="Frame generation (lsfg-vk)">
        {!env?.lsfg.installed ? (
          <Note warning>
            {env?.lsfg.legacyV1 ? "Old lsfg-vk 1.x found. Update to lsfg-vk 2.x (e.g. with the Decky LSFG-VK plugin)." : "lsfg-vk 2.x isn't installed. Install it (e.g. with the Decky LSFG-VK plugin) and own Lossless Scaling on Steam, lsfg-vk branch."}
          </Note>
        ) : !isGame ? (
          <Note>Frame gen is set per game. Create a game profile above to enable it.</Note>
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
                {!env.lsfg.dll && !env.lsfg.dllFound && (
                  <Note warning>Lossless.dll not found. Install Lossless Scaling on Steam and switch it to the lsfg-vk beta branch.</Note>
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
      </PanelSection>

      <PanelSection title="Settings">
        <PanelSectionRow>
          <ToggleField label="Auto-apply on game launch" checked={c.settings.autoApply}
            onChange={(v) => c.updateSettings({ autoApply: v })} />
        </PanelSectionRow>
        <PanelSectionRow>
          <DropdownItem label="Power control path"
            rgOptions={[
              { data: "auto", label: "Auto (recommended)" },
              { data: "steam", label: "Steam slider (HHD)" },
              { data: "hhd", label: "Handheld Daemon API" },
              { data: "sysfs", label: "Direct sysfs" },
              { data: "off", label: "Off" },
            ]}
            selectedOption={c.settings.powerBackend}
            onChange={(o) => c.updateSettings({ powerBackend: o.data as PowerBackend })} />
        </PanelSectionRow>
        {app && (
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => c.applyCurrent(true)}>Apply now</ButtonItem>
          </PanelSectionRow>
        )}
        <Field label="Profiles saved" bottomSeparator="none">{Object.keys(c.settings.profiles).length - 1} games</Field>
      </PanelSection>
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
