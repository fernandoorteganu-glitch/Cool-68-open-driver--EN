"""Page base class plus Dashboard, Keymap and Lighting pages."""
import functools

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QApplication, QComboBox, QStackedWidget, QGridLayout, QHBoxLayout, QLineEdit, QMessageBox, QScrollArea,
                               QSpinBox, QVBoxLayout, QWidget)

import cool68
from cool68 import KEY_POS, LIGHT_MODES, MACRO_REPEAT, macro_key

from . import effects, keys, theme
from .widgets import (Card, ColorPicker, EffectView, GradientLabel, KeyboardView, LabeledSlider, Segmented, Toggle,
                      button, label, spin)


def guarded(fn):
    """Run a hardware-touching method with a wait cursor; device errors become a toast instead of a crash."""
    @functools.wraps(fn)
    def wrapper(self, *a, **k):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            return fn(self, *a, **k)
        except Exception as e:  # device unplugged, timeout, bad value
            self.ctx.fail(e)
        finally:
            QApplication.restoreOverrideCursor()
    return wrapper


class Page(QWidget):
    def __init__(self, ctx, title, subtitle):
        super().__init__()
        self.ctx = ctx
        self.loaded = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 26, 32, 24)
        outer.setSpacing(18)
        self.page_colors = theme.PAGE_COLORS.get(title, (theme.ACCENT, theme.ACCENT2))
        head = QVBoxLayout()
        head.setSpacing(0)
        head.addWidget(GradientLabel(title, self.page_colors))
        head.addWidget(label(subtitle, "muted"))
        outer.addLayout(head)
        self.body = QVBoxLayout()
        self.body.setSpacing(16)
        outer.addLayout(self.body, 1)

    def on_show(self):
        if not self.loaded:
            self.loaded = True
            self.load()

    def load(self):
        pass

    def on_leave(self):
        pass

    def invalidate(self):
        self.loaded = False
        if self.isVisible():
            self.on_show()


def row(*widgets, stretch=None, spacing=12):
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    for i, w in enumerate(widgets):
        if w is None:
            lay.addStretch()
        else:
            lay.addWidget(w, stretch[i] if stretch else 0)
    return lay


def setting_row(title, desc, control):
    lay = QHBoxLayout()
    col = QVBoxLayout()
    col.setSpacing(0)
    col.addWidget(label(title))
    col.addWidget(label(desc, "muted"))
    lay.addLayout(col, 1)
    lay.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)
    return lay


class DashboardPage(Page):
    def __init__(self, ctx):
        super().__init__(ctx, "Dashboard", "Your COOL 68 at a glance")
        top = QHBoxLayout()
        top.setSpacing(16)
        dev = Card("Device")
        self.fw, self.dev_id = label("—", "value"), label("—", "value")
        for name, w in (("Firmware", self.fw), ("Device ID", self.dev_id)):
            r = QHBoxLayout()
            r.addWidget(label(name, "muted"))
            r.addStretch()
            r.addWidget(w)
            dev.lay.addLayout(r)
        dev.lay.addWidget(label("Profile", "muted"))
        self.profiles = Segmented([(f"Profile {i + 1}", i) for i in range(3)])
        self.profiles.changed.connect(self.set_profile)
        dev.lay.addWidget(self.profiles)
        dev.lay.addStretch()
        top.addWidget(dev, 2)
        quick = Card("Quick settings")
        quick.lay.addWidget(label("Polling rate", "muted"))
        self.polling = Segmented([(f"{hz} Hz", hz) for hz in cool68.POLLING_LEVELS])
        self.polling.changed.connect(self.set_polling)
        quick.lay.addWidget(self.polling)
        self.win_lock, self.mac = Toggle(), Toggle()
        self.win_lock.toggled.connect(lambda on: self.set_flag("win lock", cool68.Cool68.set_win_lock, on))
        self.mac.toggled.connect(lambda on: self.set_flag("Mac mode", cool68.Cool68.set_mac_mode, on))
        quick.lay.addLayout(setting_row("Windows key lock", "Disable the Win key while gaming", self.win_lock))
        quick.lay.addLayout(setting_row("Mac layout", "Swap Alt and Win for macOS", self.mac))
        top.addWidget(quick, 3)
        self.body.addLayout(top)
        prev = Card("Live preview", "What the backlight is doing right now")
        self.view = EffectView(240)
        self.view.clicked.connect(lambda pos, _: self.view.press(pos))
        prev.lay.addWidget(self.view, 1)
        self.body.addWidget(prev, 1)

    @guarded
    def load(self):
        kb = self.ctx.kb
        fw = kb.get_firmware_version()
        self.fw.setText(f"{fw >> 8}.{fw & 0xFF:02X}")
        self.dev_id.setText(f"{kb.get_device_id():X}")
        self.profiles.set_value(kb.get_profile())
        self.polling.set_value(kb.get_polling())
        self.win_lock.set_silent(kb.get_win_lock())
        self.mac.set_silent(kb.get_mac_mode())
        light, side = kb.get_light(), kb.get_side_light()
        self.view.static_fills = ({p: QColor(*c) for p, c in kb.get_key_colors().items() if c != (0, 0, 0)}
                                  if light["mode"] == cool68.LIGHT_CUSTOM else {})
        self.view.set_effect(light["mode"], QColor(light["r"], light["g"], light["b"]), light["mix"],
                             light["brightness"], light["speed"])
        self.view.side = (QColor(side["r"], side["g"], side["b"]), side["brightness"])

    @guarded
    def set_profile(self, idx):
        self.ctx.kb.set_profile(idx)
        self.ctx.toast(f"Switched to profile {idx + 1}")
        self.ctx.reload_all()

    @guarded
    def set_polling(self, hz):
        self.ctx.kb.set_polling(hz)
        self.ctx.toast(f"Polling rate set to {hz} Hz", "ok")
        self.ctx.reconnect_soon()

    @guarded
    def set_flag(self, name, setter, on):
        setter(self.ctx.kb, on)
        self.ctx.toast(f"{name} {'on' if on else 'off'}")


