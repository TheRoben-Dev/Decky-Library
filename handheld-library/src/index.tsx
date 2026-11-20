import {
  ButtonItem, ConfirmModal, DropdownItem, Navigation, PanelSection,
  PanelSectionRow, showModal, staticClasses, TextField, ToggleField,
} from "@decky/ui";
import { definePlugin, toaster } from "@decky/api";
import { useEffect, useMemo, useState } from "react";
import { FaEyeSlash, FaFilter } from "react-icons/fa";
import { HiddenTab } from "./hiddenTab";
import { installLibrary, LIBRARY_TABS, libraryActive, seenLibraryTabs, setLibraryConfig, tabMasterInstalled, uninstallLibrary } from "./library";
import { installQam, onSeenTabs, qamActive, seenTabs, setHiddenTabs, uninstallQam } from "./qam";
import { GameRow, note, warn } from "./ui";
import { deleteCollection, Game, isHidden, launch } from "./steam";
import { loadSettings, snapshot, start, stop, subscribe, sync, updateSettings } from "./engine";

const PAGE = 25;

function useEngine() {
  const [s, set] = useState(snapshot());
  useEffect(() => subscribe(() => set(snapshot())), []);
  return s;
}

function confirm(title: string, body: string, okText: string): Promise<boolean> {
  return new Promise((resolve) => {
    showModal(<ConfirmModal strTitle={title} strDescription={body} strOKButtonText={okText}
      onOK={() => resolve(true)} onCancel={() => resolve(false)} />);
  });
}

function openPage(appid: number) {
  Navigation.CloseSideMenus();
  Navigation.Navigate(`/library/app/${appid}`);
}

function ago(t: number): string {
  const m = Math.round((Date.now() - t) / 60000);
  return m < 1 ? "just now" : m < 60 ? `${m} min ago` : `${Math.round(m / 60)} h ago`;
}

const ctrlLabel = (g: Game) => (g.controller === 2 ? "Full controller" : "Partial controller");

function FilterView() {
  const st = useEngine();
  const s = st.settings;
  const [shown, setShown] = useState(PAGE);
  const [name, setName] = useState(s?.collectionName ?? "");
  useEffect(() => { if (s) setName(s.collectionName); }, [s?.collectionName]);

  const list = useMemo(() => st.matches.filter((m) =>
    !isHidden(m.g.appid) && (!s?.installedOnly || m.g.installed)), [st.matches, s?.installedOnly]);
  if (!s) return <PanelSection><PanelSectionRow><div style={note}>Loading…</div></PanelSectionRow></PanelSection>;

  const nothingAccepted = s.deckMin === "off" && !s.steamOS && !s.native && s.protonDB === "off";
  const status = !s.enabled ? "Collection sync is off."
    : st.syncing ? "Syncing…"
    : st.last?.ok ? `"${s.collectionName}": ${st.last.count} games · synced ${ago(st.last.at)}`
    : st.last?.error ?? "Waiting for the Steam library to load…";

  return (
    <>
      <PanelSection title="Library collection">
        <PanelSectionRow>
          <div style={st.last && !st.last.ok ? warn : note}>{status}</div>
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField label="Keep collection in sync" checked={s.enabled}
            description="Shows the matches as a collection in Library → Collections. Updates by itself."
            onChange={(v) => updateSettings({ enabled: v })} />
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField label="Collection name" value={name} onChange={(e) => setName(e.target.value)}
            onBlur={() => name.trim() && name.trim() !== s.collectionName && updateSettings({ collectionName: name.trim() })} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={st.syncing} onClick={() => sync()}>Sync now</ButtonItem>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Rules">
        <PanelSectionRow>
          <DropdownItem label="Steam Deck rating" selectedOption={s.deckMin}
            rgOptions={[
              { data: "playable", label: "Verified or Playable" },
              { data: "verified", label: "Verified only" },
              { data: "off", label: "Ignore" },
            ]}
            onChange={(o) => updateSettings({ deckMin: o.data })} />
        </PanelSectionRow>
        <PanelSectionRow>
          <DropdownItem label="Controller support" selectedOption={s.controller}
            rgOptions={[
              { data: "partial", label: "Full or partial" },
              { data: "full", label: "Full only" },
            ]}
            onChange={(o) => updateSettings({ controller: o.data })} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField label="Also: SteamOS Compatible" checked={s.steamOS}
            description="Steam's rating for SteamOS PCs and handhelds that aren't a Deck."
            onChange={(v) => updateSettings({ steamOS: v })} />
        </PanelSectionRow>
        <PanelSectionRow>
          <DropdownItem label="Also: ProtonDB" selectedOption={s.protonDB}
            rgOptions={[
              { data: "off", label: "Off" },
              { data: "gold", label: "Gold or Platinum" },
              { data: "platinum", label: "Platinum only" },
            ]}
            onChange={(o) => updateSettings({ protonDB: o.data })} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField label="Also: native Linux build" checked={s.native}
            onChange={(v) => updateSettings({ native: v })} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField label="Never include Deck Unsupported" checked={s.excludeUnsupported}
            description="Valve's Unsupported rating wins over ProtonDB, SteamOS and native."
            onChange={(v) => updateSettings({ excludeUnsupported: v })} />
        </PanelSectionRow>
        {nothingAccepted && <PanelSectionRow><div style={warn}>No rating is accepted, so nothing matches.</div></PanelSectionRow>}
      </PanelSection>

      <PanelSection title={`Matches (${list.length})`}>
        <PanelSectionRow>
          <ToggleField label="Installed only" checked={s.installedOnly}
            onChange={(v) => { setShown(PAGE); updateSettings({ installedOnly: v }, false); }} />
        </PanelSectionRow>
        {list.length === 0 && <PanelSectionRow><div style={note}>No games match yet.</div></PanelSectionRow>}
        {list.slice(0, shown).map(({ g, why }) => (
          <GameRow key={g.appid} g={g} desc={`${why} · ${ctrlLabel(g)}${g.installed ? "" : " · not installed"}`}
            actions={[
              { label: g.installed ? "Play" : "Install", onClick: () => { Navigation.CloseSideMenus(); launch(g); } },
              { label: "Page", onClick: () => openPage(g.appid) },
            ]} />
        ))}
        {list.length > shown && (
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => setShown(shown + PAGE)}>Show more ({list.length - shown} left)</ButtonItem>
          </PanelSectionRow>
        )}
      </PanelSection>

      {s.collectionId && (
        <PanelSection title="Clean up">
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={async () => {
              if (!(await confirm("Delete the collection?", `Removes "${s.collectionName}" from your library (the games stay). Sync is turned off.`, "Delete"))) return;
              const ok = await deleteCollection(s.collectionId);
              await updateSettings({ enabled: false, collectionId: "" }, false);
              toaster.toast({ title: "Handheld Library", body: ok ? "Collection deleted." : "Collection was already gone." });
            }}>Delete collection</ButtonItem>
          </PanelSectionRow>
        </PanelSection>
      )}
    </>
  );
}

