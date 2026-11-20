import { ButtonItem, ConfirmModal, Navigation, PanelSection, PanelSectionRow, showModal } from "@decky/ui";
import { toaster, useQuickAccessVisible } from "@decky/api";
import { useEffect, useState } from "react";
import { GameRow, note } from "./ui";
import { Game, hiddenGames, launch, unhide } from "./steam";

const installedHidden = () => hiddenGames().filter((g) => g.installed);

/** Content of the "Hidden games" Quick Access tab: hidden games that are installed on this device. */
export function HiddenTab() {
  const visible = useQuickAccessVisible();
  const [games, setGames] = useState<Game[]>(installedHidden);
  const refresh = () => setGames(installedHidden());
  useEffect(() => { if (visible) refresh(); }, [visible]);

  const doUnhide = (ids: number[]) => {
    try { unhide(ids); } catch (e) { toaster.toast({ title: "Hidden games", body: `Couldn't unhide: ${e}` }); }
    setTimeout(refresh, 300);   // Steam updates its Hidden collection asynchronously
  };

  return (
    <PanelSection>
      {games.length === 0 && <PanelSectionRow><div style={note}>No hidden games are installed.</div></PanelSectionRow>}
      {games.map((g) => (
        <GameRow key={g.appid} g={g} desc=""
          actions={[
            { label: "Play", onClick: () => { Navigation.CloseSideMenus(); launch(g); } },
            { label: "Unhide", onClick: () => doUnhide([g.appid]) },
            { label: "Page", onClick: () => { Navigation.CloseSideMenus(); Navigation.Navigate(`/library/app/${g.appid}`); } },
          ]} />
      ))}
      {games.length > 1 && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => showModal(
            <ConfirmModal strTitle="Unhide all?" strOKButtonText="Unhide all"
              strDescription={`Shows these ${games.length} games in your library again.`}
              onOK={() => doUnhide(games.map((g) => g.appid))} />,
          )}>Unhide all</ButtonItem>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}
