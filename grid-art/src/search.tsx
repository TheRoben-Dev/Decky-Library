/*
 * Custom SteamGridDB search: type any text (the on-screen keyboard opens on the field) and press
 * Enter or "Search" to browse art for that text as typed: the browser merges the art of its top
 * matching games. The game list under the field is only a suggestion: picking one narrows the art
 * to that game. Suggestions refresh 450 ms after typing stops; only the newest answer is shown.
 * SteamGridDB has no free-text artwork search, so the term goes through its game search.
 */
import { DialogButton, Focusable, ModalRoot, SteamSpinner, TextField } from "@decky/ui";
import { useEffect, useRef, useState } from "react";
import { Game, Match, searchGames } from "./backend";
import { MAX_TERM_GAMES } from "./state";
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
  const [applying, setApplying] = useState(false);
  const shown = useRef("");          // term the current suggestions belong to
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
      else { setGames(r.games); shown.current = q; }
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

  /** Use the typed text itself: art from its top matching games, no game pick needed. */
  const searchTerm = async (raw: string) => {
    const q = raw.trim();
    if (q.length < 2 || applying) return;
    window.clearTimeout(timer.current);
    seq.current++;   // drop any suggestion request still in flight
    setApplying(true); setError(null); setLoading(false);
    try {
      let list = shown.current === q && games ? games : null;
      if (!list) {
        const r = await searchGames(q);
        if (!r.ok) { setError(r.error); return; }
        list = r.games; setGames(list); shown.current = q;
      }
      const top = list.slice(0, MAX_TERM_GAMES);
      if (!top.length) { setError(`Nothing on SteamGridDB matches “${q}”.`); return; }
      pick({ id: top[0].id, name: q, ids: top.map((g) => g.id), names: top.map((g) => g.name), term: true });
    } catch (e) {
      setError(String(e));
    } finally {
      setApplying(false);
    }
  };

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
          onKeyDown={(e) => { if (e.key === "Enter") searchTerm((e.target as HTMLInputElement).value); }} />
        <Focusable flow-children="row" style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <DialogButton style={{ ...btn, flex: 1, borderLeft: `3px solid ${C.active}` }} disabled={term.trim().length < 2 || applying}
            onClick={() => searchTerm(term)}>
            {applying ? "Searching…" : term.trim().length < 2 ? "Type at least 2 letters" : `Search “${term.trim()}”`}
          </DialogButton>
        </Focusable>
        <div style={{ minHeight: 24, margin: "8px 0 4px", fontSize: 12, color: error ? C.warn : C.text1, whiteSpace: "normal" }}>
          {error ?? (loading || games === null ? "" : games.length === 0 ? `Nothing on SteamGridDB matches “${term.trim()}”.` : "Or narrow it to one game:")}
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
