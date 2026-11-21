import { ButtonItem, DropdownItem, Field, Navigation, PanelSectionRow, staticClasses, TextField, ToggleField } from "@decky/ui";
import { definePlugin, routerHook } from "@decky/api";
import { useEffect, useState } from "react";
import { FaImages } from "react-icons/fa";
import { clearKey, getSettings, setKey, setOptions, Settings } from "./backend";
import { patchGameMenu } from "./menu";
import { ArtPage } from "./page";
import { sectionFactory } from "./section";
import { appInfo, focusedApp, libraryApps, runningApp } from "./steam";
import { clearPages, state } from "./state";
import { C, note, warn } from "./ui";

const Section = sectionFactory("grid-art");
const ROUTE = "/grid-art/:appid";

/** Which game the panel is about: the one picked here, else the open game page, else the running game. */
function target(): { appid: number | null; why: string } {
  const page = focusedApp();
  if (state.picked != null) return { appid: state.picked, why: "Picked" };
  if (page) return { appid: page, why: "Open page" };
  const run = runningApp();
  if (run) return { appid: run, why: "Running" };
  return { appid: null, why: "" };
}

function KeySection({ s, onSettings }: { s: Settings; onSettings: (s: Settings) => void }) {
  const [draft, setDraft] = useState("");
  const [msg, setMsg] = useState<{ text: string; bad: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await setKey(draft);
      if (!r.ok) { setMsg({ text: r.error, bad: true }); return; }
      setDraft(""); onSettings(r.settings);
      setMsg(r.checked ? { text: "Key works.", bad: false } : { text: "Saved, but SteamGridDB couldn't be reached to check it.", bad: true });
    } finally { setBusy(false); }
  };
  return (
    <Section id="key" title="API key" defaultOpen={!s.hasKey} summary={s.hasKey ? `Set ${s.keyHint}` : "Not set"}>
      {s.hasKey ? (
        <>
          <PanelSectionRow><Field label="SteamGridDB key" bottomSeparator="none">{s.keyHint || "Set"}</Field></PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={async () => { onSettings(await clearKey()); clearPages(); }}>Remove key</ButtonItem>
          </PanelSectionRow>
        </>
      ) : (
        <>
          <PanelSectionRow>
            <div style={note}>
              Artwork comes from SteamGridDB. Their API key is free: sign in at steamgriddb.com, then Preferences → API.
            </div>
          </PanelSectionRow>
          <PanelSectionRow>
            <TextField label="Paste or type the key" bIsPassword value={draft} onChange={(e) => setDraft(e.target.value)} />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy || draft.trim().length < 16} onClick={save}>{busy ? "Checking…" : "Save key"}</ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <div style={note}>Easier from Desktop Mode: put the key in ~/homebrew/settings/Grid Art/key.txt. It's picked up the next time this panel opens, and the file is removed.</div>
          </PanelSectionRow>
        </>
      )}
      {msg && <PanelSectionRow><div style={msg.bad ? warn : { ...note, color: C.ok, opacity: 1 }}>{msg.text}</div></PanelSectionRow>}
    </Section>
  );
}

function FilterSection({ s, onSettings }: { s: Settings; onSettings: (s: Settings) => void }) {
  const set = async (patch: Partial<Settings>) => { onSettings(await setOptions(patch)); clearPages(); };
  const on = [s.animated && "animated", s.nsfw && "adult", s.humor && "humor", s.epilepsy && "flashing"].filter(Boolean);
  return (
    <Section id="filters" title="Filters" summary={on.length ? `Showing ${on.join(", ")}` : "Static, safe only"}>
      <PanelSectionRow>
        <ToggleField label="Animated art" description="Animated PNGs instead of still images." checked={s.animated} onChange={(v) => set({ animated: v })} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField label="Humor" checked={s.humor} onChange={(v) => set({ humor: v })} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField label="Flashing images" description="Art tagged as an epilepsy risk." checked={s.epilepsy} onChange={(v) => set({ epilepsy: v })} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField label="Adult content" checked={s.nsfw} onChange={(v) => set({ nsfw: v })} />
      </PanelSectionRow>
    </Section>
  );
}

function Content() {
  const [s, setS] = useState<Settings | null>(state.settings);
  const [, force] = useState(0);
  useEffect(() => { getSettings().then((v) => { state.settings = v; setS(v); }).catch(() => {}); }, []);
  const onSettings = (v: Settings) => { state.settings = v; setS(v); };

  const t = target();
  const app = t.appid != null ? appInfo(t.appid) : null;
  const games = libraryApps();
  const options = [...games];
  if (app && !options.some((g) => g.appid === app.appid)) options.unshift(app);

  const open = () => {
    if (!app) return;
    Navigation.CloseSideMenus();
    Navigation.Navigate(`/grid-art/${app.appid}`);
  };

  return (
    <>
      <Section id="game" title={t.why ? `Game · ${t.why}` : "Game"} collapsible={false}>
        <PanelSectionRow>
          <DropdownItem label="" selectedOption={app?.appid ?? null} strDefaultLabel="Pick a game"
            rgOptions={options.map((g) => ({ data: g.appid, label: g.shortcut ? `${g.name} · shortcut` : g.name }))}
            onChange={(o) => { state.picked = o.data as number; force((n) => n + 1); }} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={!app || !s?.hasKey} onClick={open}>Change artwork</ButtonItem>
        </PanelSectionRow>
        {state.picked != null && (
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => { state.picked = null; force((n) => n + 1); }}>Follow the open game page</ButtonItem>
          </PanelSectionRow>
        )}
        {s && !s.hasKey && <PanelSectionRow><div style={warn}>Add a SteamGridDB API key below first.</div></PanelSectionRow>}
      </Section>
      {s && <KeySection s={s} onSettings={onSettings} />}
      {s && <FilterSection s={s} onSettings={onSettings} />}
      <Section id="about" title="About" summary="SteamGridDB artwork for Steam">
        <PanelSectionRow>
          <div style={note}>
            Sets capsule, wide capsule, hero, logo and the small game icon through Steam's own custom
            artwork feature, so it stays even without this plugin. Pick Change artwork… in a game's menu (between Manage and Properties), or open a game's page and come here.
            Reset in the browser puts Steam's art back. Nothing runs in the background.
          </div>
        </PanelSectionRow>
      </Section>
    </>
  );
}

export default definePlugin(() => {
  routerHook.addRoute(ROUTE, ArtPage, { exact: true });
  const menu = patchGameMenu();
  return {
    name: "Grid Art",
    titleView: <div className={staticClasses.Title}>Grid Art</div>,
    content: <Content />,
    icon: <FaImages />,
    onDismount() { menu.unpatch(); routerHook.removeRoute(ROUTE); },
  };
});
