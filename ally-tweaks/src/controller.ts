// Watches the running game (tells the backend so per-game lighting/buttons
// switch even with the menu closed) and keeps a fresh copy of backend state
// for the UI.
import { Router } from "@decky/ui";
import * as be from "./backend";
import { AppState, clone, DEFAULT_LIGHT, Light, Settings } from "./types";

type Listener = () => void;

class Controller {
  state: AppState | null = null;
  appid = "";
  private listeners = new Set<Listener>();
  private gameTimer?: number;
  private stateTimer?: number;
  private saveTimer?: number;
  private pending: Partial<Settings> = {};

  subscribe(l: Listener) {
    this.listeners.add(l);
    if (this.listeners.size === 1) {
      this.refresh();
      this.stateTimer = window.setInterval(() => this.refresh(), 3000);
    }
    return () => {
      this.listeners.delete(l);
      if (!this.listeners.size) clearInterval(this.stateTimer);
    };
  }
  private emit() {
    this.listeners.forEach((l) => l());
  }

  start() {
    this.gameTimer = window.setInterval(() => this.watchGame(), 1500);
    this.watchGame();
  }
  stop() {
    clearInterval(this.gameTimer);
    clearInterval(this.stateTimer);
  }

  private watchGame() {
    const app: any = Router.MainRunningApp;
    const id = app?.appid ? String(app.appid) : "";
    if (id === this.appid) return;
    this.appid = id;
    be.setGame(id, app?.display_name ?? (id ? `App ${id}` : "")).catch((e) => be.log(`setGame ${e}`));
    setTimeout(() => this.refresh(), 500);
  }

  async refresh() {
    try {
      const s = await be.getState();
      // Keep unsaved local edits visible while a save is pending.
      if (Object.keys(this.pending).length) s.settings = { ...s.settings, ...this.pending } as Settings;
      this.state = s;
      this.emit();
    } catch (e) {
      console.warn("[AllyTweaks] state failed", e);
    }
  }

  get settings(): Settings | null {
    return this.state?.settings ?? null;
  }

  /** Optimistic local update + debounced save (sliders fire a lot). */
  patch(p: Partial<Settings>) {
    if (!this.state) return;
    this.state = { ...this.state, settings: { ...this.state.settings, ...p } };
    this.pending = { ...this.pending, ...p };
    this.emit();
    clearTimeout(this.saveTimer);
    this.saveTimer = window.setTimeout(async () => {
      const send = this.pending;
      this.pending = {};
      await be.saveSettings(send).catch((e) => be.log(`save ${e}`));
      this.refresh();
    }, 350);
  }

  // ---------- lighting ----------
  gameLight(): Light | null {
    const s = this.settings;
    return s && this.appid ? s.rgb.perGame[this.appid]?.light ?? null : null;
  }
  editLight(m: (l: Light) => void) {
    const s = this.settings;
    if (!s) return;
    const rgb = clone(s.rgb);
    const g = this.appid ? rgb.perGame[this.appid] : undefined;
    m(g ? g.light : rgb.base);
    this.patch({ rgb });
  }
  setRgb(p: Partial<Settings["rgb"]>) {
    const s = this.settings;
    if (s) this.patch({ rgb: { ...clone(s.rgb), ...p } });
  }
  toggleGameLight(on: boolean) {
    const s = this.settings;
    if (!s || !this.appid) return;
    const rgb = clone(s.rgb);
    if (on) rgb.perGame[this.appid] = { name: this.state?.game?.name ?? this.appid, light: clone(rgb.base ?? DEFAULT_LIGHT) };
    else delete rgb.perGame[this.appid];
    this.patch({ rgb });
  }

  // ---------- buttons ----------
  async toggleGameButtons(on: boolean) {
    const s = this.settings;
    const b = this.state?.buttons;
    if (!s || !this.appid) return;
    const buttons = clone(s.buttons);
    if (on) {
      buttons.perGame[this.appid] = {
        name: this.state?.game?.name ?? this.appid,
        paddles: b?.paddles ?? "steam_input",
        nintendo: b?.nintendo ?? false,
      };
    } else delete buttons.perGame[this.appid];
    await this.saveButtons(buttons);
  }
  async editGameButtons(m: (g: Settings["buttons"]["perGame"][string]) => void) {
    const s = this.settings;
    if (!s || !this.appid || !s.buttons.perGame[this.appid]) return;
    const buttons = clone(s.buttons);
    m(buttons.perGame[this.appid]);
    await this.saveButtons(buttons);
  }
  private async saveButtons(buttons: Settings["buttons"]) {
    // Send only perGame; the backend owns the saved "default" snapshot.
    await be.saveSettings({ buttons: { perGame: buttons.perGame } as any });
    await be.reapplyButtons();
    this.refresh();
  }
}

export const controller = new Controller();
