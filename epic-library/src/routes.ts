export const LIBRARY_ROUTE = "/epic-library";
export const GAME_ROUTE = "/epic-library/game/:app";
export const OFFER_ROUTE = "/epic-library/offer";
export const gamePath = (app: string) => `/epic-library/game/${encodeURIComponent(app)}`;
