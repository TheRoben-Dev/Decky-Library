/*
 * Free-game store page: /amazon-library/offer/:id
 * Everything Amazon's free games list says about the game (description, screenshots, genres,
 * modes, rating), plus the ways to claim it. Uses the list already loaded by the Free games tab
 * (cached for a few hours by the backend), so opening a page costs no extra request.
 */
import { DialogButton, Focusable, Navigation, showModal, SteamSpinner, useParams } from "@decky/ui";
import { useEffect } from "react";
import { loadOffers } from "./actions";
import { About, Details, Gallery } from "./media";
import { ClaimModal, owned } from "./offers";
import { gamePath, useStore } from "./state";
import { C, PAGE_CSS } from "./ui";

export const OFFER_ROUTE = "/amazon-library/offer/:id";

export function OfferPage() {
  const s = useStore();
  const id = decodeURIComponent(useParams<{ id: string }>().id);
  useEffect(() => { if (s.offers === null) loadOffers(false); }, []);
  const o = s.offers?.find((x) => x.id === id);
  const g = o ? owned(o) : undefined;

  let body;
  if (s.offers === null) body = <SteamSpinner background="transparent" />;
  else if (!o) body = (
    <div className="al-msg err">{s.offersError || "This free game isn't listed anymore."}
      <div style={{ marginTop: 16 }}><DialogButton className="al-btn" onClick={() => Navigation.NavigateBack()}>Back</DialogButton></div>
    </div>
  );
  else {
    const meta = [o.developer, o.publisher !== o.developer ? o.publisher : "", (o.released ?? "").slice(0, 4), ...(o.genres ?? []).slice(0, 2)]
      .filter(Boolean).join(" · ");
    body = (
      <div className="al-detail">
        <div className="cover" style={{ flex: "0 0 380px" }}>
          <div className="frame" style={{ aspectRatio: "16 / 9" }}>{o.image && <img src={o.image} draggable={false} />}</div>
        </div>
        <Focusable className="info" flow-children="column">
          {o.logo ? <img src={o.logo} alt={o.title} style={{ maxWidth: 420, maxHeight: 120, objectFit: "contain", objectPosition: "left" }} />
            : <h1>{o.title}</h1>}
          {meta && <div className="by">{meta}</div>}
          <div className="al-row">
            {o.direct ? <span className="al-chip free">Free with Prime · Amazon Games</span> : <span className="al-chip code">Code for another store</span>}
            {g ? <span className="al-chip done">In your library</span> : o.claimed ? <span className="al-chip done">Claimed</span> : null}
            {o.ends && <span className="by">Free until {o.ends}</span>}
          </div>
          <div className="al-panel">
            <Focusable className="al-row" flow-children="row">
              {g ? <DialogButton className="al-btn primary" onClick={() => Navigation.Navigate(gamePath(g.id))}>Open in library</DialogButton>
                : <DialogButton className="al-btn primary" onClick={() => showModal(<ClaimModal o={o} url={s.claimsUrl} />)}>
                  {o.claimed && o.direct ? "Find it in my library" : "Claim"}</DialogButton>}
            </Focusable>
            <div style={{ fontSize: 12, color: C.text1 }}>
              {g ? "Already on your account: install it from its library page."
                : o.direct ? "Claim it on Amazon (phone QR or this handheld), then it installs here like any other game."
                  : "Amazon gives a code for another store; redeem it there (for example with GOG Library or Epic Library)."}
            </div>
            {o.link_needed && <div style={{ fontSize: 12, color: C.warn }}>Amazon wants a linked account before you can claim this one.</div>}
          </div>
          <Gallery shots={o.screenshots ?? []} />
          <About text={o.description || o.short} />
          <Details f={o} />
        </Focusable>
      </div>
    );
  }

  return (
    <div className="al-page">
      <style>{PAGE_CSS}</style>
      {(o?.background || o?.screenshots?.[0]) && <div className="al-hero" style={{ backgroundImage: `url("${o.background || o.screenshots![0]}")` }} />}
      <div className="al-inner">
        <div className="al-head">
          <span className="t">Amazon Library</span>
          <span className="s">{o?.title ?? "Free games"}</span>
          <span className="grow" />
          <span className="tag">FREE WITH PRIME</span>
        </div>
        {body}
      </div>
    </div>
  );
}
