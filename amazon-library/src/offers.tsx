/*
 * Free games tab: this month's free games with Prime (Prime Gaming, now part of Luna).
 * Amazon has no public storefront API, and claiming happens on Amazon's site, so a game is
 * claimed on the phone (QR) or in Steam's browser, then "I claimed it" pulls it into the library.
 * Offers that are codes for another store (GOG, Epic, ...) are marked as such.
 */
import { DialogButton, Focusable, ModalRoot, Navigation, showModal, SteamSpinner } from "@decky/ui";
import { useEffect, useState } from "react";
import { loadLibrary, loadOffers } from "./actions";
import { Offer } from "./backend";
import { Qr } from "./signin";
import { gamePath, offerPath, state, useStore } from "./state";
import { toast } from "./steam";
import { C } from "./ui";

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

export function owned(o: Offer) {
  const t = norm(o.title);
  return state.games?.find((g) => norm(g.title) === t);
}

export function ClaimModal({ o, url, closeModal }: { o: Offer; url: string; closeModal?: () => void }) {
  const [busy, setBusy] = useState(false);
  const claimed = async () => {
    setBusy(true);
    const err = await loadLibrary(true);
    await loadOffers(true);
    setBusy(false);
    if (err) { toast(err); return; }
    const g = owned(o);
    if (g) { closeModal?.(); Navigation.Navigate(gamePath(g.id)); }
    else toast(`${o.title} isn't in your library yet. Amazon can take a minute after claiming.`);
  };
  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      <div style={{ display: "flex", gap: 24, alignItems: "center", flexWrap: "wrap" }}>
        <Qr text={url} />
        <div style={{ flex: 1, minWidth: 240, display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ fontSize: 18, fontWeight: 700 }}>Claim {o.title}</div>
          <div style={{ fontSize: 13, color: C.text1 }}>
            {o.direct
              ? "Scan to open Amazon's free games page on your phone, claim it there with the same Amazon account, then press I claimed it. It shows up in your library and installs like any other game."
              : "This one is a code for another store, not an Amazon Games download. Claim it on your phone and redeem the code in that store."}
          </div>
          {o.link_needed && <div style={{ fontSize: 12, color: C.warn }}>Amazon wants a linked account (for example Twitch or the other store) before you can claim it.</div>}
          <div style={{ fontSize: 11, color: C.data, wordBreak: "break-all" }}>{url}</div>
          <Focusable className="al-row" flow-children="row" style={{ display: "flex", gap: 8 }}>
            {o.direct && <DialogButton disabled={busy} onClick={claimed}>{busy ? "Checking…" : "I claimed it"}</DialogButton>}
            <DialogButton onClick={() => { closeModal?.(); Navigation.CloseSideMenus(); Navigation.NavigateToExternalWeb(url); }}>Open on this handheld</DialogButton>
            <DialogButton onClick={() => closeModal?.()}>Close</DialogButton>
          </Focusable>
        </div>
      </div>
    </ModalRoot>
  );
}

function Tile({ o }: { o: Offer }) {
  const g = owned(o);
  const open = () => Navigation.Navigate(offerPath(o.id));
  return (
    <Focusable className="al-tile" focusClassName="al-focus" onActivate={open} onClick={open}
      onOKActionDescription="Details"
      onSecondaryButton={g ? undefined : () => showModal(<ClaimModal o={o} url={state.claimsUrl} />)}
      onSecondaryActionDescription={g ? undefined : "Claim"}>
      <div className="art" style={{ aspectRatio: "16 / 9" }}>
        {o.image ? <img src={o.image} loading="lazy" decoding="async" draggable={false} /> : <div className="none">{o.title}</div>}
        {g ? <div className="badge">IN LIBRARY</div> : o.claimed ? <div className="badge upd">CLAIMED</div> : null}
      </div>
      <div className="name">{o.title}</div>
      <div className="sub">
        {o.direct ? <span className="al-chip free">Amazon Games</span> : <span className="al-chip code">Code · other store</span>}
        {o.ends && <span>until {o.ends}</span>}
      </div>
    </Focusable>
  );
}

export function FreeTab() {
  const s = useStore();
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (s.offers === null) loadOffers(false); }, []);
  const refresh = async () => { setBusy(true); await loadOffers(true); setBusy(false); };
  const bar = (
    <Focusable className="al-bar" flow-children="row" style={{ padding: "0 24px 10px" }}>
      <span className="lbl">Free with Prime · claim on Amazon, play here</span>
      <div style={{ flex: 1 }} />
      <DialogButton className="al-btn" onClick={() => showModal(<ClaimModal o={{ id: "", title: "free games", ends: "", direct: true, image: "", publisher: "", short: "", claimed: false, can_claim: true, prime: true, link_needed: false }} url={s.claimsUrl} />)}>
        Open claims page
      </DialogButton>
      <DialogButton className="al-btn" disabled={busy} onClick={refresh}>{busy ? "Refreshing…" : "Refresh"}</DialogButton>
    </Focusable>
  );
  if (s.offers === null) return <>{bar}<SteamSpinner background="transparent" /></>;
  const direct = s.offers.filter((o) => o.direct);
  const codes = s.offers.filter((o) => !o.direct);
  return (
    <>
      {bar}
      {s.offersError && (
        <div className="al-msg err" style={{ paddingTop: 0 }}>
          {s.offersError}. You can still claim on Amazon's site with Open claims page; claimed games appear under All after Refresh.
        </div>
      )}
      {!s.offersError && !s.offers.length && <div className="al-msg">No free games listed right now.</div>}
      {direct.length > 0 && <Focusable className="al-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>{direct.map((o) => <Tile key={o.id} o={o} />)}</Focusable>}
      {codes.length > 0 && (
        <>
          <div className="al-msg" style={{ padding: "4px 24px 10px" }}>Codes for other stores</div>
          <Focusable className="al-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>{codes.map((o) => <Tile key={o.id} o={o} />)}</Focusable>
        </>
      )}
    </>
  );
}
