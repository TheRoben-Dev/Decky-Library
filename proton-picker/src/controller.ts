// Proton Picker brain: library sweep (auto-assign), manual picks, rollback,
// crash-on-launch rollback, and keeping custom Proton builds installed.
import { toaster } from "@decky/api";
import * as be from "./backend";
import * as steam from "./steam";
import { cmpVersion, familyOf, newestOf, recommend, Recommendation } from "./recommend";
import {
  clone, DEFAULT_SETTINGS, DiskTool, Family, GameInfo, GameRecord, InstallState, newRecord,
  ProtonDBSummary, Release, Settings, SteamTool,
} from "./types";

const QUICK_EXIT_MS = 45_000;   // closed this fast on a new build -> treat as broken
const VERIFIED_MS = 120_000;    // ran this long -> build works for this game
const HISTORY_MAX = 10;
const FAMILIES: Family[] = ["ge", "cachyos"];
export const FAMILY_LABEL: Record<Family, string> = { ge: "GE-Proton", cachyos: "Proton-CachyOS" };

type Listener = () => void;

class Controller {
  settings: Settings = clone(DEFAULT_SETTINGS);
  installedTags: Partial<Record<Family, string>> = {};
  steamTools: SteamTool[] = [];
  diskTools: DiskTool[] = [];
  releases: Partial<Record<Family, Release>> = {};
  install: InstallState = { phase: "idle" };
  pdb: Record<string, ProtonDBSummary | null | "error"> = {};
  infos: Record<string, GameInfo> = {};
  selected: string | null = null;
  sweeping = false;
  sweepNote = "";
  private listeners = new Set<Listener>();
  private starts: Record<string, number> = {};
  private unsubs: (() => void)[] = [];
  private timers: number[] = [];
  private installPoll?: number;
  private saveTimer?: number;

  subscribe(l: Listener) {
    this.listeners.add(l);
    return () => { this.listeners.delete(l); };
  }
  emit() { this.listeners.forEach((l) => l()); }

  // ------------------------------------------------------------------ lifecycle
  async start() {
    const saved: any = await be.getSettings().catch(() => ({}));
    this.settings = { ...clone(DEFAULT_SETTINGS), ...saved, games: saved?.games ?? {} };
    this.installedTags = saved?.installedTags ?? {};
    await this.refreshTools();
    this.unsubs.push(steam.onLifetime((id, running) => this.onLifetime(id, running)));
    // Let Steam finish loading the library before the first sweep.
    this.timers.push(window.setTimeout(() => this.background(), 8000));
    this.timers.push(window.setInterval(() => this.background(), 6 * 3600_000));
    const st = await be.installState().catch(() => null);
    if (st && ["starting", "downloading", "verifying", "extracting"].includes(st.phase)) this.pollInstall();
  }

  stop() {
    this.unsubs.forEach((u) => u());
    this.timers.forEach((t) => { clearTimeout(t); clearInterval(t); });
    if (this.installPoll) clearInterval(this.installPoll);
  }

  private async background() {
    await this.refreshReleases();
    await this.autoInstall();
    await this.sweep();
  }

  private save() {
    if (this.saveTimer) clearTimeout(this.saveTimer);
    this.saveTimer = window.setTimeout(() => {
      be.saveSettings({ ...this.settings, installedTags: this.installedTags } as any).catch(() => {});
    }, 300);
  }

  setOption<K extends keyof Settings>(k: K, v: Settings[K]) {
    this.settings[k] = v;
    this.save();
    this.emit();
    if (k === "autoManage" && v) this.sweep(true);
    if (k === "preferredFamily" || k === "autoInstall") this.background();
  }

  // ------------------------------------------------------------------ tools
  async refreshTools() {
    const [steamTools, disk] = await Promise.all([
      steam.globalTools(),
      be.listTools().catch(() => ({ tools: [] as DiskTool[], compatDir: "" })),
    ]);
    this.steamTools = steamTools;
    this.diskTools = disk.tools;
    this.emit();
  }

