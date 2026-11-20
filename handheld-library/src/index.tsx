import {
  ButtonItem, ConfirmModal, DialogButton, DropdownItem, Field, Focusable, Navigation, PanelSection,
  PanelSectionRow, showModal, staticClasses, TextField, ToggleField,
} from "@decky/ui";
import { definePlugin, toaster } from "@decky/api";
import { useEffect, useMemo, useState } from "react";
import { FaFilter } from "react-icons/fa";
import { deleteCollection, Game, hiddenGames, isHidden, launch, unhide } from "./steam";
import { snapshot, start, stop, subscribe, sync, updateSettings } from "./engine";

const note = { fontSize: "12px", lineHeight: "16px", opacity: 0.75, whiteSpace: "normal" as const };
const warn = { ...note, color: "#FF9F1C", opacity: 1 };
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

function GameRow({ g, desc, actions }: { g: Game; desc: string; actions: { label: string; onClick: () => void }[] }) {
  return (
    <PanelSectionRow>
      <Field label={g.name} description={desc} bottomSeparator="standard" padding="none"
        childrenLayout="below" focusable={false}>
        <Focusable style={{ display: "flex", gap: "6px", marginTop: "4px" }} flow-children="horizontal">
          {actions.map((a) => (
            <DialogButton key={a.label} style={{ minWidth: 0, flex: 1, padding: "6px 8px", fontSize: "13px" }}
              onClick={a.onClick}>{a.label}</DialogButton>
          ))}
        </Focusable>
      </Field>
    </PanelSectionRow>
  );
}

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

function HiddenView() {
  const [games, setGames] = useState<Game[]>(() => hiddenGames());
  const refresh = () => setGames(hiddenGames());

  const doUnhide = (ids: number[]) => {
    try { unhide(ids); } catch (e) { toaster.toast({ title: "Handheld Library", body: `Couldn't unhide: ${e}` }); }
    // Steam updates the hidden collection asynchronously.
    setTimeout(refresh, 300);
  };

  return (
    <PanelSection title={`Hidden games (${games.length})`}>
      {games.length === 0 && <PanelSectionRow><div style={note}>Nothing is hidden.</div></PanelSectionRow>}
      {games.map((g) => (
        <GameRow key={g.appid} g={g} desc={g.installed ? "Installed" : "Not installed"}
          actions={[
            { label: g.installed ? "Play" : "Install", onClick: () => { Navigation.CloseSideMenus(); launch(g); } },
            { label: "Unhide", onClick: () => doUnhide([g.appid]) },
            { label: "Page", onClick: () => openPage(g.appid) },
          ]} />
      ))}
      {games.length > 1 && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={async () => {
            if (await confirm("Unhide all?", `Shows all ${games.length} hidden games in your library again.`, "Unhide all")) {
              doUnhide(games.map((g) => g.appid));
            }
          }}>Unhide all</ButtonItem>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}

let lastTab: "filter" | "hidden" = "filter";

function Content() {
  const [tab, setTab] = useState(lastTab);
  const pick = (t: typeof tab) => { lastTab = t; setTab(t); };
  const tabBtn = (t: typeof tab, label: string) => (
    <DialogButton style={{ minWidth: 0, flex: 1, padding: "6px", opacity: tab === t ? 1 : 0.55,
      borderBottom: tab === t ? "2px solid currentColor" : "2px solid transparent" }}
      onClick={() => pick(t)}>{label}</DialogButton>
  );
  return (
    <>
      <PanelSection>
        <PanelSectionRow>
          <Focusable style={{ display: "flex", gap: "6px" }} flow-children="horizontal">
            {tabBtn("filter", "Handheld Ready")}
            {tabBtn("hidden", "Hidden")}
          </Focusable>
        </PanelSectionRow>
      </PanelSection>
      {tab === "filter" ? <FilterView /> : <HiddenView />}
    </>
  );
}

export default definePlugin(() => {
  start();
  return {
    name: "Handheld Library",
    titleView: <div className={staticClasses.Title}>Handheld Library</div>,
    content: <Content />,
    icon: <FaFilter />,
    onDismount() { stop(); },
  };
});
