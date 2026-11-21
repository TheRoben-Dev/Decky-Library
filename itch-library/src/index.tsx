import { ButtonItem, DropdownItem, Field, Navigation, PanelSectionRow, staticClasses, ToggleField } from "@decky/ui";
import { definePlugin, routerHook } from "@decky/api";
import { useEffect, useState } from "react";
import { FaGamepad } from "react-icons/fa";
import { cancelJob, listen, loadSettings, refreshInstalled } from "./actions";
import { getQueue, getRoots, Root, setOptions, Settings, signOut } from "./backend";
import { GamePage } from "./game";
import { GAME_ROUTE, LIBRARY_ROUTE, LibraryPage } from "./page";
import { sectionFactory } from "./section";
import { changed, fmtBytes, jobLine, state, updateCount, useStore } from "./state";
import { protonTools } from "./steam";
import { Bar, C, note } from "./ui";

const Section = sectionFactory("itch-library");

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
    <Section id="settings" title="Settings" summary={`${where?.label ?? "Internal"} · ${s.prefer === "windows" ? "Windows builds first" : "Linux builds first"}`}>
      <PanelSectionRow>
        <DropdownItem label="Install to" description={s.root}
          selectedOption={s.root} strDefaultLabel="Internal"
          rgOptions={roots.map((r) => ({ data: r.path, label: `${r.label} · ${fmtBytes(r.free)} free` }))}
          onChange={(o) => set({ root: o.data })} />
      </PanelSectionRow>
      <PanelSectionRow>
        <DropdownItem label="Builds" description="Used when a game has both. Already installed games keep theirs."
          selectedOption={s.prefer}
          rgOptions={[{ data: "linux", label: "Native Linux first" }, { data: "windows", label: "Windows (Proton) first" }]}
          onChange={(o) => set({ prefer: o.data })} />
      </PanelSectionRow>
      <PanelSectionRow>
        <DropdownItem label="Proton for Windows games" selectedOption={s.tool}
          rgOptions={[{ data: "", label: "Newest Proton (default)" }, ...tools.map((t) => ({ data: t.name, label: t.display }))]}
          onChange={(o) => set({ tool: o.data })} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField label="Show non-games" description="Soundtracks, books, assets and other purchases." checked={s.show_all}
          onChange={(v) => { set({ show_all: v }); state.games = null; }} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField label="Keep downloaded archives" description="Takes extra space; reinstalls skip the download." checked={s.keep_downloads}
          onChange={(v) => set({ keep_downloads: v })} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField label="Show adult content in Browse" description="Off by default. Adds the Adult / NSFW tags to Browse filters."
          checked={!!s.adult} onChange={(v) => { set({ adult: v }); state.store.items = null; state.store.key = ""; }} />
      </PanelSectionRow>
      {s.signedIn && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={async () => { state.settings = await signOut(); state.games = null; changed(); }}>
            Sign out of itch.io
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
      <Section id="status" title="itch.io" collapsible={false}>
        <PanelSectionRow>
          <Field label={set?.signedIn ? (user?.name || user?.username || "Signed in") : "Not signed in"} bottomSeparator="none">
            <span style={{ color: set?.signedIn ? C.ok : C.warn, fontSize: 12 }}>{set?.signedIn ? "ONLINE" : "SIGN IN"}</span>
          </Field>
        </PanelSectionRow>
        {set?.signedIn && (
          <PanelSectionRow>
            <div style={note}>{n} installed{upd ? ` · ${upd} update${upd > 1 ? "s" : ""}` : ""}</div>
          </PanelSectionRow>
        )}
        {s.jobs.map((j, i) => (
          <PanelSectionRow key={j.game_id}>
            <Field label={j.title} description={jobLine(j)} bottomSeparator="none" />
            {i === 0 && <Bar value={j.phase === "downloading" && j.total ? j.done / j.total : j.phase === "queued" ? 0 : 1} />}
          </PanelSectionRow>
        ))}
        {s.jobs.length > 0 && (
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => cancelJob(s.jobs[0].game_id)}>Cancel {s.jobs[0].title}</ButtonItem>
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={open}>{set?.signedIn ? "Open library" : "Sign in"}</ButtonItem>
        </PanelSectionRow>
      </Section>
      {set && <SettingsSection s={set} />}
      <Section id="about" title="About" summary="Your itch.io games in Game Mode">
        <PanelSectionRow>
          <div style={note}>
            Lists the games you own or claimed on itch.io, installs them (native Linux builds, or Windows builds through
            Proton) and adds each to Steam with generated artwork. Updates keep the saves a game keeps in its own folder.
            Nothing runs in the background: the library is fetched and updates are checked only when you open it.
            Unofficial; uses itch.io's public API with your own API key.
          </div>
        </PanelSectionRow>
      </Section>
    </>
  );
}

export default definePlugin(() => {
  routerHook.addRoute(LIBRARY_ROUTE, LibraryPage, { exact: true });
  routerHook.addRoute(GAME_ROUTE, GamePage, { exact: true });
  const unlisten = listen();
  return {
    name: "Itch Library",
    titleView: <div className={staticClasses.Title}>Itch Library</div>,
    content: <Content />,
    icon: <FaGamepad />,
    onDismount() {
      unlisten();
      routerHook.removeRoute(LIBRARY_ROUTE);
      routerHook.removeRoute(GAME_ROUTE);
    },
  };
});