  /** Installed on disk but Steam hasn't loaded them yet (needs a Steam restart). */
  pendingRestart(): DiskTool[] {
    const known = new Set(this.steamTools.map((t) => t.name));
    return this.steamTools.length ? this.diskTools.filter((t) => !known.has(t.name)) : [];
  }

  async refreshReleases(force = false) {
    await Promise.all(FAMILIES.map(async (f) => {
      const r = await be.latestRelease(f, force).catch((e) => ({ ok: false, error: String(e) } as Release));
      if (r.ok || !this.releases[f]) this.releases[f] = r;
    }));
    this.emit();
  }

  /** Is the latest release of this family already on disk? */
  hasLatest(f: Family): boolean {
    const tag = this.releases[f]?.tag;
    if (!tag) return false;
    if (this.installedTags[f] === tag) return true;
    const core = tag.replace(/^cachyos-/, "");
    return this.diskTools.some((t) => t.name === tag || t.name.includes(core) || t.display.includes(core));
  }

  hasAny(f: Family): boolean {
    return this.diskTools.some((t) => t.family === f);
  }

  private async autoInstall() {
    if (!this.settings.autoInstall || steam.runningAppId()) return;
    const f = this.settings.preferredFamily;
    const rel = this.releases[f];
    if (!rel?.ok || !rel.asset || this.hasLatest(f) || this.install.phase === "downloading") return;
    // Install when missing, or when there's a newer build and auto-update is on.
    if (!this.hasAny(f) || this.settings.autoUpdate) await this.installFamily(f, true);
  }

  async installFamily(f: Family, auto = false) {
    const r = await be.install(f);
    if (!r.ok) {
      if (!auto) toaster.toast({ title: "Proton Picker", body: r.error ?? "Install failed to start" });
      return;
    }
    this.install = { phase: "starting", family: f };
    this.emit();
    this.pollInstall();
  }

  private pollInstall() {
    if (this.installPoll) clearInterval(this.installPoll);
    this.installPoll = window.setInterval(async () => {
      const st = await be.installState().catch(() => null);
      if (!st) return;
      this.install = st;
      this.emit();
      if (st.phase === "done" || st.phase === "error") {
        clearInterval(this.installPoll);
        this.installPoll = undefined;
        if (st.phase === "done") {
          if (st.family && st.tag) this.installedTags[st.family] = st.tag;
          this.save();
          await this.refreshTools();
          toaster.toast({
            title: `${st.display ?? st.tool} installed`,
            body: this.pendingRestart().length ? "Steam loads it on its next start. Games switch over automatically." : "Ready to use.",
          });
          this.sweep(true);
        } else {
          toaster.toast({ title: "Proton install failed", body: st.error ?? "unknown error" });
        }
      }
    }, 700);
  }

  /** Remove builds we installed that are outdated and not used or kept for rollback by any game. */
  async removeOldBuilds(): Promise<number> {
    const used = new Set<string>();
    Object.values(this.infos).forEach((i) => i.currentTool && used.add(i.currentTool));
    Object.values(this.settings.games).forEach((r) => {
      if (r.setByUs) used.add(r.setByUs);
      r.history.forEach((h) => h && used.add(h));
    });
    let n = 0;
    for (const t of this.diskTools) {
      if (!t.owned || used.has(t.name)) continue;
      const newest = this.diskTools
        .filter((x) => x.family === t.family)
        .sort((a, b) => cmpVersion(b.name, a.name))[0];
      if (newest?.name === t.name) continue;
      const r = await be.removeTool(t.name);
      if (r.ok) n++;
    }
    await this.refreshTools();
    return n;
  }

  // ------------------------------------------------------------------ games
  record(appid: string): GameRecord {
    return this.settings.games[appid] ?? newRecord();
  }

