import { ButtonItem, DropdownItem, Field, Navigation, PanelSectionRow, staticClasses, ToggleField } from "@decky/ui";
import { definePlugin, routerHook } from "@decky/api";
import { useEffect, useState } from "react";
import { FaFilm } from "react-icons/fa";
import { applyMovie, movieUrl, getSaver, getStatus, Kind, SaverSettings, setSaver, setShuffle, Status } from "./backend";
import { DEFAULT_SAVER, playMovie, previewSaver, SaverConfig, ScreensaverHost, setSaverConfig, watchController } from "./screensaver";
import { STYLES } from "./saverArt";
import { sectionFactory } from "./section";

const Section = sectionFactory("nightgrid-movies");

const note = { fontSize: "12px", lineHeight: "16px", opacity: 0.75, whiteSpace: "normal" as const };
const warn = { ...note, color: "#FF9F1C", opacity: 1 };

const MINUTES = [1, 2, 3, 5, 10, 15, 30];
const styleName = (id: string) => id === "random" ? "Random" : STYLES.find((x) => x.id === id)?.name ?? id;

function SaverSection({ s, setS }: { s: Status; setS: (s: Status) => void }) {
  const v = s.saver;
  const save = async (next: SaverSettings) => {
    setS({ ...s, saver: next });
    const stored = await setSaver(next);
    setSaverConfig(stored as SaverConfig);
  };
  return (
    <Section id="saver" title="Screensaver" defaultOpen
      summary={v.enabled ? `${styleName(v.style)} after ${v.minutes} min` : "Off"}>
      <PanelSectionRow>
        <ToggleField label="Screensaver" description="Covers Game Mode when nothing's pressed for a while. Never over a running game."
          checked={v.enabled} onChange={(on) => save({ ...v, enabled: on })} />
      </PanelSectionRow>
      <PanelSectionRow>
        <DropdownItem label="Start after" disabled={!v.enabled} selectedOption={v.minutes}
          rgOptions={MINUTES.map((m) => ({ data: m, label: `${m} min` }))}
          onChange={(o) => save({ ...v, minutes: o.data as number })} />
      </PanelSectionRow>
      <PanelSectionRow>
        <DropdownItem label="Style" disabled={!v.enabled} selectedOption={v.style}
          rgOptions={[{ data: "random", label: "Random" }, ...STYLES.map((x) => ({ data: x.id, label: x.name }))]}
          onChange={(o) => save({ ...v, style: o.data as string })} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => { Navigation.CloseSideMenus(); setTimeout(previewSaver, 400); }}>
          Preview
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <div style={note}>Any button, stick or touch wakes it. Steam's own dim and sleep timers still apply.</div>
      </PanelSectionRow>
    </Section>
  );
}

const nameOf = (s: Status, kind: Kind) => s.catalog[kind].find((m) => m.id === s[kind])?.name ?? "Steam default";

function PreviewButton({ id, name }: { id: string; name: string }) {
  const [state, setState] = useState<string | null>(null);
  const go = async () => {
    try {
      setState("Loading… 0%");
      const url = await movieUrl(id, (p) => setState(`Loading… ${p}%`));
      setState(null);
      Navigation.CloseSideMenus();
      setTimeout(() => playMovie(url), 400);
    } catch (e) { setState(`Preview failed: ${e}`); }
  };
  return (
    <>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={!!state && state.startsWith("Loading")} onClick={go}>
          {state && state.startsWith("Loading") ? state : `Preview ${name}`}
        </ButtonItem>
      </PanelSectionRow>
      {state && !state.startsWith("Loading") && <PanelSectionRow><div style={warn}>{state}</div></PanelSectionRow>}
    </>
  );
}

