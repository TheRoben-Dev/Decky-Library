// Keeps settings, watches the running game and applies its profile.
import { toaster } from "@decky/api";
import * as be from "./backend";
import * as steam from "./steam";
import { clone, DEFAULT_SETTINGS, Environment, normalizeProfile, PowerBackend, Profile, Settings } from "./types";

type Listener = () => void;

class Controller {
  settings: Settings = clone(DEFAULT_SETTINGS);
  env: Environment | null = null;
  app: steam.RunningApp | null = null;
  lastApplied = "";
  private listeners = new Set<Listener>();
  private pollId?: number;
  private saveTimer?: number;
  private applyTimer?: number;

  subscribe(l: Listener) {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  }
  private emit() {
    this.listeners.forEach((l) => l());
  }

  async start() {
    const saved = await be.getSettings().catch(() => ({}));
    const profiles: Record<string, Profile> = {};
    for (const [k, v] of Object.entries((saved as any).profiles ?? {})) profiles[k] = normalizeProfile(v as Profile);
    if (!profiles.default) profiles.default = normalizeProfile(undefined, "Default");
    this.settings = { ...clone(DEFAULT_SETTINGS), ...(saved as Partial<Settings>), profiles, launch: (saved as any).launch ?? {} };
    steam.perfStore(); // Steam creates the store lazily; touch it early
    await this.refreshEnv();
    this.pollId = window.setInterval(() => this.tick(), 1500);
    this.tick();
  }

  stop() {
    if (this.pollId) clearInterval(this.pollId);
  }

  async refreshEnv() {
    try {
      this.env = await be.getEnvironment();
    } catch (e) {
      console.warn("[Vex] env failed", e);
    }
    this.emit();
  }

  private tick() {
    const app = steam.runningApp();
    const id = app?.appid ?? "";
    if (id === (this.app?.appid ?? "")) return;
    this.app = app;
    this.emit();
    if (!this.settings.autoApply) return;
    if (app) this.applyCurrent(true);
    else this.onNoGame();
  }

  /** Which TDP path to use. "auto" prefers Steam's own slider (Bazzite 44+ routes it
   *  through steamos-manager/PowerStation), then PowerStation directly, then sysfs.
   *  Handheld Daemon (retired in Bazzite 44) is only used when picked by hand. */
  resolvedBackend(): PowerBackend {
    const b = this.settings.powerBackend;
    if (b !== "auto") return b;
    const env = this.env;
    if (env?.conflicts.plugins.some((p) => /TDP/.test(p.controls))) return "off";
    if (steam.getLimits().tdpMax > 0) return "steam";
    if (env?.powerstation.running && !env.powerstation.tdpUnsupported) return "powerstation";
    if (env?.hhd.running) return "off"; // legacy HHD owns the hardware; don't fight it
    if (env?.power.sysfsTdp) return "sysfs";
    return "off";
  }

  profileKeyFor(appid?: string) {
    return appid && this.settings.profiles[appid] ? appid : "default";
  }
  activeProfile(): Profile {
    return this.settings.profiles[this.profileKeyFor(this.app?.appid)];
  }

  async applyCurrent(launch = false) {
    const app = this.app;
    if (!app) return;
    const p = this.activeProfile();
    const backend = this.resolvedBackend();
    const parts: string[] = [];
    try {
      parts.push(...(await steam.applySteamPerf(p, { steamTdp: backend === "steam" })));
    } catch (e) {
      parts.push("Steam perf failed");
      be.log(`steam perf error ${e}`);
    }
    if (backend !== "off") {
      const r = await be.applyPower(backend, p.power.tdpEnabled, p.power.tdp, p.power.gpuMode, p.power.gpuMin, p.power.gpuMax).catch((e) => ({ error: String(e) } as any));
      if (backend !== "steam" && p.power.tdpEnabled && r?.tdp === "ok") parts.push(`${p.power.tdp} W`);
      if (p.power.gpuMode !== "auto" && r?.gpu === "ok") parts.push(`GPU ${p.power.gpuMode === "max" ? "≤" : ""}${p.power.gpuMax} MHz`);
      if (r?.error) be.log(`power error ${r.error}`);
    }
    // Render resolution only affects the next launch; set it now so it's ready.
    if (p.scaling.enabled && p.scaling.resolution) steam.setResolution(app.appid, p.scaling.resolution);
    this.lastApplied = parts.join(" · ");
    this.emit();
    if (launch && parts.length) {
      toaster.toast({ title: `Vex: ${this.profileKeyFor(app.appid) === "default" ? "Default" : "Game"} profile`, body: this.lastApplied });
    }
  }

