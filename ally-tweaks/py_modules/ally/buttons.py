"""Back buttons (M1/M2) and A/B layout through Handheld Daemon.

HHD keys (hhd/plugins/outputs.yml, hhd/device/rog_ally/controllers.yml):
  controllers.rog_ally.controller_mode.mode               dualsense | uinput (Xbox) | ...
  controllers.rog_ally.controller_mode.<mode>.paddles_as  what M1/M2 do
  controllers.rog_ally.nintendo_mode                      swap A/B and X/Y
"Steam Input" passes M1/M2 to Steam as back paddles, so Steam's own per-game
controller layouts can bind them to anything (keys, macros, action sets).

Any change here makes HHD restart its virtual controller (about a second),
so the plugin only writes when the value actually differs.
"""
from . import hhd

PADDLE_OPTIONS = {
    "dualsense": ["steam_input", "noob", "touchpad", "disabled"],
    "uinput": ["steam_input", "noob", "disabled"],
}
NINTENDO = "controllers.rog_ally.nintendo_mode"


def status(state: dict) -> dict:
    mode = state.get("controllers.rog_ally.controller_mode.mode")
    key = f"controllers.rog_ally.controller_mode.{mode}.paddles_as"
    return {
        "supported": mode is not None,
        "controllerMode": mode,
        "paddles": state.get(key),
        "paddleOptions": PADDLE_OPTIONS.get(mode, []) if key in state else [],
        "nintendo": bool(state.get(NINTENDO, False)),
    }


def apply(paddles: str | None, nintendo: bool | None, state: dict | None = None) -> bool:
    st = state if state is not None else hhd.get_state()
    mode = st.get("controllers.rog_ally.controller_mode.mode")
    vals = {}
    key = f"controllers.rog_ally.controller_mode.{mode}.paddles_as"
    if paddles and key in st and paddles in PADDLE_OPTIONS.get(mode, []):
        vals[key] = paddles
    if nintendo is not None and NINTENDO in st:
        vals[NINTENDO] = bool(nintendo)
    return hhd.set_changed(vals, st) if vals else False