function Picker({ s, kind, label, busy, onPick }: {
  s: Status; kind: Kind; label: string; busy: boolean; onPick: (kind: Kind, id: string) => void;
}) {
  const opts = [{ data: "", label: "Steam default" }, ...s.catalog[kind].map((m) => ({
    data: m.id,
    label: (
      <span style={{ display: "inline-flex", alignItems: "center", gap: "10px" }}>
        {m.thumb && <img src={m.thumb} style={{ width: "64px", height: "36px", objectFit: "cover", border: "1px solid #1F2633" }} />}
        {m.name}
      </span>
    ),
  }))];
  const cur = s.catalog[kind].find((m) => m.id === s[kind]);
  return (
    <>
      <PanelSectionRow>
        <DropdownItem label={label} rgOptions={opts} selectedOption={s[kind]} disabled={busy}
          onChange={(o) => onPick(kind, o.data as string)} />
      </PanelSectionRow>
      {cur?.thumb && (
        <PanelSectionRow>
          <img src={cur.thumb} style={{ width: "100%", aspectRatio: "16 / 9", objectFit: "cover", display: "block", border: "1px solid #1F2633" }} />
        </PanelSectionRow>
      )}
      {cur?.about && <PanelSectionRow><div style={note}>{cur.about}</div></PanelSectionRow>}
      {cur && <PreviewButton id={cur.id} name={cur.name} />}
      {s.states[kind] === "other" && (
        <PanelSectionRow>
          <div style={warn}>
            Something else (another plugin or a file you added) replaced this video. Pick a Nightgrid one to take it
            back; the other file is kept as “.before-nightgrid” and restored when you switch to Steam default.
          </div>
        </PanelSectionRow>
      )}
    </>
  );
}

function Content() {
  const [s, setS] = useState<Status | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = async () => {
    const r = await getStatus();
    if (r.ok) { setS(r); setErr(null); } else setErr(r.error ?? "Couldn't read the movie folder.");
  };
  useEffect(() => { load(); }, []);

  const pick = async (kind: Kind, id: string) => {
    setBusy(true);
    try {
      const r = await applyMovie(kind, id);
      if (r.ok) { setS(r); setErr(null); } else setErr(r.error ?? "failed");
    } finally { setBusy(false); }
  };

  if (!s) return <Section id="status" title="Nightgrid Movies" collapsible={false}>
    <PanelSectionRow><div style={err ? warn : note}>{err ?? "Loading…"}</div></PanelSectionRow>
  </Section>;

  return (
    <>
      <Section id="status" title="Now playing" collapsible={false}>
        <PanelSectionRow>
          <Field label="Startup" description={nameOf(s, "boot") + (s.shuffle && s.boot ? " · shuffles each boot" : "")} bottomSeparator="none" />
        </PanelSectionRow>
        <PanelSectionRow>
          <Field label="Sleep" description={nameOf(s, "suspend")} bottomSeparator="none" />
        </PanelSectionRow>
        {err && <PanelSectionRow><div style={warn}>{err}</div></PanelSectionRow>}
      </Section>

      <Section id="boot" title="Startup movie" collapsible={false}>
        <Picker s={s} kind="boot" label="Movie" busy={busy} onPick={pick} />
        <PanelSectionRow>
          <ToggleField label="Shuffle each boot" description="A different Nightgrid movie every start-up"
            checked={s.shuffle} disabled={busy || !s.boot}
            onChange={async (v) => { await setShuffle(v); setS({ ...s, shuffle: v }); }} />
        </PanelSectionRow>
        {s.boot && (
          <PanelSectionRow>
            <div style={note}>
              Plays on the next start-up. If you picked a Points Shop movie in Settings → Customization → Startup
              Movie, set it back to the default there, or Steam plays that one instead.
            </div>
          </PanelSectionRow>
        )}
      </Section>

      <Section id="suspend" title="Sleep animation" summary={nameOf(s, "suspend")} defaultOpen>
        <Picker s={s} kind="suspend" label="Animation" busy={busy} onPick={pick} />
        <PanelSectionRow>
          <div style={note}>Plays when the Ally goes to sleep, from the menus and from in-game.</div>
        </PanelSectionRow>
      </Section>

      <SaverSection s={s} setS={setS} />

      <Section id="about" title="About" summary="Where the files go">
        <PanelSectionRow>
          <div style={note}>
            Videos are copied to {s.overrideDir}. Switching to “Steam default” or uninstalling this plugin removes them
            and puts back anything that was there before. Made for the Nightgrid CSS Loader theme.
          </div>
        </PanelSectionRow>
      </Section>
    </>
  );
}

export default definePlugin(() => {
  setSaverConfig(DEFAULT_SAVER);
  getSaver().then((c) => setSaverConfig(c as SaverConfig)).catch(() => { /* keep defaults */ });
  const stopController = watchController();
  routerHook.addGlobalComponent("NightgridScreensaver", ScreensaverHost);
  return {
    name: "Nightgrid Movies",
    titleView: <div className={staticClasses.Title}>Nightgrid Movies</div>,
    content: <Content />,
    icon: <FaFilm />,
    onDismount() {
      routerHook.removeGlobalComponent("NightgridScreensaver");
      stopController();
    },
  };
});