  private putRecord(appid: string, rec: GameRecord) {
    this.settings.games[appid] = rec;
    this.save();
  }

  async loadGame(appid: string, forcePdb = false) {
    const [info, pdb] = await Promise.all([
      steam.gameInfo(appid),
      be.protondbSummaries([appid], forcePdb).catch(() => ({} as Record<string, any>)),
    ]);
    if (info) this.infos[appid] = info;
    if (appid in pdb) this.pdb[appid] = pdb[appid];
    this.emit();
    return info;
  }

  recommendationFor(appid: string): Recommendation | null {
    const info = this.infos[appid];
    if (!info) return null;
    const p = this.pdb[appid];
    return recommend(info, p === "error" ? null : p, this.steamTools, this.settings.preferredFamily);
  }

  /** Did someone set this game's tool outside Proton Picker (Steam Properties, another tool)? */
  setElsewhere(appid: string): boolean {
    const info = this.infos[appid];
    if (!info?.currentTool) return false;
    return info.currentPriority >= steam.USER_PRIORITY && info.currentTool !== this.record(appid).setByUs;
  }

  private applyTool(appid: string, tool: string, rec: GameRecord, note: string): boolean {
    const info = this.infos[appid];
    const current = info?.currentTool ?? "";
    if (current === tool) {
      rec.setByUs = tool;
      this.putRecord(appid, rec);
      return false;
    }
    if (!steam.specifyTool(appid, tool)) return false;
    rec.history = [...rec.history, current].slice(-HISTORY_MAX);
    rec.setByUs = tool;
    rec.verified = false;
    rec.changedAt = Date.now();
    rec.note = note;
    if (info) { info.currentTool = tool; info.currentPriority = steam.USER_PRIORITY; }
    this.putRecord(appid, rec);
    be.log(`app ${appid}: ${current || "default"} -> ${tool || "default"} (${note})`);
    return true;
  }

  /** User choice from the panel: "auto" | "default" | "off" | <tool name>. */
  async choose(appid: string, choice: string) {
    const rec = this.record(appid);
    if (choice === "off") {
      rec.mode = "off";
      this.putRecord(appid, rec);
    } else if (choice === "auto") {
      rec.mode = "auto";
      this.putRecord(appid, rec);
      await this.evaluate(appid, true);
    } else {
      rec.mode = "pinned";
      this.applyTool(appid, choice === "default" ? "" : choice, rec, "picked by you");
    }
    this.emit();
  }

  async rollback(appid: string, why = "rolled back") {
    const rec = this.record(appid);
    if (!rec.history.length) return;
    const prev = rec.history[rec.history.length - 1];
    if (!steam.specifyTool(appid, prev)) return;
    rec.history = rec.history.slice(0, -1);
    rec.setByUs = prev;
    rec.mode = "pinned"; // don't let the sweep flip it straight back
    rec.verified = true;
    rec.changedAt = Date.now();
    rec.note = why;
    const info = this.infos[appid];
    if (info) { info.currentTool = prev; info.currentPriority = prev ? steam.USER_PRIORITY : 0; }
    this.putRecord(appid, rec);
    be.log(`app ${appid}: ${why} -> ${prev || "default"}`);
    this.emit();
  }

  /** Auto-mode decision for one game. Returns true if its tool changed. */
  private async evaluate(appid: string, explicit = false): Promise<boolean> {
    const info = this.infos[appid] ?? (await this.loadGame(appid));
    if (!info) return false;
    const rec = this.record(appid);
    if (rec.mode !== "auto") return false;
    if (!explicit && this.setElsewhere(appid)) return false; // respect the user's own Steam setting
    // ProtonDB unreachable: don't guess for the whole library, try again on the next check.
    if (!explicit && (this.pdb[appid] === "error" || !(appid in this.pdb))) return false;
    const r = this.recommendationFor(appid);
    if (!r) return false;
    if (r.tool === null) {
      // Leave Steam's default alone; only undo our own pick when the user asks for Auto explicitly.
      if (explicit && rec.setByUs) return this.applyTool(appid, "", rec, r.reason);
      return false;
    }
    const current = info.currentTool;
    if (current === r.tool) return false;
    const ours = !current || current === rec.setByUs || explicit;
    if (!ours) return false;
    // Moving a game we already set to a newer/different build is the "auto-update" part.
    if (current && !explicit && !this.settings.autoUpdate) return false;
    return this.applyTool(appid, r.tool, rec, r.reason);
  }

