"""Key naming and the catalogue of things a key can be assigned to."""
from cool68 import MODS_BY_BIT, basic_key, consumer_key, modifier_key

HID_NAMES = {0x28: "Enter", 0x29: "Esc", 0x2A: "Backspace", 0x2B: "Tab", 0x2C: "Space", 0x2D: "-",
             0x2E: "=", 0x2F: "[", 0x30: "]", 0x31: "\\", 0x33: ";", 0x34: "'", 0x35: "`", 0x36: ",",
             0x37: ".", 0x38: "/", 0x39: "Caps", 0x46: "PrtSc", 0x47: "ScrLk", 0x48: "Pause",
             0x49: "Insert", 0x4A: "Home", 0x4B: "PgUp", 0x4C: "Delete", 0x4D: "End", 0x4E: "PgDn",
             0x4F: "→", 0x50: "←", 0x51: "↓", 0x52: "↑", 0x53: "NumLk", 0x65: "Menu"}
HID_NAMES.update({0x04 + i: chr(ord("A") + i) for i in range(26)})
HID_NAMES.update({0x1E + i: str((i + 1) % 10) for i in range(10)})
HID_NAMES.update({0x3A + i: f"F{i + 1}" for i in range(12)})
HID_NAMES.update({0x68 + i: f"F{13 + i}" for i in range(12)})
HID_NAMES.update({0x54: "Num /", 0x55: "Num *", 0x56: "Num -", 0x57: "Num +", 0x58: "Num Ent", 0x63: "Num .",
                  **{0x59 + i: f"Num {i + 1}" for i in range(9)}, 0x62: "Num 0"})

MEDIA = {0xCD: "Play/Pause", 0xB5: "Next", 0xB6: "Previous", 0xB7: "Stop", 0xE9: "Vol +", 0xEA: "Vol −",
         0xE2: "Mute", 0x223: "Browser", 0x192: "Calculator", 0x18A: "Mail", 0x194: "My PC",
         0x22A: "Favourites", 0x6F: "Screen +", 0x70: "Screen −"}

MOUSE = {0x01010100: "Left click", 0x01020100: "Right click", 0x01030100: "Middle click",
         0x01040100: "Back", 0x01050100: "Forward"}

# lighting / system keys found on the Fn layer
SPECIAL = {0x08000000: "Backlight mode", 0x08020000: "Backlight colour", 0x08030000: "Backlight brightness",
           0x08040100: "Backlight speed +", 0x08040200: "Backlight speed −", 0x08000001: "Side-light mode",
           0x08020001: "Side-light colour", 0x08030101: "Side bright. +", 0x08030201: "Side bright. −",
           0x07000001: "Win lock (hold 3s)", 0x0D000000: "Fn", 0x0D010000: "Fn 1"}


def combo(mods, usage):
    return mods << 16 | usage << 8


CTRL, SHIFT, ALT, WIN = 0x01, 0x02, 0x04, 0x08
SHORTCUTS = {
    combo(CTRL, 0x06): "Copy", combo(CTRL, 0x19): "Paste", combo(CTRL, 0x1B): "Cut", combo(CTRL, 0x1D): "Undo",
    combo(CTRL, 0x1C): "Redo", combo(CTRL, 0x04): "Select all", combo(CTRL, 0x16): "Save",
    combo(CTRL, 0x09): "Find", combo(CTRL, 0x12): "Open", combo(CTRL, 0x11): "New", combo(CTRL, 0x17): "New tab",
    combo(CTRL, 0x1A): "Close tab", combo(CTRL | SHIFT, 0x29): "Task manager", combo(ALT, 0x2B): "Alt+Tab",
    combo(ALT, 0x3D): "Close app", combo(WIN, 0x07): "Show desktop", combo(WIN, 0x0F): "Lock PC",
    combo(WIN, 0x15): "Run", combo(WIN, 0x08): "Explorer", combo(WIN, 0x0C): "Win settings",
    combo(WIN, 0x0A): "Game bar", combo(WIN, 0x37): "Emoji", combo(CTRL, 0x2E): "Zoom in",
    combo(CTRL, 0x2D): "Zoom out",
}


