"""Macros live in a local JSON file because the keyboard cannot read them back."""
import json
import os
from pathlib import Path

from PySide6.QtCore import Qt

from cool68 import macro_event

PATH = Path(os.environ.get("APPDATA", Path.home())) / "COOL68" / "macros.json"


class MacroStore:
    def __init__(self):
        self.macros = []   # [{"name": str, "events": [{"key": str, "down": bool, "delay": int}]}]
        try:
            self.macros = json.loads(PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass

    def save(self):
        PATH.parent.mkdir(parents=True, exist_ok=True)
        PATH.write_text(json.dumps(self.macros, indent=1), encoding="utf-8")

    def names(self):
        return [m["name"] for m in self.macros]

    def add(self, name):
        self.macros.append({"name": name, "events": []})
        self.save()
        return len(self.macros) - 1

    def remove(self, i):
        del self.macros[i]
        self.save()

    def for_device(self):
        return [(m["name"], [macro_event(e["key"], e["down"], e["delay"]) for e in m["events"]]) for m in self.macros]


def _qt_names():
    m = {Qt.Key_Escape: "Escape", Qt.Key_Delete: "Delete", Qt.Key_Home: "Home", Qt.Key_End: "End",
         Qt.Key_PageUp: "PageUp", Qt.Key_PageDown: "PageDown", Qt.Key_QuoteLeft: "Backquote", Qt.Key_Minus: "Minus",
         Qt.Key_Equal: "Equal", Qt.Key_Backspace: "Backspace", Qt.Key_Tab: "Tab", Qt.Key_BracketLeft: "BracketLeft",
         Qt.Key_BracketRight: "BracketRight", Qt.Key_Backslash: "Backslash", Qt.Key_CapsLock: "CapsLock",
         Qt.Key_Semicolon: "Semicolon", Qt.Key_Apostrophe: "Quote", Qt.Key_Return: "Enter", Qt.Key_Enter: "Enter",
         Qt.Key_Comma: "Comma", Qt.Key_Period: "Period", Qt.Key_Slash: "Slash", Qt.Key_Space: "Space",
         Qt.Key_Up: "ArrowUp", Qt.Key_Down: "ArrowDown", Qt.Key_Left: "ArrowLeft", Qt.Key_Right: "ArrowRight",
         Qt.Key_Insert: "Insert", Qt.Key_Pause: "Pause", Qt.Key_Print: "PrintScreen", Qt.Key_ScrollLock: "ScrollLock",
         Qt.Key_NumLock: "NumLock", Qt.Key_Menu: "ContextMenu", Qt.Key_Meta: "MetaLeft"}
    for i in range(26):
        m[getattr(Qt, f"Key_{chr(65 + i)}")] = f"Key{chr(65 + i)}"
    for i in range(10):
        m[getattr(Qt, f"Key_{i}")] = f"Digit{i}"
    for i in range(1, 13):
        m[getattr(Qt, f"Key_F{i}")] = f"F{i}"
    return m


QT_KEYS = _qt_names()


def key_name(event):
    """MACRO_KEYS name for a Qt key event, or None if the key isn't supported."""
    k = event.key()
    right = bool(event.nativeScanCode() & 0x100)
    if k == Qt.Key_Shift:
        return "ShiftRight" if event.nativeScanCode() == 0x36 else "ShiftLeft"
    if k == Qt.Key_Control:
        return "ControlRight" if right else "ControlLeft"
    if k == Qt.Key_Alt:
        return "AltRight" if right else "AltLeft"
    return QT_KEYS.get(k)


TEXT_KEYS = {" ": "Space", ",": "Comma", ".": "Period", "/": "Slash", ";": "Semicolon", "'": "Quote", "-": "Minus",
             "=": "Equal", "\n": "Enter"}


def text_to_events(text, delay=20):
    """Typing macro for plain ASCII text (letters, digits and a few symbols)."""
    ev = []
    for ch in text:
        shift = ch.isupper()
        if ch.isalpha() and ch.isascii():
            name = f"Key{ch.upper()}"
        elif ch.isdigit() and ch.isascii():
            name = f"Digit{ch}"
        elif ch in TEXT_KEYS:
            name = TEXT_KEYS[ch]
        else:
            continue
        if shift:
            ev.append({"key": "ShiftLeft", "down": True, "delay": 5})
        ev += [{"key": name, "down": True, "delay": delay}, {"key": name, "down": False, "delay": delay}]
        if shift:
            ev.append({"key": "ShiftLeft", "down": False, "delay": 5})
    return ev