class KeymapPage(Page):
    def __init__(self, ctx):
        super().__init__(ctx, "Keymap", "Click a key, then pick what it should do")
        self.layer, self.values, self.category = 0, {}, "Letters"
        top = row(None)
        self.layers = Segmented([("Layer 0", 0), ("Fn layer 1", 1), ("Layer 2", 2)])
        self.layers.set_value(0)
        self.layers.changed.connect(self.set_layer)
        top.insertWidget(0, self.layers)
        self.restore_btn = button("Restore layer defaults", danger=True, slot=self.restore)
        top.addWidget(self.restore_btn)
        top.addWidget(button("Reload from keyboard", slot=self.invalidate))
        self.body.addLayout(top)
        self.view = KeyboardView(250)
        self.view.clicked.connect(self.on_key)
        self.body.addWidget(self.view, 2)
        pick = Card()
        self.info = label("Select a key on the keyboard above", "h2")
        pick.lay.addWidget(self.info)
        self.cats = Segmented([(c, c) for c in list(keys.catalogue()) + ["Macros", "Raw"]])
        self.cats.set_value("Letters")
        self.cats.changed.connect(self.set_category)
        self.cats_scroll = QScrollArea()
        self.cats_scroll.setWidgetResizable(True)
        self.cats_scroll.setFixedHeight(54)
        self.cats_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cats_scroll.setWidget(self.cats)
        pick.lay.addWidget(self.cats_scroll)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(8)
        self.grid.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.grid_host)
        scroll.setMinimumHeight(170)
        pick.lay.addWidget(scroll, 1)
        self.body.addWidget(pick, 3)
        self.fill_grid()

    @guarded
    def load(self):
        self.values = self.ctx.kb.get_keymap(self.layer)
        self.refresh_labels()

    def refresh_labels(self):
        self.view.labels = {p: keys.describe(v, short=True) for p, v in self.values.items()}
        self.view.update()

    @guarded
    def restore(self):
        if self.layer not in cool68.FACTORY_KEYMAP:
            self.ctx.toast("Layer 2 has no factory defaults", "info")
            return
        if QMessageBox.question(self, "Restore defaults", f"Put every key on layer {self.layer} back to the factory "
                                "assignment? Your changes to this layer will be lost.") != QMessageBox.Yes:
            return
        self.ctx.kb.restore_layer(self.layer)
        self.load()
        self.ctx.toast(f"Layer {self.layer} restored to factory defaults")

    def set_layer(self, layer):
        self.layer = layer
        self.restore_btn.setEnabled(layer in cool68.FACTORY_KEYMAP)
        self.view.selected.clear()
        self.info.setText("Select a key on the keyboard above")
        self.load()

    def on_key(self, pos, additive):
        if additive:
            self.view.selected ^= {pos}
        else:
            self.view.selected = {pos}
        self.view.update()
        sel = sorted(self.view.selected)
        if len(sel) == 1:
            v = self.values.get(sel[0])
            self.info.setText(f"{cool68.KEY_NAMES.get(sel[0], sel[0])}  →  {keys.describe(v)}"
                              + (f"    (0x{v:08X})" if v is not None else ""))
        else:
            self.info.setText(f"{len(sel)} keys selected")

    def set_category(self, c):
        self.category = c
        self.fill_grid()

    def fill_grid(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        if self.category == "Raw":
            self.raw = QLineEdit()
            self.raw.setPlaceholderText("32-bit hex, e.g. 00000004")
            self.grid.addWidget(self.raw, 0, 0, 1, 3)
            self.grid.addWidget(button("Assign", accent=True, slot=self.assign_raw), 0, 3)
            self.grid.addWidget(button("Disable key", slot=lambda: self.assign(0)), 0, 4)
            return
        if self.category == "Macros":
            macros = self.ctx.macros.names()
            self.count = spin(*cool68.MACRO_REPEAT_COUNT)
            self.grid.addWidget(label("Play the macro this many times:", "muted"), 0, 0, 1, 2)
            self.grid.addWidget(self.count, 0, 2)
            if not macros:
                self.grid.addWidget(label("No macros yet. Create one on the Macros page and upload it.", "muted"), 1, 0, 1, 5)
            for i, name in enumerate(macros):
                b = button(name, tile=True)
                b.clicked.connect(lambda _=False, i=i: self.assign(macro_key(MACRO_REPEAT, self.count.value(), i)))
                self.grid.addWidget(b, 1 + i // 5, i % 5)
            return
        for i, (name, value) in enumerate(keys.catalogue()[self.category]):
            b = button(name, tile=True)
            b.clicked.connect(lambda _=False, v=value: self.assign(v))
            self.grid.addWidget(b, i // 8, i % 8)

    def assign_raw(self):
        try:
            self.assign(int(self.raw.text(), 16))
        except ValueError:
            self.ctx.toast("That is not a valid hex value", "error")

    @guarded
    def assign(self, value):
        sel = sorted(self.view.selected)
        if not sel:
            self.ctx.toast("Select a key first", "info")
            return
        for pos in sel:
            old = self.values.get(pos, 0)
            if old >> 24 == 0x0D and value != old:
                if QMessageBox.question(self, "Replace the Fn key?", "Replacing Fn can lock you out of the Fn layer. Continue?"
                                        ) != QMessageBox.Yes:
                    return
        self.ctx.kb.set_keys(self.layer, {p: value for p in sel})
        for p in sel:
            self.values[p] = value
        self.refresh_labels()
        self.on_key(sel[0], False) if len(sel) == 1 else None
        self.ctx.toast(f"Assigned {keys.describe(value)} to {len(sel)} key{'s' if len(sel) > 1 else ''}")


class EffectPicker(QWidget):
    """Effect tiles grouped by what the colour controls do."""
    picked = Signal(int)

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.tiles = {}
        for name, note, modes in effects.GROUPS:
            head = QHBoxLayout()
            head.addWidget(label(name.upper(), "muted"))
            if note:
                n = label("·  " + note, "muted")
                head.addWidget(n)
            head.addStretch()
            lay.addLayout(head)
            grid = QGridLayout()
            grid.setSpacing(8)
            for i, m in enumerate(modes):
                b = button(LIGHT_MODES[m], tile=True)
                b.clicked.connect(lambda _=False, m=m: self.picked.emit(m))
                self.tiles[m] = b
                grid.addWidget(b, i // 4, i % 4)
            for c in range(4):
                grid.setColumnStretch(c, 1)
            lay.addLayout(grid)
            lay.addSpacing(8)
        lay.addStretch()

    def set_mode(self, m):
        for k, b in self.tiles.items():
            b.setChecked(k == m)


class ZonePanel(QWidget):
    """Colour, brightness, speed and multicolour switch for one light zone."""
    changed = Signal()

    def __init__(self, with_mix=True):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        self.picker = ColorPicker()
        self.picker.changed.connect(self._picked)
        lay.addWidget(self.picker, 1)
        self.bright = LabeledSlider("Brightness", *cool68.BRIGHTNESS_RANGE)
        self.speed = LabeledSlider("Speed", *cool68.SPEED_RANGE)
        for s_ in (self.bright, self.speed):
            s_.moving.connect(lambda _: self.changed.emit())
            lay.addWidget(s_)
        self.mix = Toggle()
        self.mix.toggled.connect(lambda _: self.changed.emit())
        self.mix_row = QWidget()
        mix_lay = QVBoxLayout(self.mix_row)
        mix_lay.setContentsMargins(0, 0, 0, 0)
        mix_lay.addLayout(setting_row("Multicolour", "The keyboard's built-in palette (a fixed yellow here). "
                                      "Picking a colour turns it off", self.mix))
        lay.insertWidget(0, self.mix_row)           # on top so it is always in view

    def _picked(self, _):
        self.set_multicolour(False)     # like the vendor app: choosing a colour means a single colour
        self.changed.emit()

    def set_multicolour(self, on, mask=None):
        """Set the multicolour switch without emitting a change."""
        self.mix.set_silent(on)

    def set_caps(self, caps):
        """Enable only the controls this effect supports."""
        self.picker.setEnabled("color" in caps)
        self.bright.setEnabled("brightness" in caps)
        self.speed.setEnabled("speed" in caps)
        self.mix_row.setEnabled("mix" in caps)

    def state(self):
        mix = 7 if self.mix.isChecked() else 0     # the keyboard only knows 0 (single colour) and 7 (multicolour)
        return self.picker.color(), int(self.bright.value()), int(self.speed.value()), mix

    def load(self, d):
        # a stored colour of pure black would turn the light off as soon as the user picks an effect, so show white
        rgb = (d["r"], d["g"], d["b"]) if (d["r"], d["g"], d["b"]) != (0, 0, 0) else (255, 255, 255)
        self.picker.set_color(QColor(*rgb))
        self.bright.set_value(d["brightness"])
        self.speed.set_value(d["speed"])
        self.set_multicolour(d["mix"], d["mix_mask"] if d["mix"] else None)


class LightingPage(Page):
    def __init__(self, ctx):
        super().__init__(ctx, "Lighting", "Effects, side light and per-key colours")
        self.back_mode, self.side_mode, self.colors = 1, 0, {}
        self.tabs = Segmented([("Backlight", 0), ("Side light", 1), ("Per-key colours", 2)])
        self.tabs.set_value(0)
        self.tabs.changed.connect(self.switch)
        self.body.addWidget(self.tabs)
        prev = Card()
        prev.lay.setContentsMargins(14, 12, 14, 10)
        self.view = EffectView(250)
        self.view.clicked.connect(self.on_key)
        prev.lay.addWidget(self.view, 1)
        self.hint = label("Preview of the effect. Click keys to see reactive effects. It is an approximation: "
                          "the keyboard can't report what it is actually showing.", "muted", True)
        prev.lay.addWidget(self.hint)
        self.body.addWidget(prev, 2)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.build_back())
        self.stack.addWidget(self.build_side())
        self.stack.addWidget(self.build_perkey())
        self.body.addWidget(self.stack, 3)
        self.timer = QTimer(self, singleShot=True, interval=130)
        self.timer.timeout.connect(self.send_live)

    # ----- panels
    def build_back(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        c1 = Card("Effect")
        self.picker = EffectPicker()
        self.picker.picked.connect(self.pick_back)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(self.picker)
        self.picker.setAutoFillBackground(False)
        sc.viewport().setAutoFillBackground(False)
        c1.lay.addWidget(sc, 1)
        c2 = Card("Colour & motion")
        self.back = ZonePanel()
        self.back.changed.connect(self.live)
        c2.lay.addWidget(self.back, 1)
        lay.addWidget(c1, 3)
        lay.addWidget(c2, 2)
        return w

    def build_side(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        c1 = Card("Side light", "The glowing edge strip around the board")
        self.side_combo = QComboBox()
        for m in range(20):
            self.side_combo.addItem(f"Effect {m}", m)
        self.side_combo.activated.connect(self.pick_side)
        c1.lay.addLayout(row(label("Effect"), self.side_combo, stretch=[0, 1]))
        c1.lay.addWidget(label("The side light's effects are not named by the keyboard, so they are numbered. "
                               "Try a few and see which you like.", "muted", True))
        c1.lay.addStretch()
        c2 = Card("Colour & motion")
        self.side = ZonePanel()
        self.side.changed.connect(self.live)
        c2.lay.addWidget(self.side, 1)
        lay.addWidget(c1, 2)
        lay.addWidget(c2, 2)
        return w

    def build_perkey(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        c1 = Card("Paint your keys", "Select keys on the preview above (Ctrl+click for several), or turn on paint-on-click.")
        self.paint_click = Toggle()
        c1.lay.addLayout(setting_row("Paint on click", "Every key you click gets the current colour", self.paint_click))
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, (text, slot, kw) in enumerate((
                ("Paint selected", self.paint_selected, {}), ("Fill all", self.fill_all, {}),
                ("Clear all", self.clear_all, {}), ("Read from keyboard", self.read, {}),
                ("Send to keyboard", self.send, {"accent": True}))):
            grid.addWidget(button(text, slot=slot, **kw), i // 2, i % 2)
        c1.lay.addLayout(grid)
        c1.lay.addStretch()
        c2 = Card("Colour")
        self.pk_picker = ColorPicker()
        self.pk_picker.set_color(QColor("#ff2d55"))
        c2.lay.addWidget(self.pk_picker, 1)
        lay.addWidget(c1, 2)
        lay.addWidget(c2, 2)
        return w

    # ----- state / live updates
    def switch(self, i):
        self.stack.setCurrentIndex(i)
        self.view.selected = set()
        self.view.demo = i != 2
        if i == 2:
            if not self.colors:
                self.read()
            self.view.static_fills = self.colors
            self.view.set_effect(cool68.LIGHT_CUSTOM, QColor("white"), False, 20, 2)
        else:
            self.refresh_preview()
        self.view.update()

    def refresh_preview(self):
        c, b, sp, mix = self.back.state()
        if self.back_mode == cool68.LIGHT_CUSTOM:
            self.view.static_fills = self.colors
        self.view.set_effect(self.back_mode, c, bool(mix), b, sp)
        sc, sb, _, _ = self.side.state()
        self.view.side = (sc, sb)

    def apply_caps(self):
        bc = cool68.light_capabilities(self.back_mode)
        self.back.set_caps(bc)
        self.side.set_caps(cool68.light_capabilities(self.side_mode, side=True))

    def pick_back(self, m):
        self.back_mode = m
        self.picker.set_mode(m)
        caps = cool68.light_capabilities(m)
        if "color" not in caps and "mix" in caps:
            self.back.set_multicolour(True)     # no colour choice: the effect's own palette
        self.apply_caps()
        self.live()

    def pick_side(self, i):
        self.side_mode = i
        caps = cool68.light_capabilities(i, side=True)
        if "color" not in caps and "mix" in caps:
            self.side.set_multicolour(True)
        self.apply_caps()
        self.live()

    def live(self):
        self.refresh_preview()
        self.timer.start()

    @guarded
    def send_live(self):
        kb = self.ctx.kb
        if self.stack.currentIndex() == 1:
            c, b, sp, mix = self.side.state()
            kb.set_side_light(self.side_mode, c.red(), c.green(), c.blue(), b, sp, mix)
        else:
            c, b, sp, mix = self.back.state()
            kb.set_light(self.back_mode, c.red(), c.green(), c.blue(), b, sp, mix)

    @guarded
    def load(self):
        kb = self.ctx.kb
        d, sd = kb.get_light(), kb.get_side_light()
        self.back_mode, self.side_mode = d["mode"], sd["mode"]
        self.picker.set_mode(self.back_mode)
        self.back.load(d)
        self.side.load(sd)
        self.side_combo.setCurrentIndex(self.side_mode)
        self.apply_caps()
        if self.back_mode == cool68.LIGHT_CUSTOM:
            self.colors = kb.get_key_colors()
        self.refresh_preview()

    # ----- per-key painting
    def on_key(self, pos, additive):
        if self.stack.currentIndex() != 2:
            self.view.press(pos)
            return
        if self.paint_click.isChecked():
            self.colors[pos] = self.hex_rgb()
            self.refresh_colors()
        elif additive:
            self.view.selected ^= {pos}
        else:
            self.view.selected = {pos}

    def hex_rgb(self):
        c = self.pk_picker.color()
        return c.red(), c.green(), c.blue()

    def refresh_colors(self):
        self.view.static_fills = {p: QColor(*c) for p, c in self.colors.items() if c != (0, 0, 0)}
        self.view.tick()

    def paint_selected(self):
        for p in self.view.selected:
            self.colors[p] = self.hex_rgb()
        self.refresh_colors()

    def fill_all(self):
        self.colors = {p: self.hex_rgb() for p in KEY_POS}
        self.refresh_colors()

    def clear_all(self):
        self.colors = {p: (0, 0, 0) for p in KEY_POS}
        self.refresh_colors()

    @guarded
    def read(self):
        self.colors = self.ctx.kb.get_key_colors()
        self.refresh_colors()

    @guarded
    def send(self):
        kb = self.ctx.kb
        cur = kb.get_light()  # custom mode first, otherwise the keyboard drops the colours
        kb.set_light(cool68.LIGHT_CUSTOM, cur["r"], cur["g"], cur["b"], cur["brightness"], cur["speed"], cur["mix_mask"])
        kb.set_key_colors({p: self.colors.get(p, (0, 0, 0)) for p in KEY_POS})
        self.back_mode = cool68.LIGHT_CUSTOM
        self.picker.set_mode(self.back_mode)
        self.ctx.toast("Per-key colours sent")