SHORT = {0x08000000: "Light mode", 0x08020000: "Light colour", 0x08030000: "Light bright", 0x08040100: "Speed +",
         0x08040200: "Speed −", 0x08000001: "Side mode", 0x08020001: "Side colour", 0x08030101: "Side bright +",
         0x08030201: "Side bright −", 0x07000001: "Win lock", 0x0D000000: "Fn", 0x0D010000: "Fn 1",
         0x020000CD: "Play", 0x020000B5: "Next", 0x020000B6: "Prev", 0x020000E9: "Vol +", 0x020000EA: "Vol −",
         0x020000E2: "Mute"}


NO_FUNCTION = {0x07000004, 0x07000012}   # Fn+Tab and Fn+\ : the firmware defines them but they do nothing


def describe(v, short=False):
    """Readable label for a 32-bit key value. short=True gives a compact label for a keycap."""
    if v is None:
        return ""
    if v == 0:
        return "—"
    if v in NO_FUNCTION:
        return "No function"
    if short and v in SHORT:
        return SHORT[v]
    if v in SPECIAL:
        return SPECIAL[v]
    if short and v >> 24 in (7, 8):          # Fn-layer system / lighting codes we have no name for
        return f"{'Sys' if v >> 24 == 7 else 'Light'} {v & 0xFFFF:04X}"
    if v in MOUSE:
        return MOUSE[v]
    if v in SHORTCUTS:
        return SHORTCUTS[v]
    t, mods, hi, lo = v >> 24, v >> 16 & 0xFF, v >> 8 & 0xFF, v & 0xFF
    if t == 0 and not hi and not lo and mods in MODS_BY_BIT:
        return MODS_BY_BIT[mods]
    if t == 0 and not mods and not hi:
        return HID_NAMES.get(lo, f"0x{lo:02X}")
    if t == 0 and mods and hi:
        return "+".join(n for b, n in MODS_BY_BIT.items() if mods & b) + "+" + HID_NAMES.get(hi, f"0x{hi:02X}")
    if t == 2:
        return MEDIA.get(v & 0xFFFF, f"media {v & 0xFFFF:X}")
    if t == 3:
        return f"Macro {(v & 0xFF) + 1}"
    return f"{v:08X}"


def catalogue():
    """{category: [(label, value)]} for the assignment picker."""
    keys = {
        "Letters": [(HID_NAMES[u], basic_key(u)) for u in range(0x04, 0x1E)],
        "Numbers": [(HID_NAMES[u], basic_key(u)) for u in list(range(0x1E, 0x28))],
        "F keys": [(HID_NAMES[u], basic_key(u)) for u in list(range(0x3A, 0x46)) + list(range(0x68, 0x74))],
        "Symbols": [(HID_NAMES[u], basic_key(u)) for u in (0x2D, 0x2E, 0x2F, 0x30, 0x31, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38)],
        "Editing": [(HID_NAMES[u], basic_key(u)) for u in (0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x39, 0x49, 0x4C, 0x4A, 0x4D,
                                                         0x4B, 0x4E, 0x4F, 0x50, 0x51, 0x52, 0x46, 0x47, 0x48, 0x65)],
        "Numpad": [(HID_NAMES[u], basic_key(u)) for u in list(range(0x53, 0x64))],
        "Modifiers": [(n, modifier_key(b)) for b, n in MODS_BY_BIT.items()],
        "Media": [(n, consumer_key(u)) for u, n in MEDIA.items()],
        "Shortcuts": [(n, v) for v, n in SHORTCUTS.items()],
        "Mouse": [(n, v) for v, n in MOUSE.items()],
        "Lighting / Fn": [(n, v) for v, n in SPECIAL.items()],
    }
    return keys
