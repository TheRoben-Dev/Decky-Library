import {
  DropdownItem,
  Field,
  PanelSection,
  PanelSectionRow,
  SliderField,
  ToggleField,
  staticClasses,
} from "@decky/ui";
import { definePlugin, toaster } from "@decky/api";
import { useEffect, useReducer } from "react";
import { FaGamepad } from "react-icons/fa";
import * as be from "./backend";
import { controller } from "./controller";
import { Light, LightMode, Reactive, Speed } from "./types";

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

const hsl = (h: number, s: number) => `hsl(${h}, ${s}%, ${50 + (100 - s) / 2}%)`;

function Swatch({ h, s }: { h: number; s: number }) {
  return <div style={{ width: 22, height: 22, borderRadius: 11, background: hsl(h, s), border: "2px solid #ffffff55" }} />;
}

const MODES: { data: LightMode; label: string }[] = [
  { data: "solid", label: "Solid" },
  { data: "pulse", label: "Pulse" },
  { data: "duality", label: "Two colors" },
  { data: "rainbow", label: "Rainbow" },
  { data: "spiral", label: "Spiral" },
  { data: "off", label: "Off" },
];
const SPEEDS: { data: Speed; label: string }[] = [
  { data: "low", label: "Slow" },
  { data: "medium", label: "Medium" },
  { data: "high", label: "Fast" },
];
const REACTIVE: { data: Reactive; label: string }[] = [
  { data: "none", label: "Fixed color" },
  { data: "battery", label: "Battery level (red → green)" },
  { data: "temperature", label: "APU temperature (cyan → red)" },
  { data: "tdp", label: "TDP mode (HHD colors)" },
];
const QUICK = [
  { label: "ROG red", hue: 0, saturation: 100 },
  { label: "Cyan", hue: 190, saturation: 100 },
  { label: "Purple", hue: 280, saturation: 100 },
  { label: "White", hue: 0, saturation: 0 },
];
const PADDLES: Record<string, string> = {
  steam_input: "Steam Input (bind per game in Steam)",
  noob: "Keyboard / HHD overlay",
  touchpad: "Touchpad clicks",
  disabled: "Disabled",
};
const LIMITS = [70, 80, 85, 90, 95, 100];

function LightEditor({ light }: { light: Light }) {
  const c = controller;
  const follow = !!c.settings?.rgb.followScreen;
  const colored = ["solid", "pulse", "duality"].includes(light.mode);
  return (
    <>
      <PanelSectionRow>
        <DropdownItem
          label="Effect"
          rgOptions={MODES}
          selectedOption={light.mode}
          onChange={(o) => c.editLight((l) => { l.mode = o.data; })}
        />
      </PanelSectionRow>
      {colored && (
        <>
          <PanelSectionRow>
            <Field label="Color" bottomSeparator="none">
              <div style={{ display: "flex", gap: 10 }}>
                {QUICK.map((q) => (
                  <div key={q.label} onClick={() => c.editLight((l) => { l.hue = q.hue; l.saturation = q.saturation; })}>
                    <Swatch h={q.hue} s={q.saturation} />
                  </div>
                ))}
                <span style={{ marginLeft: 8 }}><Swatch h={light.hue} s={light.saturation} /></span>
              </div>
            </Field>
          </PanelSectionRow>
          <PanelSectionRow>
            <SliderField label="Hue" value={light.hue} min={0} max={360} step={5} showValue
              onChange={(v) => c.editLight((l) => { l.hue = v; })} />
          </PanelSectionRow>
          <PanelSectionRow>
            <SliderField label="Saturation" value={light.saturation} min={0} max={100} step={10} showValue
              onChange={(v) => c.editLight((l) => { l.saturation = v; })} />
          </PanelSectionRow>
          {light.mode === "duality" && (
            <PanelSectionRow>
              <SliderField label="Second hue" value={light.hue2} min={0} max={360} step={5} showValue
                onChange={(v) => c.editLight((l) => { l.hue2 = v; })} />
            </PanelSectionRow>
          )}
        </>
      )}
      {light.mode !== "off" && (
        <PanelSectionRow>
          <SliderField
            label={follow ? "Max brightness" : "Brightness"}
            value={light.brightness}
            min={10}
            max={100}
            step={10}
            showValue
            description={[
              follow ? "Rings run at this level when the screen is at 100%." : "",
              colored ? "" : "Rainbow and spiral only have three hardware levels: low, medium, high.",
            ].filter(Boolean).join(" ") || undefined}
            onChange={(v) => c.editLight((l) => { l.brightness = v; })}
          />
        </PanelSectionRow>
      )}
      {["pulse", "duality", "spiral"].includes(light.mode) && (
        <PanelSectionRow>
          <DropdownItem label="Speed" rgOptions={SPEEDS} selectedOption={light.speed}
            onChange={(o) => c.editLight((l) => { l.speed = o.data; })} />
        </PanelSectionRow>
      )}
      {light.mode === "spiral" && (
        <PanelSectionRow>
          <DropdownItem label="Direction"
            rgOptions={[{ data: "left", label: "Counter-clockwise" }, { data: "right", label: "Clockwise" }]}
            selectedOption={light.direction}
            onChange={(o) => c.editLight((l) => { l.direction = o.data; })} />
        </PanelSectionRow>
      )}
    </>
  );
}

