/*
 * Custom SteamGridDB search: type any name (the on-screen keyboard opens on the field) and pick
 * the game whose artwork the browser should show. Searches run 450 ms after typing stops, or
 * right away on Enter; only the newest answer is shown. Results come from the backend's cache
 * when the same term was searched in the last 10 minutes.
 */
import { DialogButton, Focusable, ModalRoot, SteamSpinner, TextField } from "@decky/ui";
import { useEffect, useRef, useState } from "react";
import { Game, Match, searchGames } from "./backend";
import { C, MONO } from "./ui";

const DEBOUNCE_MS = 450;

const btn = { width: "auto", minWidth: 0, padding: "6px 16px", borderRadius: 0, fontSize: 13 };

export function SearchModal({ start, current, auto, onPick, closeModal }: {
  start: string;                      // term the field opens with
  current: number;                    // SteamGridDB game id shown now (0 = Steam app id lookup)
  auto: string;                       // label for the "back to automatic" button
  onPick: (m: Match | null) => void;  // null = drop the custom pick
  closeModal?: () => void;
}) {
  const [term, setTerm] = useState(start);
  const [games, setGames] = useState<Game[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);
  const timer = useRef<number | undefined>(undefined);

  const run = async (t: string) => {
    window.clearTimeout(timer.current);
    const q = t.trim();
    const n = ++seq.current;
    if (q.length < 2) { setGames(null); setError(null); setLoading(false); return; }
    setLoading(true); setError(null);
    try {
      const r = await searchGames(q);
      if (n !== seq.current) return;
      if (!r.ok) { setError(r.error); setGames(null); }
      else setGames(r.games);
    } catch (e) {
      if (n === seq.current) setError(String(e));
    } finally {
      if (n === seq.current) setLoading(false);
    }
  };

  useEffect(() => { run(start); return () => { seq.current++; window.clearTimeout(timer.current); }; }, []);

  const onChange = (v: string) => {
    setTerm(v);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => run(v), DEBOUNCE_MS);
  };

  const pick = (m: Match | null) => { onPick(m); closeModal?.(); };

  // Modals render outside the page's stylesheet, so everything here is styled inline.
  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      <div style={{ fontFamily: MONO, color: C.text0 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 10 }}>
          <span style={{ fontSize: 16, fontWeight: 700, letterSpacing: ".06em", textTransform: "uppercase" }}>Search artwork</span>
          <span style={{ marginLeft: "auto", fontSize: 11, color: C.data, border: `1px solid ${C.data}`, padding: "1px 6px", letterSpacing: ".1em" }}>STEAMGRIDDB</span>
        </div>
        <TextField label="Game name" value={term} bShowClearAction focusOnMount
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") run((e.target as HTMLInputElement).value); }} />
        <div style={{ minHeight: 24, margin: "8px 0 4px", fontSize: 12, color: error ? C.warn : C.text1, whiteSpace: "normal" }}>
          {error ?? (loading ? "" : games === null ? "Type at least 2 letters." : games.length === 0 ? `Nothing on SteamGridDB called “${term.trim()}”.` : `${games.length} match${games.length === 1 ? "" : "es"}`)}
        </div>
        {loading && <div style={{ height: 48 }}><SteamSpinner background="transparent" /></div>}
        {!loading && games && games.length > 0 && (
          <Focusable flow-children="column" style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: "44vh", overflowY: "auto", paddingRight: 4 }}>
            {games.map((g) => (
              <DialogButton key={g.id} onClick={() => pick({ id: g.id, name: g.name })}
                style={{ ...btn, width: "100%", display: "flex", alignItems: "center", gap: 10, textAlign: "left",
                  borderLeft: `3px solid ${g.id === current ? C.ok : "transparent"}` }}>
                <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{g.name}</span>
                {g.year && <span style={{ fontSize: 11, color: C.text1 }}>{g.year}</span>}
                {g.verified && <span style={{ fontSize: 10, color: C.data, letterSpacing: ".08em" }}>VERIFIED</span>}
                {g.id === current && <span style={{ fontSize: 10, color: C.ok, letterSpacing: ".08em" }}>IN USE</span>}
              </DialogButton>
            ))}
          </Focusable>
        )}
        <Focusable flow-children="row" style={{ display: "flex", gap: 8, marginTop: 12, justifyContent: "flex-end" }}>
          <DialogButton style={btn} onClick={() => pick(null)}>{auto}</DialogButton>
          <DialogButton style={btn} onClick={closeModal}>Cancel</DialogButton>
        </Focusable>
      </div>
    </ModalRoot>
  );
}
