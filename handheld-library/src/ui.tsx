import { DialogButton, Field, Focusable, PanelSectionRow } from "@decky/ui";
import type { Game } from "./steam";

export const note = { fontSize: "12px", lineHeight: "16px", opacity: 0.75, whiteSpace: "normal" as const };
export const warn = { ...note, color: "#FF9F1C", opacity: 1 };

export function GameRow({ g, desc, actions }: { g: Game; desc: string; actions: { label: string; onClick: () => void }[] }) {
  return (
    <PanelSectionRow>
      <Field label={g.name} description={desc || undefined} bottomSeparator="standard" padding="none"
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
