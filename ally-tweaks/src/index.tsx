import {
  DropdownItem,
  Field,
  Focusable,
  PanelSection,
  PanelSectionRow,
  SliderField,
  ToggleField,
  staticClasses,
} from "@decky/ui";
import { definePlugin, toaster } from "@decky/api";
import { useEffect, useReducer, useState } from "react";
import { FaGamepad } from "react-icons/fa";
import * as be from "./backend";
import { controller } from "./controller";
import { sectionFactory } from "./section";

const Section = sectionFactory("ally-tweaks");
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

const MODES_SYSFS: { data: LightMode; label: string }[] = [
  { data: "solid", label: "Solid" },
  { data: "split", label: "Left / right colors" },
  { data: "zones", label: "Four zones" },
];
const MODES_HHD: { data: LightMode; label: string }[] = [
  { data: "solid", label: "Solid" },
  { data: "pulse", label: "Pulse" },
  { data: "duality", label: "Two colors" },
  { data: "rainbow", label: "Rainbow" },
  { data: "spiral", label: "Spiral" },
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
  { label: "Red", hue: 0, saturation: 100 },
  { label: "Orange", hue: 25, saturation: 100 },
  { label: "Yellow", hue: 55, saturation: 100 },
  { label: "Green", hue: 120, saturation: 100 },
  { label: "Cyan", hue: 185, saturation: 100 },
  { label: "Blue", hue: 225, saturation: 100 },
  { label: "Purple", hue: 275, saturation: 100 },
  { label: "Pink", hue: 320, saturation: 80 },
  { label: "Warm white", hue: 30, saturation: 30 },
  { label: "White", hue: 0, saturation: 0 },
];
const PADDLES: Record<string, string> = {
  steam_input: "Steam Input (bind per game in Steam)",
  noob: "Keyboard / HHD overlay",
  touchpad: "Touchpad clicks",
  disabled: "Disabled",
};
const LIMITS = [70, 80, 85, 90, 95, 100];

const ACCENT = "#00E5FF"; // Nightgrid cyan

/** Big, controller-friendly colour picker: the focused swatch gets a thick
 *  Nightgrid-cyan ring, grows, and its name shows under the row; the colour in
 *  use gets a white check ring. */
function Swatches({ onPick, hue, sat }: { onPick: (hue: number, sat: number) => void; hue: number; sat: number }) {
  const [focus, setFocus] = useState<number | null>(null);
  const current = QUICK.findIndex((q) => q.saturation === sat && (sat === 0 || q.hue === hue));
  const label = focus != null ? QUICK[focus].label : current >= 0 ? QUICK[current].label : "Custom color";
  return (
    <PanelSectionRow>
      <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 6, padding: "6px 0 2px" }} flow-children="horizontal">
        {QUICK.map((q, i) => {
          const f = focus === i, on = current === i;
          return (
            <Focusable key={q.label}
              onActivate={() => onPick(q.hue, q.saturation)} onClick={() => onPick(q.hue, q.saturation)}
              onGamepadFocus={() => setFocus(i)} onGamepadBlur={() => setFocus((x) => (x === i ? null : x))}
              noFocusRing
              style={{
                width: 34, height: 34, borderRadius: 17, boxSizing: "border-box", padding: 3,
                border: `3px solid ${f ? ACCENT : on ? "#ffffffcc" : "transparent"}`,
                boxShadow: f ? `0 0 10px ${ACCENT}` : "none",
                transform: f ? "scale(1.15)" : "none", transition: "transform 80ms, box-shadow 80ms",
              }}>
              <div style={{ width: "100%", height: "100%", borderRadius: "50%", background: hsl(q.hue, q.saturation),
                border: "1px solid #ffffff40", boxSizing: "border-box" }} />
            </Focusable>
          );
        })}
      </Focusable>
      <div style={{ fontSize: 12, lineHeight: "16px", marginTop: 2, color: focus != null ? ACCENT : "#8B98A9" }}>
        {focus != null ? `Ⓐ Set ${label}` : `Current: ${label}`}
      </div>
    </PanelSectionRow>
  );
}

