import { DialogButton, Field, Focusable, PanelSectionRow } from "@decky/ui";
import { useState } from "react";
import { FaGamepad } from "react-icons/fa";
import { Game, iconUrls } from "./steam";

export const note = { fontSize: "12px", lineHeight: "16px", opacity: 0.75, whiteSpace: "normal" as const };
export const warn = { ...note, color: "#FF9F1C", opacity: 1 };

const ICON = 32;

/** The game's square Steam icon; tries each URL in turn, then a gamepad placeholder. */
export function GameIcon({ g }: { g: Game }) {
  const [urls] = useState(() => iconUrls(g));
  const [i, setI] = useState(0);
  const box = { width: ICON, height: ICON, minWidth: ICON, borderRadius: "3px", flexShrink: 0 } as const;
  if (i >= urls.length) {
    return (
      <div style={{ ...box, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(255,255,255,0.08)" }}>
        <FaGamepad style={{ opacity: 0.6 }} />
      </div>
    );
  }
  return <img src={urls[i]} style={{ ...box, objectFit: "cover" }} onError={() => setI(i + 1)} loading="lazy" />;
}

export function GameRow({ g, desc, actions }: { g: Game; desc: string; actions: { label: string; onClick: () => void }[] }) {
  const label = (
    <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0 }}>
      <GameIcon g={g} />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{g.name}</span>
    </div>
  );
  return (
    <PanelSectionRow>
      <Field label={label} description={desc || undefined} bottomSeparator="standard" padding="none"
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