function QamTabsSection() {
  const st = useEngine();
  const [tabs, setTabs] = useState(seenTabs());
  useEffect(() => onSeenTabs(() => setTabs(seenTabs())), []);
  const s = st.settings;
  if (!s) return null;
  const hiddenSet = new Set(s.hiddenQamTabs);
  return (
    <PanelSection title="Quick Access tabs">
      {!qamActive() && (
        <PanelSectionRow><div style={warn}>Decky's Quick Access hook wasn't found, so the Hidden games tab and tab hiding are off. Quick Access is unchanged.</div></PanelSectionRow>
      )}
      <PanelSectionRow>
        <div style={note}>Turn a tab off to remove its icon from Quick Access. Takes effect the next time Quick Access opens. Decky's own tab always stays.</div>
      </PanelSectionRow>
      {tabs.map((t) => (
        <PanelSectionRow key={t.key}>
          <ToggleField label={t.label} checked={t.locked || !hiddenSet.has(t.key)} disabled={t.locked}
            onChange={(on) => {
              const next = new Set(hiddenSet);
              if (on) next.delete(t.key); else next.add(t.key);
              updateSettings({ hiddenQamTabs: [...next] }, false);
            }} />
        </PanelSectionRow>
      ))}
    </PanelSection>
  );
}

function LibraryTabsSection() {
  const st = useEngine();
  const s = st.settings;
  if (!s) return null;
  if (tabMasterInstalled()) {
    return (
      <PanelSection title="Library tabs">
        <PanelSectionRow><div style={note}>TabMaster is installed and already controls the Library tabs, so this section is off. Hide tabs in TabMaster instead.</div></PanelSectionRow>
      </PanelSection>
    );
  }
  const hiddenSet = new Set(s.hiddenLibraryTabs);
  const ids = [...new Set([...seenLibraryTabs(), ...s.hiddenLibraryTabs])];
  if (!ids.length) ids.push(...Object.keys(LIBRARY_TABS).filter((k) => ["AllGames", "Installed", "Favorites", "Collections", "DesktopApps", "Soundtracks"].includes(k)));
  const toggle = (id: string, on: boolean) => {
    const next = new Set(hiddenSet);
    if (on) next.delete(id); else next.add(id);
    updateSettings({ hiddenLibraryTabs: [...next] }, false);
  };
  return (
    <PanelSection title="Library tabs">
      {!libraryActive() && (
        <PanelSectionRow><div style={warn}>The Library patch isn't active, so Steam shows its normal tabs.</div></PanelSectionRow>
      )}
      <PanelSectionRow>
        <div style={note}>Turn a tab off to remove it from the Library. Applies the next time the Library opens. If every tab is off, Steam's tabs come back.</div>
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField label={`"${s.collectionName}" tab`} checked={s.readyLibraryTab} disabled={!s.collectionId}
          description={s.collectionId ? "Shows the collection as its own Library tab, second from the left." : "Turn on collection sync first."}
          onChange={(v) => updateSettings({ readyLibraryTab: v }, false)} />
      </PanelSectionRow>
      {ids.map((id) => (
        <PanelSectionRow key={id}>
          <ToggleField label={LIBRARY_TABS[id] ?? id} checked={!hiddenSet.has(id)} onChange={(on) => toggle(id, on)} />
        </PanelSectionRow>
      ))}
    </PanelSection>
  );
}

function Content() {
  return (
    <>
      <FilterView />
      <LibraryTabsSection />
      <QamTabsSection />
    </>
  );
}

export default definePlugin(() => {
  start();
  const qamOk = installQam({
    title: <div className={staticClasses.Title}>Hidden games</div>,
    icon: <FaEyeSlash />,
    content: <HiddenTab />,
  });
  installLibrary();
  const apply = () => {
    const s = snapshot().settings;
    if (!s) return;
    if (qamOk) setHiddenTabs(s.hiddenQamTabs);
    setLibraryConfig({
      hidden: new Set(s.hiddenLibraryTabs),
      readyTab: s.readyLibraryTab && s.collectionId && s.enabled ? { name: s.collectionName, collectionId: s.collectionId } : null,
    });
  };
  subscribe(apply);
  loadSettings().then(apply).catch(() => {});
  return {
    name: "Handheld Library",
    titleView: <div className={staticClasses.Title}>Handheld Library</div>,
    content: <Content />,
    icon: <FaFilter />,
    onDismount() { uninstallLibrary(); uninstallQam(); stop(); },
  };
});