const ZONE_LABELS = ["Zone 1", "Zone 2", "Zone 3", "Zone 4"];

function LightEditor({ light }: { light: Light }) {
  const c = controller;
  const st = c.state;
  const follow = !!c.settings?.rgb.followScreen;
  const hhdMode = st?.rgbBackend === "hhd";
  const hwEffects = !hhdMode && !st?.leds.hidFallback ? st?.leds.effects ?? [] : [];
  const modes = hhdMode ? MODES_HHD : [
    ...MODES_SYSFS,
    ...(hwEffects.length ? [{ data: "hw" as LightMode, label: "Animated (controller effect)" }] : []),
  ];
  const [zone, setZone] = useState(0);
  // A light saved under the other backend falls back to Solid here.
  const shown = modes.some((m) => m.data === light.mode) ? light.mode : "solid";
  const colored = ["solid", "pulse", "duality", "split", "zones"].includes(shown) ||
    (shown === "hw" && !["rainbow", "chroma"].includes(light.hwEffect ?? ""));
  const zh = (light.zoneHues ?? [light.hue, light.hue, light.hue, light.hue]).slice(0, 4);
  const zs = (light.zoneSats ?? [light.saturation, light.saturation, light.saturation, light.saturation]).slice(0, 4);
  const editHue = shown === "zones" ? zh[zone] : light.hue;
  const editSat = shown === "zones" ? zs[zone] : light.saturation;
  const setColor = (h: number | null, sat: number | null) => c.editLight((l) => {
    if (shown === "zones") {
      const hs = [...zh]; const ss = [...zs];
      if (h != null) hs[zone] = h;
      if (sat != null) ss[zone] = sat;
      l.zoneHues = hs; l.zoneSats = ss;
    } else {
      if (h != null) l.hue = h;
      if (sat != null) l.saturation = sat;
    }
  });
  return (
    <>
      <PanelSectionRow>
        <DropdownItem label="Effect" rgOptions={modes} selectedOption={shown}
          onChange={(o) => c.editLight((l) => {
            l.mode = o.data;
            if (o.data === "zones" && !l.zoneHues) { l.zoneHues = [l.hue, l.hue, l.hue2, l.hue2]; l.zoneSats = [l.saturation, l.saturation, l.saturation, l.saturation]; }
            if (o.data === "hw" && !l.hwEffect) l.hwEffect = hwEffects.find((e) => e !== "monocolor") ?? hwEffects[0];
          })} />
      </PanelSectionRow>
      {shown === "hw" && (
        <>
          <PanelSectionRow>
            <DropdownItem label="Controller effect" rgOptions={hwEffects.map((e) => ({ data: e, label: e[0].toUpperCase() + e.slice(1) }))}
              selectedOption={light.hwEffect} onChange={(o) => c.editLight((l) => { l.hwEffect = o.data; })} />
          </PanelSectionRow>
          <PanelSectionRow>
            <SliderField label="Speed" value={light.hwSpeed ?? 50} min={0} max={100} step={10} showValue
              onChange={(v) => c.editLight((l) => { l.hwSpeed = v; })} />
          </PanelSectionRow>
        </>
      )}
      {shown === "zones" && (
        <>
          <PanelSectionRow>
            <Field label="Zones" bottomSeparator="none">
              <div style={{ display: "flex", gap: 8 }}>
                {zh.map((h, i) => <Swatch key={i} h={h} s={zs[i]} />)}
              </div>
            </Field>
          </PanelSectionRow>
          <PanelSectionRow>
            <DropdownItem label="Editing" rgOptions={ZONE_LABELS.map((l, i) => ({ data: i, label: l }))}
              selectedOption={zone} onChange={(o) => setZone(o.data)} />
          </PanelSectionRow>
        </>
      )}
      {colored && (
        <>
          <Swatches onPick={(h, sat) => setColor(h, sat)} hue={editHue} sat={editSat} />
          <PanelSectionRow>
            <SliderField label={shown === "split" ? "Left ring hue" : "Hue"} value={editHue} min={0} max={360} step={5} showValue
              onChange={(v) => setColor(v, null)} />
          </PanelSectionRow>
          <PanelSectionRow>
            <SliderField label="Saturation" value={editSat} min={0} max={100} step={5} showValue
              onChange={(v) => setColor(null, v)} />
          </PanelSectionRow>
          {(shown === "duality" || shown === "split") && (
            <PanelSectionRow>
              <SliderField label={shown === "split" ? "Right ring hue" : "Second hue"} value={light.hue2} min={0} max={360} step={5} showValue
                onChange={(v) => c.editLight((l) => { l.hue2 = v; })} />
            </PanelSectionRow>
          )}
          {shown === "split" && (
            <PanelSectionRow>
              <ToggleField label="Swap sides" checked={!!light.swapSides}
                description="Use this if the colors land on the wrong rings."
                onChange={(v) => c.editLight((l) => { l.swapSides = v; })} />
            </PanelSectionRow>
          )}
        </>
      )}
      {shown !== "off" && (
        <PanelSectionRow>
          <SliderField
            label={follow ? "Max brightness" : "Brightness"}
            value={light.brightness}
            min={hhdMode ? 10 : 5}
            max={100}
            step={hhdMode ? 10 : 5}
            showValue
            description={[
              follow ? "Rings run at this level when the screen is at 100%." : "",
              hhdMode && !colored ? "Rainbow and spiral only have three hardware levels: low, medium, high." : "",
            ].filter(Boolean).join(" ") || undefined}
            onChange={(v) => c.editLight((l) => { l.brightness = v; })}
          />
        </PanelSectionRow>
      )}
      {["pulse", "duality", "spiral"].includes(shown) && (
        <PanelSectionRow>
          <DropdownItem label="Speed" rgOptions={SPEEDS} selectedOption={light.speed}
            onChange={(o) => c.editLight((l) => { l.speed = o.data; })} />
        </PanelSectionRow>
      )}
      {shown === "spiral" && (
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
  const extrasSummary = [
    s.reactive !== "none" ? `color follows ${s.reactive}` : null,
    s.followScreen ? "follows screen" : null,
    s.lowBattery ? `red pulse ≤${s.lowBatteryAt}%` : null,
    s.offOnBattery ? "off on battery" : null,
  ].filter(Boolean).join(" · ") || "None on";
  return (
    <>
    <PanelSection title="Ring lighting">
      {st.rgbBackend === "none" && <Note warning>No ring LED control found: neither the kernel's joystick-ring LED nor Handheld Daemon is available on this system.</Note>}
      {st.rgbBackend === "sysfs" && st.leds.clamped && st.leds.hidFallback && (
        <Note>Your kernel caps ring color values at 255, which turns every color blue through the normal LED interface. Colors are sent with the ring LED's own color command instead (the one the driver and HHD use). Hardware animations aren't available in this mode.</Note>
      )}
      {st.rgbBackend === "sysfs" && st.leds.clamped && !st.leds.hidFallback && (
        <Note warning>Your kernel caps each ring color value at 255 (multi_max_intensity), but the Ally driver packs the whole RGB color into that one value, so every color comes out as a shade of blue. This is a kernel/driver bug, not a setting. The plugin couldn't find the ring LED's HID interface to work around it.</Note>
      )}
      {st.rgbBackend === "sysfs" && st.leds.lastError && (!st.leds.clamped || st.leds.hidFallback) && (
        <Note warning>The ring LED rejected the last change: {st.leds.lastError}</Note>
      )}
      {st.rgbBackend === "sysfs" && st.leds.lightbarTarget && (
        <Note warning>InputPlumber is emulating a {st.leds.lightbarTarget}, so Steam's light-bar color (blue by default) gets copied onto the rings and overrides these settings. Set the controller's light bar to off or a color in Steam (Settings → Controller → your controller), or use an Xbox-type controller mode.</Note>
      )}
      {st.rgbBackend === "sysfs" && st.leds.contested && !st.leds.lightbarTarget && (
        <Note warning>Another program keeps changing the ring colors, so the plugin stopped fighting it. Your next change here still applies.</Note>
      )}
      {r?.controllerOwnsLeds && <Note warning>HHD's Dualsense "LED Support" is on, so games control the rings. Turn it off in HHD to use these settings.</Note>}
      {r && !r.hhdRgbEnabled && <Note>RGB support is off in HHD. Changing a setting here turns it on.</Note>}
      <PanelSectionRow>
        <ToggleField label="Manage ring lighting" checked={s.managed}
          description={st.rgbBackend === "hhd"
            ? "Saved in Handheld Daemon, so it stays on when this plugin or Decky isn't loaded."
            : "Set through the kernel LED driver. A small restore service brings it back after reboot and sleep, even without Decky."}
          onChange={(v) => c.setRgb({ managed: v })} />
      </PanelSectionRow>
      {s.managed && (
        <>
          <PanelSectionRow>
            <ToggleField label={gameLight ? "Rings on in this game" : "Rings on"} checked={light.mode !== "off"}
              description={light.mode === "off" ? "Rings are off. Your color is kept for when you turn them back on." : undefined}
              onChange={(v) => c.editLight((l) => {
                if (v) { l.mode = l.prevMode && l.prevMode !== "off" ? l.prevMode : "solid"; }
                else { if (l.mode !== "off") l.prevMode = l.mode; l.mode = "off"; }
              })} />
          </PanelSectionRow>
          {st.lightReason && <Note>Now showing: {st.lightReason}</Note>}
          {c.appid && (
            <PanelSectionRow>
              <ToggleField label={`Own lighting for ${st.game?.name ?? "this game"}`} checked={!!gameLight}
                onChange={(v) => c.toggleGameLight(v)} />
            </PanelSectionRow>
          )}
          <Note>{gameLight ? "Editing this game's lighting." : "Editing the default lighting."}</Note>
          {light.mode !== "off" && <LightEditor light={light} />}
        </>
      )}
    </PanelSection>
    {s.managed && (
      <Section id="lighting-extras" title="Lighting extras" summary={extrasSummary}>
        {!gameLight && (
          <PanelSectionRow>
            <DropdownItem label="Color follows"
              rgOptions={REACTIVE.filter((r) => r.data !== "tdp" || st.rgbBackend === "hhd")}
              selectedOption={s.reactive === "tdp" && st.rgbBackend !== "hhd" ? "none" : s.reactive}
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
      </Section>
    )}
    </>
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
  if (!b?.supported) {
    if (!st.inputplumber) return null;
    return (
      <Section id="buttons" title="Back buttons (M1 / M2)" summary="Bind them per game in Steam's controller layout">
        <Note>InputPlumber presents M1/M2 as Xbox Elite back paddles, so Steam already lets you bind them per game: the game's controller layout in Steam, under the back paddles. Keys, macros and action-layer shifts all work there, with nothing extra running.</Note>
      </Section>
    );
  }
  const game = c.appid ? st.settings.buttons.perGame[c.appid] : undefined;
  const opts = b.paddleOptions.map((o) => ({ data: o, label: PADDLES[o] ?? o }));
  return (
    <Section id="buttons" title="Back buttons (M1 / M2)" summary={game ? `Own layout for ${st.game?.name ?? "this game"}` : `All games: ${PADDLES[b.paddles ?? ""] ?? b.paddles ?? "default"}`}>
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
    </Section>
  );
}

function Panel() {
  const c = useController();
  const p = c.state!.panel;
  const st = c.state!;
  const sys = st.settings.system;
  const setSys = async (key: string, v: boolean | string) => {
    c.setSystemLocal(key, v);
    const r = await be.setSystem(key, v);
    if (!r.ok) toaster.toast({ title: "Ally Tweaks", body: `Saved, but applying it failed${r.error ? `: ${r.error}` : ""}` });
    c.refresh();
  };
  if (p.panelOverdrive == null && p.bootSound == null && !st.cpu.touch && st.cpu.audioPowerSave == null && !st.cpu.amps) return null;
  const displaySummary = [
    p.panelOverdrive != null ? `overdrive ${p.panelOverdrive ? "on" : "off"}` : null,
    st.cpu.touch ? `touch ${sys.touch === "games" ? "off in games" : sys.touch ?? "on"}` : null,
    sys.audioPowersaveOff || sys.ampsAwake ? "audio fixes on" : null,
  ].filter(Boolean).join(" · ");
  const set = async (key: string, v: boolean) => {
    const r = await be.setPanel(key, v);
    if (!r.ok) toaster.toast({ title: "Ally Tweaks", body: `Couldn't change setting${r.error ? `: ${r.error}` : ""}` });
    c.refresh();
  };
  return (
    <Section id="display" title="Display & audio" summary={displaySummary}>
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
          {st.cpu.touch && (
        <PanelSectionRow>
          <DropdownItem label="Touchscreen"
            rgOptions={[
              { data: "on", label: "On" },
              { data: "games", label: "Off while a game runs" },
              { data: "off", label: "Off" },
            ]}
            selectedOption={sys.touch ?? "on"}
            description="Stops accidental touches (e.g. palms on the screen edge). Turns back on instantly."
            onChange={(o) => setSys("touch", o.data)} />
        </PanelSectionRow>
      )}
      {st.cpu.audioPowerSave != null && (
        <PanelSectionRow>
          <ToggleField label="Audio codec power saving off" checked={sys.audioPowersaveOff}
            description="Keeps the sound chip awake, so there's no pop or cut-off first syllable when sound starts after silence. Bazzite already keeps PipeWire outputs awake; this also covers the codec itself. About 0.1–0.3 W."
            onChange={(v) => setSys("audioPowersaveOff", v)} />
        </PanelSectionRow>
      )}
      {st.cpu.amps && (
        <PanelSectionRow>
          <ToggleField label="Keep speaker amps awake" checked={sys.ampsAwake}
            description={`Workaround for one speaker going silent after a pause: stops the ${st.cpu.amps.count} ${st.cpu.amps.driver === "cs35l41-hda" ? "Cirrus CS35L41" : "TI TAS2781"} speaker amps from powering down between sounds, so there's nothing to fail on wake-up. Experimental (not a confirmed fix); best combined with "Audio codec power saving off". A little more idle power.`}
            onChange={(v) => setSys("ampsAwake", v)} />
        </PanelSectionRow>
      )}
    </Section>
  );
}

function SystemTweaks() {
  const c = useController();
  const st = c.state!;
  const sys = st.settings.system;
  const set = async (key: string, v: boolean) => {
    c.setSystemLocal(key, v);
    const r = await be.setSystem(key, v);
    if (!r.ok) toaster.toast({ title: "Ally Tweaks", body: `Saved, but applying it failed${r.error ? `: ${r.error}` : ""}` });
    c.refresh();
  };
  const systemSummary = [
    sys.wifiPowersaveOff ? "Wi-Fi PS off" : null,
    sys.usbAutosuspendOff ? "USB autosuspend off" : null,
    st.cpu.splitLockMitigation ? "split-lock on" : null,
    st.cpu.pcie?.next ? "PCIe PM off" : null,
  ].filter(Boolean).join(" · ") || "Bazzite defaults";
  return (
    <Section id="system" title="Connectivity & system" summary={systemSummary}>
      {st.wifi.supported && (
        <PanelSectionRow>
          <ToggleField label="Wi-Fi power saving off" checked={sys.wifiPowersaveOff}
            description={`Steadier ping and fewer stutters in streaming / online games. Costs roughly 0.2–0.5 W on battery. Stays off even in Power Saver mode, after sleep and after reboot.${st.wifi.ifaces.length ? ` Now: ${st.wifi.powerSaveOn ? "on" : "off"} (${st.wifi.ifaces.join(", ")}).` : ""}`}
            onChange={(v) => set("wifiPowersaveOff", v)} />
        </PanelSectionRow>
      )}
      {st.usb.supported && (
        <PanelSectionRow>
          <ToggleField label="USB autosuspend off" checked={sys.usbAutosuspendOff}
            description="Stops docks, USB controllers and adapters from dropping out after idling. Slightly more battery use while USB devices are plugged in. When turned off again, devices already plugged in keep this until replugged or reboot."
            onChange={(v) => set("usbAutosuspendOff", v)} />
        </PanelSectionRow>
      )}
      {st.cpu.splitLockMitigation != null && (
        <PanelSectionRow>
          <ToggleField label="Split-lock mitigation" checked={!!st.cpu.splitLockMitigation}
            description="Off by default on Bazzite (recommended for gaming): when on, the kernel deliberately slows programs that do split-lock memory accesses, which hurts some games badly. Only turn it on if you want strict isolation between programs."
            onChange={(v) => set("splitLockMitigation", v)} />
        </PanelSectionRow>
      )}
      {st.cpu.pcie.supported && <PcieToggle />}
    </Section>
  );
}

const EPP_LABELS: Record<string, string> = {
  "": "Follow power profile (default)",
  performance: "Performance",
  balance_performance: "Balanced performance",
  balance_power: "Balanced power",
  power: "Power saving",
};

function CpuTweaks() {
  const c = useController();
  const st = c.state!;
  const sys = st.settings.system;
  const cpu = st.cpu;
  if (cpu.boost == null && cpu.smt == null && !cpu.epp) return null;
  const set = async (key: string, v: boolean | string) => {
    c.setSystemLocal(key, v);
    const r = await be.setSystem(key, v);
    if (!r.ok) toaster.toast({ title: "Ally Tweaks", body: `Saved, but applying it failed${r.error ? `: ${r.error}` : ""}` });
    c.refresh();
  };
  return (
    <Section id="cpu" title="CPU" summary={[sys.cpuBoostOff ? "boost off" : "boost on", sys.smtOff ? "SMT off" : null, sys.epp ? `EPP ${EPP_LABELS[sys.epp] ?? sys.epp}` : null].filter(Boolean).join(" · ")}>
      {cpu.boost != null && (
        <PanelSectionRow>
          <ToggleField label="CPU boost" checked={!sys.cpuBoostOff}
            description="Turning boost off caps the CPU at its base clock: cooler, quieter and longer battery, at some cost in CPU-heavy games. Stays off across power-profile changes, sleep and reboot."
            onChange={(v) => set("cpuBoostOff", !v)} />
        </PanelSectionRow>
      )}
      {cpu.smt != null && (
        <PanelSectionRow>
          <ToggleField label="SMT (16 threads)" checked={!sys.smtOff}
            description="Turning SMT off leaves 8 cores / 8 threads. Saves a little power and helps a few older games; hurts games and emulators that use many threads."
            onChange={(v) => set("smtOff", !v)} />
        </PanelSectionRow>
      )}
      {cpu.epp && cpu.epp.available.length > 0 && (
        <PanelSectionRow>
          <DropdownItem label="CPU energy preference (EPP)"
            description={`How eagerly the CPU clocks up. "Follow power profile" lets Steam's power mode decide. Now: ${EPP_LABELS[cpu.epp.current ?? ""] ?? cpu.epp.current}.`}
            rgOptions={["", ...cpu.epp.available].map((v) => ({ data: v, label: EPP_LABELS[v] ?? v }))}
            selectedOption={sys.epp}
            onChange={(o) => set("epp", o.data)} />
        </PanelSectionRow>
      )}
      <Note>All within ASUS stock limits. TDP and GPU clocks stay in Vex Performance.</Note>
    </Section>
  );
}

function PcieToggle() {
  const c = useController();
  const p = c.state!.cpu.pcie;
  const [busy, setBusy] = useState(false);
  return (
    <>
      <PanelSectionRow>
        <ToggleField label="PCIe power management off" checked={p.next} disabled={busy}
          description={busy ? "Applying… this takes up to a minute."
            : `Same as "ujust manage-pcie-power": stops the PCIe bus from napping, which can remove micro-stutters and SSD latency spikes. Costs some battery and can raise sleep drain. Needs a reboot.${p.rebootNeeded ? " Reboot to apply." : ""}`}
          onChange={async (v) => {
            setBusy(true);
            const r = await be.setPcie(v);
            setBusy(false);
            if (!r.ok) toaster.toast({ title: "Ally Tweaks", body: `PCIe change failed: ${r.error}` });
            else toaster.toast({ title: "Ally Tweaks", body: "Reboot to apply the PCIe change." });
            c.refresh();
          }} />
      </PanelSectionRow>
    </>
  );
}

const APU_LABELS: Record<number, string> = { 0: "Auto (ASUS default)", 1: "2 GB", 2: "3 GB", 3: "4 GB", 5: "6 GB", 7: "8 GB" };

function GpuMemory() {
  const c = useController();
  const a = c.state!.apuMem;
  if (!a) return null;
  return (
    <Section id="vram" title="GPU memory (VRAM)" summary={APU_LABELS[a.current ?? 0] ?? `${(a.current ?? 0) + 1} GB`}>
      <PanelSectionRow>
        <DropdownItem label="Memory reserved for the GPU"
          rgOptions={a.choices.map((i) => ({ data: i, label: APU_LABELS[i] ?? `${i + 1} GB` }))}
          selectedOption={a.current ?? 0}
          description="Armoury Crate's 'Memory assigned to GPU'. More helps games that check VRAM size (and some UE5 titles); it's taken from system RAM, so 6 GB leaves 10 GB for everything else. Needs a reboot."
          onChange={async (o) => {
            const r = await be.setApuMem(o.data);
            toaster.toast({ title: "Ally Tweaks", body: r.ok ? "Reboot to apply the new GPU memory size." : `Couldn't change it${r.error ? `: ${r.error}` : ""}` });
            c.refresh();
          }} />
      </PanelSectionRow>
    </Section>
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
      {Object.keys(st.sysErrors ?? {}).length > 0 && (
        <PanelSection>
          {Object.entries(st.sysErrors ?? {}).map(([k, m]) => (
            <Note key={k} warning>{k}: saved, but applying it failed ({m}). It's retried at boot and while the plugin runs; the log has details.</Note>
          ))}
        </PanelSection>
      )}
      <Lighting />
      <Battery />
      <Buttons />
      <Panel />
      <SystemTweaks />
      <CpuTweaks />
      <GpuMemory />
      <Section id="about" title="About" summary={st.device.isAlly2023 ? `ROG Ally ${st.device.chip} · BIOS ${st.device.bios}` : st.device.product}>
        <Note>
          {st.device.isAlly2023 ? `ROG Ally ${st.device.chip} · BIOS ${st.device.bios}. ` : ""}
          Stays inside ASUS stock limits: no TDP, clock, fan or firmware changes. Power and TDP live in Vex Performance.
        </Note>
        <Note>Already set by Bazzite, nothing to change: zram swap (zstd, half of RAM) with swappiness 180, low-latency Bluetooth for controllers, and PipeWire outputs that never sleep.</Note>
      </Section>
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
