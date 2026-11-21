/*
 * Shared Quick Access layout pieces (same file in every Decky-Library plugin).
 *
 * Every plugin panel follows one structure:
 *   1. status header: what's happening right now (open, never collapses)
 *   2. main controls: what you change most (open)
 *   3. secondary groups: collapsed by default, with a one-line summary
 *   4. Settings: how the plugin itself behaves (collapsed)
 *   5. About: device/info text (collapsed, last)
 * Open/closed state is remembered per section, because Steam remounts the
 * panel every time Quick Access opens or a dropdown closes.
 */
import { Field, PanelSection, PanelSectionRow } from "@decky/ui";
import { ReactNode, useState } from "react";

function load(key: string, fallback: boolean): boolean {
  try {
    const v = window.localStorage.getItem(key);
    return v === null ? fallback : v === "1";
  } catch { return fallback; }
}

function store(key: string, open: boolean) {
  try { window.localStorage.setItem(key, open ? "1" : "0"); } catch { /* private mode etc. */ }
}

export interface SectionProps {
  /** Stable id, used to remember open/closed. */
  id: string;
  title: string;
  /** Shown under the title while collapsed (e.g. "Off" or "80 % limit"). */
  summary?: ReactNode;
  /** Collapsible sections start closed unless this is true. */
  defaultOpen?: boolean;
  /** false = plain always-open section with a normal header. */
  collapsible?: boolean;
  children?: ReactNode;
}

export function sectionFactory(plugin: string) {
  return function Section({ id, title, summary, defaultOpen = false, collapsible = true, children }: SectionProps) {
    const key = `${plugin}:section:${id}`;
    const [open, setOpen] = useState(() => load(key, defaultOpen));
    if (!collapsible) return <PanelSection title={title}>{children}</PanelSection>;
    const toggle = () => { const next = !open; setOpen(next); store(key, next); };
    return (
      <PanelSection>
        <PanelSectionRow>
          <Field
            label={<span style={{ textTransform: "uppercase", letterSpacing: "0.04em", fontSize: "13px", fontWeight: 600 }}>{title}</span>}
            description={!open && summary ? <span style={{ fontSize: "12px" }}>{summary}</span> : undefined}
            focusable highlightOnFocus onActivate={toggle} onClick={toggle}
            bottomSeparator={open ? "standard" : "none"}
          >
            <span style={{ opacity: 0.7, fontSize: "14px" }}>{open ? "▾" : "▸"}</span>
          </Field>
        </PanelSectionRow>
        {open && children}
      </PanelSection>
    );
  };
}