  private async onNoGame() {
    const backend = this.resolvedBackend();
    if (backend !== "off") await be.resetPower(backend).catch(() => {});
    this.lastApplied = "";
    this.emit();
  }

  // ---------- editing ----------
  private persist() {
    clearTimeout(this.saveTimer);
    this.saveTimer = window.setTimeout(() => be.saveSettings(this.settings), 400);
  }

  updateSettings(patch: Partial<Settings>) {
    this.settings = { ...this.settings, ...patch };
    this.persist();
    this.emit();
  }

  createGameProfile() {
    if (!this.app) return;
    const p = clone(this.settings.profiles.default);
    p.name = this.app.name;
    this.settings.profiles = { ...this.settings.profiles, [this.app.appid]: p };
    this.persist();
    this.emit();
  }

  async deleteGameProfile() {
    const app = this.app;
    if (!app || !this.settings.profiles[app.appid]) return;
    const old = this.settings.profiles[app.appid];
    if (old.fg.enabled) await this.setFrameGen(app.appid, { ...old, fg: { ...old.fg, enabled: false } });
    const { [app.appid]: _, ...rest } = this.settings.profiles;
    this.settings.profiles = rest;
    this.persist();
    this.emit();
    this.scheduleApply();
  }

  /** Edit the profile currently shown (game profile if it exists, else Default). */
  editActive(mut: (p: Profile) => void) {
    const key = this.profileKeyFor(this.app?.appid);
    const before = this.settings.profiles[key];
    const p = clone(before);
    mut(p);
    this.settings.profiles = { ...this.settings.profiles, [key]: p };
    this.persist();
    this.emit();
    if (this.app) {
      if (key !== "default" && JSON.stringify(before.fg) !== JSON.stringify(p.fg)) this.setFrameGen(this.app.appid, p, before);
      if (before.scaling.resolution !== p.scaling.resolution && p.scaling.enabled && p.scaling.resolution) {
        toaster.toast({ title: "Vex", body: "Render resolution applies the next time the game starts." });
      }
      this.scheduleApply();
    }
  }

  private scheduleApply() {
    clearTimeout(this.applyTimer);
    this.applyTimer = window.setTimeout(() => this.applyCurrent(false), 600);
  }

  /** lsfg-vk: write conf.toml profile + (optionally) the WSI launch-option workaround. */
  async setFrameGen(appid: string, p: Profile, before?: Profile) {
    const name = this.app?.appid === appid ? this.app.name : p.name;
    const res = await be.lsfgSetGame(appid, name, p.fg.enabled, p.fg.multiplier, p.fg.flowScale, p.fg.perfMode);
    if (!res.ok) {
      toaster.toast({ title: "Vex: frame gen", body: res.error ?? "Could not update lsfg-vk config" });
      return;
    }
    try {
      const envs = p.fg.enabled && p.fg.wsiWorkaround ? ["ENABLE_GAMESCOPE_WSI=0"] : [];
      const rec = await steam.setManagedLaunch(appid, envs, this.settings.launch[appid]);
      const launch = { ...this.settings.launch };
      if (rec) launch[appid] = rec;
      else delete launch[appid];
      this.updateSettings({ launch });
    } catch (e) {
      be.log(`launch options error ${e}`);
    }
    if (!before || before.fg.enabled !== p.fg.enabled) {
      toaster.toast({ title: "Vex: frame gen", body: `${p.fg.enabled ? "Enabled" : "Disabled"}. Restart the game to apply.` });
    }
    this.refreshEnv();
  }
}

export const controller = new Controller();
