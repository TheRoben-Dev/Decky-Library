import { ButtonItem, DropdownItem, Field, Navigation, PanelSectionRow, staticClasses, ToggleField } from "@decky/ui";
import { definePlugin, routerHook } from "@decky/api";
import { useEffect, useState } from "react";
import { FaStore } from "react-icons/fa";
import { cancelJob, listen, loadSettings, refreshInstalled } from "./actions";
import { getQueue, getRoots, Root, setOptions, Settings, signOut } from "./backend";
import { GamePage, OfferPage } from "./game";
import { LibraryPage } from "./page";
import { GAME_ROUTE, LIBRARY_ROUTE, OFFER_ROUTE } from "./routes";
import { sectionFactory } from "./section";
import { changed, fmtBytes, jobLine, state, updateCount, useStore } from "./state";
import { protonTools } from "./steam";
import { Bar, C, note } from "./ui";

const Section = sectionFactory("epic-library");

function open() {
  Navigation.CloseSideMenus();
  Navigation.Navigate(LIBRARY_ROUTE);
}

function SettingsSection({ s }: { s: Settings }) {
  const [roots, setRoots] = useState<Root[]>([]);
  const [tools, setTools] = useState<{ name: string; display: string }[]>([]);
  useEffect(() => {
    getRoots().then(setRoots).catch(() => {});
    protonTools().then(setTools).catch(() => {});
  }, []);
  const set = async (patch: Partial<Settings>) => {
    const r = await setOptions(patch);
    if (r.ok) { state.settings = r.settings; changed(); }
  };
  const where = roots.find((r) => r.path === s.root);
  return (
    <Section id="settings" title="Settings" summary={`${where?.label ?? "Internal"} · ${s.tool || "newest Proton"}`}>
      <PanelSectionRow>
        <DropdownItem label="Install to" description={s.root}
          selectedOption={s.root} strDefaultLabel="Internal"
          rgOptions={roots.map((r) => ({ data: r.path, label: `${r.label} · ${fmtBytes(r.free)} free` }))}
          onChange={(o) => set({ root: o.data })} />
      </PanelSectionRow>
      <PanelSectionRow>
        <DropdownItem label="Proton" description="New Steam shortcuts use this. Change one game in its Steam properties." selectedOption={s.tool}
          rgOptions={[{ data: "", label: "Newest Proton (default)" }, ...tools.map((t) => ({ data: t.name, label: t.display }))]}
          onChange={(o) => set({ tool: o.data })} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField label="Install owned DLC" description="Downloads the DLC you own together with the game." checked={s.dlcs}
          onChange={(v) => set({ dlcs: v })} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField label="Show games from other launchers" description="EA app / Ubisoft Connect games you own on Epic (not installable here)." checked={s.show_all}
          onChange={(v) => { set({ show_all: v }); state.games = null; }} />
      </PanelSectionRow>
      {s.signedIn && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={async () => { state.settings = await signOut(); state.games = null; changed(); }}>
            Sign out of Epic
          </ButtonItem>
        </PanelSectionRow>
      )}
    </Section>
  );
}

function Content() {
  const s = useStore();
  useEffect(() => {
    loadSettings().catch(() => {});
    refreshInstalled().catch(() => {});
    getQueue().then((j) => { state.jobs = j; changed(); }).catch(() => {});
  }, []);
  const set = s.settings;
  const n = Object.keys(s.installed).length;
  const upd = updateCount();
  const user = set?.user;

  return (
    <>
      <Section id="status" title="Epic Games" collapsible={false}>
        <PanelSectionRow>
          <Field label={set?.signedIn ? (user?.name || "Signed in") : "Not signed in"} bottomSeparator="none">
            <span style={{ color: set?.signedIn ? C.ok : C.warn, fontSize: 12 }}>{set?.signedIn ? "ONLINE" : "SIGN IN"}</span>
          </Field>
        </PanelSectionRow>
        {set?.signedIn && (
          <PanelSectionRow>
            <div style={note}>{n} installed{upd ? ` · ${upd} update${upd > 1 ? "s" : ""}` : ""}</div>
          </PanelSectionRow>
        )}
        {s.jobs.map((j, i) => (
          <PanelSectionRow key={j.app}>
            <Field label={j.title} description={jobLine(j)} bottomSeparator="none" />
            {i === 0 && <Bar value={j.phase === "downloading" && j.total ? j.done / j.total : j.phase === "queued" ? 0 : 1} />}
          </PanelSectionRow>
        ))}
        {s.jobs.length > 0 && (
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => cancelJob(s.jobs[0].app)}>Pause {s.jobs[0].title}</ButtonItem>
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={open}>{set?.signedIn ? "Open library" : "Sign in"}</ButtonItem>
        </PanelSectionRow>
      </Section>
      {set && <SettingsSection s={set} />}
      {set?.problem && (
        <PanelSectionRow><div style={{ ...note, color: C.warn, opacity: 1 }}>{set.problem}</div></PanelSectionRow>
      )}
      <Section id="about" title="About" summary="Your Epic games in Game Mode">
        <PanelSectionRow>
          <div style={note}>
            Lists the games you own or claimed on the Epic Games Store, browses the store, installs games through Proton
            and adds each to Steam with its own artwork. Games launch with a fresh Epic sign-in token, so online and
            DRM-protected games work like in the Epic launcher. Nothing runs in the background. Unofficial; downloads use
            Legendary (GPL-3.0), an open-source Epic launcher.
          </div>
        </PanelSectionRow>
      </Section>
    </>
  );
}

export default definePlugin(() => {
  routerHook.addRoute(LIBRARY_ROUTE, LibraryPage, { exact: true });
  routerHook.addRoute(GAME_ROUTE, GamePage, { exact: true });
  routerHook.addRoute(OFFER_ROUTE, OfferPage, { exact: true });
  const unlisten = listen();
  return {
    name: "Epic Library",
    titleView: <div className={staticClasses.Title}>Epic Library</div>,
    content: <Content />,
    icon: <FaStore />,
    onDismount() {
      unlisten();
      routerHook.removeRoute(LIBRARY_ROUTE);
      routerHook.removeRoute(GAME_ROUTE);
      routerHook.removeRoute(OFFER_ROUTE);
    },
  };
});
