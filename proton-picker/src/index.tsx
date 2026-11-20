import {
  ButtonItem,
  DropdownItem,
  Field,
  PanelSection,
  PanelSectionRow,
  ProgressBarWithInfo,
  ToggleField,
  staticClasses,
} from "@decky/ui";
import { definePlugin, toaster } from "@decky/api";
import { useEffect, useReducer, useState } from "react";
import { FaFlask } from "react-icons/fa";
import { controller, FAMILY_LABEL } from "./controller";
import { effectiveTier, TIER_COLOR } from "./recommend";
import * as steam from "./steam";
import { Family } from "./types";

const note = { fontSize: "12px", lineHeight: "16px", opacity: 0.75, whiteSpace: "normal" as const };
const warn = { ...note, color: "#ffb84d", opacity: 1 };
const DECK = ["Unknown", "Unsupported", "Playable", "Verified"];

function useController() {
  const [, force] = useReducer((x: number) => x + 1, 0);
  useEffect(() => controller.subscribe(force), []);
  return controller;
}

function Note({ children, warning }: { children: any; warning?: boolean }) {
  return (
    <PanelSectionRow>
      <div style={warning ? warn : note}>{children}</div>
    </PanelSectionRow>
  );
}

function TierBadge({ tier }: { tier: string | null }) {
  const t = tier ?? "pending";
  return (
    <span style={{
      background: TIER_COLOR[t] ?? TIER_COLOR.pending, color: "#111", borderRadius: 4,
      padding: "1px 6px", fontSize: 11, fontWeight: 700, textTransform: "uppercase",
    }}>
      {tier ?? "no rating"}
    </span>
  );
}