  /** Go through installed games and apply the auto choice where it's ours to make. */
  async sweep(force = false) {
    // force: run even if a check ran recently (kept for callers; auto-manage must be on).
    void force;
    if (this.sweeping || !this.settings.autoManage) return;
    this.sweeping = true;
    this.sweepNote = "Checking library…";
    this.emit();
    let changed = 0;
    const changedNames: string[] = [];
    try {
      this.steamTools = await steam.globalTools();
      const running = steam.runningAppId();
      const games = steam.installedGames().filter((g) => g.appid !== running);
      const ids = games.map((g) => g.appid);
      for (let i = 0; i < ids.length; i += 25) {
        const chunk = ids.slice(i, i + 25);
        const res = await be.protondbSummaries(chunk, false).catch(() => ({} as Record<string, any>));
        Object.assign(this.pdb, res);
        this.sweepNote = `Checking ratings… ${Math.min(i + 25, ids.length)}/${ids.length}`;
        this.emit();
      }
      for (const g of games) {
        const info = await steam.gameInfo(g.appid);
        if (!info) continue;
        this.infos[g.appid] = info;
        if (await this.evaluate(g.appid)) {
          changed++;
          changedNames.push(info.name);
        }
      }
      this.sweepNote = `Last check ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}: ${games.length} games, ${changed} changed`;
      if (changed) {
        toaster.toast({
          title: `Proton Picker set ${changed} game${changed > 1 ? "s" : ""}`,
          body: changedNames.slice(0, 3).join(", ") + (changed > 3 ? "…" : ""),
        });
      }
    } catch (e) {
      this.sweepNote = `Check failed: ${e}`;
    } finally {
      this.sweeping = false;
      this.emit();
    }
  }

  // ------------------------------------------------------------------ crash rollback
  private onLifetime(appid: string, running: boolean) {
    if (running) {
      this.starts[appid] = Date.now();
      return;
    }
    const started = this.starts[appid];
    delete this.starts[appid];
    const rec = this.settings.games[appid];
    if (started && rec && !rec.verified) {
      const dur = Date.now() - started;
      if (dur < QUICK_EXIT_MS && this.settings.autoRollback && rec.history.length) {
        const prev = rec.history[rec.history.length - 1];
        const name = this.infos[appid]?.name ?? `App ${appid}`;
        this.rollback(appid, `closed after ${Math.round(dur / 1000)}s, rolled back`);
        toaster.toast({
          title: `${name} closed right after launch`,
          body: `Rolled back to ${prev || "Steam default"}. Change it in Proton Picker if that wasn't a crash.`,
        });
      } else if (dur >= VERIFIED_MS) {
        rec.verified = true;
        this.putRecord(appid, rec);
      }
    }
    // A game just closed: good moment for pending installs.
    window.setTimeout(() => this.autoInstall(), 5000);
  }

  // ------------------------------------------------------------------ helpers for UI
  displayName(tool: string): string {
    if (!tool) return "Steam default";
    return this.steamTools.find((t) => t.name === tool)?.display ?? this.diskTools.find((t) => t.name === tool)?.display ?? tool;
  }

  newestInstalled(f: Family) {
    return newestOf(f, this.steamTools) ?? newestOf(f, this.diskTools.map((t) => ({ name: t.name, display: t.display })));
  }
}

export { familyOf };
export const controller = new Controller();
