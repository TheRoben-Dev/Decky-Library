// Picks a Proton build for a game from its ProtonDB tier, Steam Deck rating
// and the builds Steam has loaded.
//
// ProtonDB exposes only per-game summaries (tier, trending tier, report
// count), not which Proton version each report used, so the choice is a
// policy, not a per-report vote:
//   native Linux build              -> leave alone (don't force Proton on it)
//   Platinum, or Deck Verified       -> leave on Steam's default Proton
//   Gold / Silver / Bronze / Borked / no reports
//                                    -> newest GE-Proton (or CachyOS if preferred),
//                                       falling back to the other custom build,
//                                       then Proton Experimental.
import { Family, GameInfo, ProtonDBSummary, SteamTool } from "./types";

export const TIER_ORDER = ["borked", "bronze", "silver", "gold", "platinum", "native"];
export const TIER_COLOR: Record<string, string> = {
  native: "#5cc85c",
  platinum: "#b4c7dc",
  gold: "#cfb53b",
  silver: "#a6a6a6",
  bronze: "#cd7f32",
  borked: "#ff4d4d",
  pending: "#8c8c8c",
};

export function effectiveTier(s?: ProtonDBSummary | null): string | null {
  if (!s) return null;
  // trendingTier reflects recent reports (newer game patches / Proton); only
  // trust it once there are a few reports behind it.
  if (s.trendingTier && (s.total ?? 0) >= 5) return s.trendingTier;
  return s.tier ?? s.provisionalTier ?? null;
}

export function familyOf(name: string): string {
  const n = name.toLowerCase();
  if (n.includes("cachyos")) return "cachyos";
  if (n.startsWith("ge-proton") || n.includes("proton-ge")) return "ge";
  if (n.includes("experimental")) return "experimental";
  if (n.includes("hotfix")) return "hotfix";
  if (n.startsWith("proton")) return "valve";
  return "other";
}

function versionKey(name: string): number[] {
  return (name.match(/\d+/g) ?? []).map(Number);
}

function cmpVersion(a: string, b: string): number {
  const x = versionKey(a), y = versionKey(b);
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    const d = (x[i] ?? -1) - (y[i] ?? -1);
    if (d) return d;
  }
  return 0;
}

export function newestOf(family: string, tools: SteamTool[]): SteamTool | null {
  const list = tools.filter((t) => familyOf(t.name) === family);
  list.sort((a, b) => cmpVersion(b.name, a.name));
  return list[0] ?? null;
}

export interface Recommendation {
  /** null = leave the game on whatever Steam picks by default. */
  tool: string | null;
  display: string;
  reason: string;
  /** Preferred family isn't loaded in Steam yet. */
  wantsFamily?: Family;
}

export function recommend(
  game: Pick<GameInfo, "native" | "deckCategory">,
  pdb: ProtonDBSummary | null | undefined,
  tools: SteamTool[],
  preferred: Family,
): Recommendation {
  const tier = effectiveTier(pdb);
  if (game.native) return { tool: null, display: "Steam default", reason: "Native Linux build" };
  if (tier === "native") return { tool: null, display: "Steam default", reason: "ProtonDB: runs natively" };
  if (tier === "platinum") return { tool: null, display: "Steam default", reason: "ProtonDB Platinum: works out of the box" };
  if (game.deckCategory === 3) return { tool: null, display: "Steam default", reason: "Steam Deck Verified" };

  const why = tier ? `ProtonDB ${tier[0].toUpperCase()}${tier.slice(1)}` : "No ProtonDB rating";
  const other: Family = preferred === "ge" ? "cachyos" : "ge";
  const pick = newestOf(preferred, tools);
  if (pick) return { tool: pick.name, display: pick.display, reason: `${why}: custom build has extra game fixes` };
  const alt = newestOf(other, tools);
  if (alt) return { tool: alt.name, display: alt.display, reason: `${why}: custom build has extra game fixes`, wantsFamily: preferred };
  const exp = tools.find((t) => t.name === "proton_experimental");
  if (exp) return { tool: exp.name, display: exp.display, reason: `${why}: newest Valve fixes`, wantsFamily: preferred };
  return { tool: null, display: "Steam default", reason: `${why}: no custom build installed yet`, wantsFamily: preferred };
}

export { cmpVersion };