function GameSection() {
  const c = useController();
  const running = steam.runningAppId();
  const games = steam.installedGames();
  const [appid, setAppid] = useState<string | null>(c.selected ?? running ?? games[0]?.appid ?? null);

  useEffect(() => {
    if (!appid) return;
    c.selected = appid;
    c.loadGame(appid);
  }, [appid]);

  const recent = games.slice(0, 40);
  if (appid && !recent.some((g) => g.appid === appid)) {
    const info = c.infos[appid];
    recent.unshift({ appid, name: info?.name ?? `App ${appid}`, lastPlayed: 0, deckCategory: 0 });
  }

  const info = appid ? c.infos[appid] : undefined;
  const rec = appid ? c.record(appid) : null;
  const pdb = appid ? c.pdb[appid] : undefined;
  const tier = pdb && pdb !== "error" ? effectiveTier(pdb) : null;
  const r = appid ? c.recommendationFor(appid) : null;
  const elsewhere = appid ? c.setElsewhere(appid) : false;

  const options = [
    { data: "auto", label: `Auto${r ? ` (${r.display})` : ""}` },
    { data: "default", label: "Steam default" },
    ...c.steamTools.map((t) => ({ data: t.name, label: t.display })),
    { data: "off", label: "Hands off (don't touch)" },
  ];
  const selectedOpt = !rec ? "auto"
    : rec.mode === "auto" ? "auto"
    : rec.mode === "off" ? "off"
    : (rec.setByUs ?? "") === "" ? "default" : rec.setByUs!;
  const prev = rec?.history.length ? rec.history[rec.history.length - 1] : null;

  return (
    <PanelSection title="Game">
      <PanelSectionRow>
        <DropdownItem
          label={running === appid ? "Running now" : "Game"}
          rgOptions={recent.map((g) => ({ data: g.appid, label: g.name }))}
          selectedOption={appid}
          onChange={(o) => setAppid(String(o.data))}
        />
      </PanelSectionRow>
      {!appid && <Note>No installed games found.</Note>}
      {info && (
        <>
          <PanelSectionRow>
            <Field label="ProtonDB" bottomSeparator="none">
              <TierBadge tier={tier} />
              {pdb && pdb !== "error" && pdb.total ? <span style={{ ...note, marginLeft: 6 }}>{pdb.total} reports</span> : null}
            </Field>
          </PanelSectionRow>
          {pdb === "error" && <Note warning>Couldn't reach ProtonDB. Using Steam Deck rating only.</Note>}
          <PanelSectionRow>
            <Field label="Steam Deck" bottomSeparator="none">{info.native ? "Native Linux" : DECK[info.deckCategory] ?? "Unknown"}</Field>
          </PanelSectionRow>
          <PanelSectionRow>
            <Field label="Uses now" bottomSeparator="none">{c.displayName(info.currentTool)}</Field>
          </PanelSectionRow>
          <PanelSectionRow>
            <DropdownItem
              label="Proton version"
              rgOptions={options}
              selectedOption={selectedOpt}
              onChange={async (o) => {
                await c.choose(info.appid, String(o.data));
                if (running === info.appid) toaster.toast({ title: "Proton Picker", body: "Takes effect next time the game starts." });
              }}
            />
          </PanelSectionRow>
          {r && <Note>Auto pick: {r.display}. {r.reason}.</Note>}
          {elsewhere && rec?.mode === "auto" && (
            <Note warning>Set in Steam's own Properties, so Auto leaves it alone. Pick Auto again here to hand it over.</Note>
          )}
          {r?.wantsFamily && !c.hasAny(r.wantsFamily) && (
            <Note warning>{FAMILY_LABEL[r.wantsFamily]} isn't installed yet. {c.settings.autoInstall ? "It will install automatically." : "Install it below."}</Note>
          )}
          {rec?.note && <Note>Last change: {rec.note}{rec.verified ? "" : " (not played long enough yet to confirm it works)"}.</Note>}
          {prev !== null && (
            <PanelSectionRow>
              <ButtonItem layout="below" onClick={() => c.rollback(info.appid, "rolled back by you")}>
                Roll back to {c.displayName(prev)}
              </ButtonItem>
            </PanelSectionRow>
          )}
        </>
      )}
    </PanelSection>
  );
}

function BuildsSection() {
  const c = useController();
  const ins = c.install;
  const busy = ["starting", "downloading", "verifying", "extracting"].includes(ins.phase);
  const pending = c.pendingRestart();
  const gb = (b?: number) => ((b ?? 0) / 1e9).toFixed(2);

  return (
    <PanelSection title="Proton builds">
      {(["ge", "cachyos"] as Family[]).map((f) => {
        const rel = c.releases[f];
        const newest = c.newestInstalled(f);
        const latest = c.hasLatest(f);
        return (
          <PanelSectionRow key={f}>
            <Field label={FAMILY_LABEL[f]} description={
              <span style={note}>
                Installed: {newest?.display ?? "none"}
                {rel?.ok && rel.tag ? <><br />Latest: {rel.tag}</> : rel && !rel.ok ? <><br />Couldn't check GitHub</> : null}
              </span>
            } bottomSeparator="none" />
            {rel?.ok && rel.asset && !latest && (
              <ButtonItem layout="below" disabled={busy} onClick={() => c.installFamily(f)}>
                Install {rel.tag}
              </ButtonItem>
            )}
          </PanelSectionRow>
        );
      })}
      {busy && (
        <PanelSectionRow>
          <ProgressBarWithInfo
            nProgress={ins.total ? ((ins.done_bytes ?? 0) / ins.total) * 100 : undefined}
            indeterminate={!ins.total || ins.phase !== "downloading"}
            sOperationText={`${ins.phase === "downloading" ? "Downloading" : ins.phase === "verifying" ? "Verifying" : ins.phase === "extracting" ? "Unpacking" : "Starting"} ${ins.tag ?? ""}`}
            sTimeRemaining={ins.phase === "downloading" && ins.total ? `${gb(ins.done_bytes)} / ${gb(ins.total)} GB` : ""}
          />
        </PanelSectionRow>
      )}
      {ins.phase === "error" && <Note warning>Install failed: {ins.error}</Note>}
      {pending.length > 0 && (
        <>
          <Note warning>
            Steam hasn't loaded {pending.map((t) => t.display).join(", ")} yet. It does on its next start, and games switch
            over automatically then.
          </Note>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={!!steam.runningAppId()} onClick={() => steam.restartSteam()}>
              Restart Steam now
            </ButtonItem>
          </PanelSectionRow>
        </>
      )}
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={async () => {
          await c.refreshTools();
          await c.refreshReleases(true);
        }}>
          Check for new builds
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={async () => {
          const n = await c.removeOldBuilds();
          toaster.toast({ title: "Proton Picker", body: n ? `Removed ${n} old build${n > 1 ? "s" : ""}` : "Nothing to remove" });
        }}>
          Remove unused old builds
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

function AutomationSection() {
  const c = useController();
  const s = c.settings;
  return (
    <PanelSection title="Automation">
      <PanelSectionRow>
        <ToggleField label="Auto-pick for my library" checked={s.autoManage}
          description="Games rated below Platinum and not Deck Verified get the newest custom Proton. Never overrides a version you set in Steam."
          onChange={(v) => c.setOption("autoManage", v)} />
      </PanelSectionRow>
      <PanelSectionRow>
        <DropdownItem label="Preferred custom build"
          rgOptions={[{ data: "ge", label: "GE-Proton" }, { data: "cachyos", label: "Proton-CachyOS" }]}
          selectedOption={s.preferredFamily}
          onChange={(o) => c.setOption("preferredFamily", o.data as Family)} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField label="Install builds automatically" checked={s.autoInstall}
          description="Downloads the preferred build when it's missing or outdated, only while no game is running."
          onChange={(v) => c.setOption("autoInstall", v)} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField label="Move auto games to new builds" checked={s.autoUpdate}
          onChange={(v) => c.setOption("autoUpdate", v)} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField label="Roll back if a game crashes on launch" checked={s.autoRollback}
          description="If a game closes within 45 s on a build it hasn't run on before, go back to the previous one."
          onChange={(v) => c.setOption("autoRollback", v)} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={c.sweeping || !s.autoManage} onClick={() => c.sweep(true)}>
          {c.sweeping ? "Checking…" : "Check library now"}
        </ButtonItem>
      </PanelSectionRow>
      {c.sweepNote && <Note>{c.sweepNote}</Note>}
    </PanelSection>
  );
}

function Content() {
  useEffect(() => { controller.refreshTools(); }, []);
  return (
    <>
      <GameSection />
      <BuildsSection />
      <AutomationSection />
    </>
  );
}

export default definePlugin(() => {
  controller.start();
  return {
    name: "Proton Picker",
    titleView: <div className={staticClasses.Title}>Proton Picker</div>,
    content: <Content />,
    icon: <FaFlask />,
    onDismount() {
      controller.stop();
    },
  };
});