function Lighting() {
  const c = useController();
  const st = c.state!;
  const s = st.settings.rgb;
  const gameLight = c.gameLight();
  const light = gameLight ?? s.base;
  const r = st.rgb;
  return (
    <PanelSection title="Ring lighting">
      {!st.hhd.running && <Note warning>Handheld Daemon isn't running, so lighting and buttons can't be changed. Bazzite starts it by default.</Note>}
      {r?.controllerOwnsLeds && <Note warning>HHD's Dualsense "LED Support" is on, so games control the rings. Turn it off in HHD to use these settings.</Note>}
      {r && !r.hhdRgbEnabled && <Note>RGB support is off in HHD. Changing a setting here turns it on.</Note>}
      <PanelSectionRow>
        <ToggleField label="Manage ring lighting" checked={s.managed}
          description="Saved in Handheld Daemon, so it stays on when this plugin or Decky isn't loaded."
          onChange={(v) => c.setRgb({ managed: v })} />
      </PanelSectionRow>
      {s.managed && (
        <>
          {st.lightReason && <Note>Now showing: {st.lightReason}</Note>}
          {c.appid && (
            <PanelSectionRow>
              <ToggleField label={`Own lighting for ${st.game?.name ?? "this game"}`} checked={!!gameLight}
                onChange={(v) => c.toggleGameLight(v)} />
            </PanelSectionRow>
          )}
          <Note>{gameLight ? "Editing this game's lighting." : "Editing the default lighting."}</Note>
          <LightEditor light={light} />
          {!gameLight && (
            <PanelSectionRow>
              <DropdownItem label="Color follows" rgOptions={REACTIVE} selectedOption={s.reactive}
                description="Changes the hue of Solid/Pulse automatically. Needs the plugin running."
                onChange={(o) => c.setRgb({ reactive: o.data })} />
            </PanelSectionRow>
          )}
          <PanelSectionRow>
            <ToggleField label="Follow screen brightness" checked={s.followScreen}
              description={`Scales the rings with the screen's real backlight level in 1% steps, and turns them off when the screen turns off.${s.followScreen && st.screen != null ? ` Screen now: ${Math.round(st.screen * 100)}%.` : ""}`}
              onChange={(v) => c.setRgb(v ? { followScreen: v, base: { ...s.base, brightness: 100 } } : { followScreen: v })} />
          </PanelSectionRow>
          <PanelSectionRow>
            <ToggleField label="Pulse red on low battery" checked={s.lowBattery}
              onChange={(v) => c.setRgb({ lowBattery: v })} />
          </PanelSectionRow>
          {s.lowBattery && (
            <PanelSectionRow>
              <SliderField label="Low battery at" value={s.lowBatteryAt} min={5} max={30} step={5} showValue
                valueSuffix="%" onChange={(v) => c.setRgb({ lowBatteryAt: v })} />
            </PanelSectionRow>
          )}
          <PanelSectionRow>
            <ToggleField label="Lights off on battery" checked={s.offOnBattery}
              description="Saves a little power when unplugged."
              onChange={(v) => c.setRgb({ offOnBattery: v })} />
          </PanelSectionRow>
          {r?.hasBootFlags && (
            <>
              <PanelSectionRow>
                <ToggleField label="Lights during boot" checked={r.rgbBoot}
                  description="Asks the controller to keep the rings lit before HHD starts. A HHD option, briefly reconnects the controller."
                  onChange={(v) => be.setRgbFlags(v, r.rgbCharging).then(() => c.refresh())} />
              </PanelSectionRow>
              <PanelSectionRow>
                <ToggleField label="Lights while charging asleep" checked={r.rgbCharging}
                  onChange={(v) => be.setRgbFlags(r.rgbBoot, v).then(() => c.refresh())} />
              </PanelSectionRow>
            </>
          )}
        </>
      )}
    </PanelSection>
  );
}

function Battery() {
  const c = useController();
  const st = c.state!;
  const b = st.battery;
  const ch = st.settings.charge;
  if (!b.present) return null;
  const apply = async (limit: number, travel: boolean) => {
    const r = await be.setCharge(limit, travel);
    if (!r.ok) toaster.toast({ title: "Ally Tweaks", body: `Charge limit failed: ${r.error}` });
    c.refresh();
  };
  return (
    <PanelSection title="Battery">
      <PanelSectionRow>
        <Field label={`${b.capacity ?? "?"}% · ${b.status}`} bottomSeparator="none">
          {b.watts != null ? `${b.watts} W` : ""}
        </Field>
      </PanelSectionRow>
      <Note>
        {b.health != null ? `Health ${b.health}% of design capacity` : "Health unknown"}
        {b.cycles != null && b.cycles > 0 ? ` · ${b.cycles} cycles` : ""}
        {b.threshold != null ? ` · charging stops at ${b.threshold}%` : ""}
      </Note>
      {st.chargeBackend === "none" ? (
        <Note warning>This kernel doesn't expose a charge limit for the battery.</Note>
      ) : (
        <>
          <PanelSectionRow>
            <DropdownItem
              label="Charge limit"
              description="80% is the sweet spot for an Ally that lives on the charger."
              rgOptions={LIMITS.map((l) => ({ data: l, label: l === 100 ? "Off (100%)" : `${l}%` }))}
              selectedOption={LIMITS.includes(ch.limit) ? ch.limit : 100}
              onChange={(o) => apply(o.data, ch.travel)}
            />
          </PanelSectionRow>
          {ch.limit < 100 && (
            <PanelSectionRow>
              <ToggleField label="Full charge once (travel)" checked={ch.travel}
                description="Charges to 100% now. Your limit comes back automatically when you unplug."
                onChange={(v) => apply(ch.limit, v)} />
            </PanelSectionRow>
          )}
          <Note>Set through {st.chargeBackend === "hhd" ? "Handheld Daemon, which re-applies it every boot" : "the kernel (asus-wmi); re-applied when Decky starts"}.</Note>
        </>
      )}
    </PanelSection>
  );
}

function Buttons() {
  const c = useController();
  const st = c.state!;
  const b = st.buttons;
  if (!b?.supported) return null;
  const game = c.appid ? st.settings.buttons.perGame[c.appid] : undefined;
  const opts = b.paddleOptions.map((o) => ({ data: o, label: PADDLES[o] ?? o }));
  return (
    <PanelSection title="Back buttons (M1 / M2)">
      <Note>Controller mode in HHD: {b.controllerMode === "uinput" ? "Xbox" : b.controllerMode}.{" "}
        {opts.length ? "" : "This mode has no back-button options; switch to Dualsense or Xbox in HHD."}</Note>
      {c.appid && opts.length > 0 && (
        <PanelSectionRow>
          <ToggleField label={`Own layout for ${st.game?.name ?? "this game"}`} checked={!!game}
            description="Applied when the game starts, undone when it closes. The controller reconnects for about a second when it changes."
            onChange={(v) => c.toggleGameButtons(v)} />
        </PanelSectionRow>
      )}
      {game ? (
        <>
          <PanelSectionRow>
            <DropdownItem label="M1 / M2 do" rgOptions={opts} selectedOption={game.paddles}
              onChange={(o) => c.editGameButtons((g) => { g.paddles = o.data; })} />
          </PanelSectionRow>
          <PanelSectionRow>
            <ToggleField label="Swap A/B and X/Y" checked={game.nintendo}
              onChange={(v) => c.editGameButtons((g) => { g.nintendo = v; })} />
          </PanelSectionRow>
        </>
      ) : opts.length > 0 && (
        <>
          <PanelSectionRow>
            <DropdownItem label="M1 / M2 do (all games)" rgOptions={opts} selectedOption={b.paddles ?? undefined}
              onChange={(o) => be.setButtonsGlobal(o.data, b.nintendo).then(() => c.refresh())} />
          </PanelSectionRow>
          <PanelSectionRow>
            <ToggleField label="Swap A/B and X/Y (all games)" checked={b.nintendo}
              onChange={(v) => be.setButtonsGlobal(b.paddles ?? "", v).then(() => c.refresh())} />
          </PanelSectionRow>
        </>
      )}
      <Note>With "Steam Input", M1/M2 show up as back paddles (L4/R4) in each game's Steam controller layout, where you can bind keys, macros or action-layer shifts per game.</Note>
    </PanelSection>
  );
}

function Panel() {
  const c = useController();
  const p = c.state!.panel;
  if (p.panelOverdrive == null && p.bootSound == null) return null;
  const set = async (key: string, v: boolean) => {
    const r = await be.setPanel(key, v);
    if (!r.ok) toaster.toast({ title: "Ally Tweaks", body: `Couldn't change setting${r.error ? `: ${r.error}` : ""}` });
    c.refresh();
  };
  return (
    <PanelSection title="Screen & system">
      {p.panelOverdrive != null && (
        <PanelSectionRow>
          <ToggleField label="Panel overdrive" checked={p.panelOverdrive}
            description="ASUS's LCD response-time boost: less ghosting in fast motion, slight overshoot on some edges."
            onChange={(v) => set("panelOverdrive", v)} />
        </PanelSectionRow>
      )}
      {p.bootSound != null && (
        <PanelSectionRow>
          <ToggleField label="Boot sound" checked={p.bootSound}
            description="The ROG chime when the Ally powers on."
            onChange={(v) => set("bootSound", v)} />
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}

function Content() {
  const c = useController();
  const st = c.state;
  if (!st) return <PanelSection><Note>Loading…</Note></PanelSection>;
  return (
    <>
      {!st.device.isAlly2023 && (
        <PanelSection>
          <Note warning>Made for the ROG Ally 2023 (RC71L). This looks like "{st.device.product || "unknown"}", so some options may not apply.</Note>
        </PanelSection>
      )}
      <Lighting />
      <Battery />
      <Buttons />
      <Panel />
      <PanelSection title="About">
        <Note>
          {st.device.isAlly2023 ? `ROG Ally ${st.device.chip} · BIOS ${st.device.bios}. ` : ""}
          Stays inside ASUS stock limits: no TDP, clock, fan or firmware changes. Power and TDP live in Vex Performance.
        </Note>
      </PanelSection>
    </>
  );
}

export default definePlugin(() => {
  controller.start();
  return {
    name: "Ally Tweaks",
    titleView: <div className={staticClasses.Title}>Ally Tweaks</div>,
    content: <Content />,
    icon: <FaGamepad />,
    onDismount() {
      controller.stop();
    },
  };
});
