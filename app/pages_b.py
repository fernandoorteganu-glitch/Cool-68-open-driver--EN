"""Performance (Hall-effect), Macros, Advanced keys and Settings pages."""
from PySide6.QtCore import QElapsedTimer, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QCompleter, QHBoxLayout, QHeaderView, QInputDialog,
                               QLineEdit, QListWidget, QMessageBox, QSpinBox, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget, QLabel)

import cool68
from cool68 import KEY_NAMES, KEY_POS, MACRO_KEYS

from . import __version__, keys, theme
from .pages_a import Page, guarded, row, setting_row
from .store import key_name, text_to_events
from .widgets import (Card, HeatLegend, KeyboardView, LabeledSlider, Segmented, Toggle, TravelGauge, button, heat_color,
                      label, spin)

PRESETS = {  # actuation (mm), rapid trigger on/off with release/press distance, dead zones (mm)
    "Default": dict(act=1.0, rt=False, up=0.3, down=0.3, top=0.0, bot=0.0),
    "Typing": dict(act=1.5, rt=False, up=0.3, down=0.3, top=0.0, bot=0.0),
    "Gaming": dict(act=0.8, rt=True, up=0.2, down=0.2, top=0.0, bot=0.0),
    "Competitive": dict(act=0.4, rt=True, up=0.1, down=0.1, top=0.05, bot=0.0),
}
DEFAULTS = dict(travel=(200, False), rt=dict(enable=False, up=2, down=2, use_global=True),
                safe=dict(up=26, down=25, use_global=False, enable=False))


class PerformancePage(Page):
    def __init__(self, ctx):
        super().__init__(ctx, "Performance", "Hall-effect tuning: actuation point, rapid trigger and dead zone per key")
        self.travel, self.rt, self.safe = {}, {}, {}
        self.prec = 5
        left = Card("Keys", "Select keys to tune. Colour shows how deep each key actuates.")
        self.view = KeyboardView(300)
        self.view.solid = True
        self.view.glow = False
        self.view.tint = False
        self.view.clicked.connect(self.on_key)
        left.lay.addWidget(self.view, 1)
        left.lay.addWidget(HeatLegend())
        sel = QHBoxLayout()
        sel.setSpacing(8)
        sel.addWidget(button("Select all", slot=self.select_all))
        sel.addWidget(button("WASD", slot=lambda: self.select_set([30, 43, 44, 45])))
        sel.addWidget(button("Clear selection", slot=lambda: self.select_set([])))
        sel.addStretch()
        sel.addWidget(button("Reload from keyboard", slot=self.invalidate))
        left.lay.addLayout(sel)
        right = Card("Tuning")
        top = QHBoxLayout()
        top.setSpacing(28)
        self.gauge = TravelGauge()
        gcard = Card("Switch travel")
        gcard.setFixedWidth(430)
        self.live_toggle = Toggle()
        self.live_toggle.toggled.connect(self.toggle_live)
        gcard.lay.insertLayout(1, setting_row("Live view", "Press a key and watch it move (up to 9 selected keys)", self.live_toggle))
        gcard.lay.addWidget(self.gauge, 1)          # fills the card, right under the title
        self.live_timer = QTimer(self, interval=16)
        self.live_timer.timeout.connect(self.poll_live)
        self.live_keys = []
        self.act = LabeledSlider("Actuation point", 0.1, 4.0, 0.005, 2, " mm", 2.0)
        self.rt_on = Toggle()
        self.rt_up = LabeledSlider("Release distance", 0.005, 4.0, 0.005, 2, " mm", 0.3)
        self.rt_down = LabeledSlider("Press distance", 0.005, 4.0, 0.005, 2, " mm", 0.3)
        self.safe_top = LabeledSlider("Dead zone at the top", 0.0, 0.5, 0.005, 2, " mm", 0.0)
        self.safe_bot = LabeledSlider("Dead zone at the bottom", 0.0, 0.5, 0.005, 2, " mm", 0.0)
        c1 = QVBoxLayout()
        c1.setSpacing(14)
        c1.addWidget(self.act)
        c1.addLayout(setting_row("Rapid trigger", "Re-fires the moment you lift and press again", self.rt_on))
        c1.addWidget(self.rt_up)
        c1.addWidget(self.rt_down)
        c1.addStretch()
        c2 = QVBoxLayout()
        c2.setSpacing(14)
        c2.addWidget(self.safe_top)
        c2.addWidget(self.safe_bot)
        c2.addSpacing(6)
        c2.addWidget(label("Quick presets (then press Apply)", "muted"))
        presets = QHBoxLayout()
        presets.setSpacing(8)
        for name, vals in PRESETS.items():
            presets.addWidget(button(name, chip=True, slot=lambda v=vals: self.preset(v)))
        presets.addStretch()
        c2.addLayout(presets)
        c2.addStretch()
        c2.addWidget(button("Apply to selected", accent=True, slot=self.apply_selected))
        c2.addWidget(button("Apply to all keys", slot=self.apply_all))
        c2.addWidget(button("Reset selected", slot=self.reset_selected))
        top.addLayout(c1, 1)
        top.addLayout(c2, 1)
        right.lay.addLayout(top, 1)
        for w in (self.act, self.rt_up, self.rt_down, self.safe_top, self.safe_bot):
            w.moving.connect(lambda _: self.update_gauge())
        self.rt_on.toggled.connect(lambda _: self.update_gauge())
        self.body.addWidget(left, 5)                 # the keyboard gets the whole width
        lower = QHBoxLayout()
        lower.setSpacing(16)
        lower.addWidget(right, 1)
        lower.addWidget(gcard)
        self.body.addLayout(lower, 4)

    @guarded
    def load(self):
        kb = self.ctx.kb
        self.prec = kb.get_precision()[1]
        step = self.prec / 1000.0
        for s, lo, hi in ((self.act, 0.1, 4.0), (self.rt_up, step, 4.0), (self.rt_down, step, 4.0),
                          (self.safe_top, 0.0, 0.5), (self.safe_bot, 0.0, 0.5)):
            s.step = step
            s.set_range(lo, hi)
        self.travel, self.rt, self.safe = kb.get_travel(), kb.get_rapid_trigger(), kb.get_safe_area()
        self.refresh_heat()
        if not self.view.selected:
            self.view.selected = {30}
        self.show_key(min(self.view.selected))

    def mm(self, raw):
        return cool68.raw_to_mm(raw, self.prec)

    def raw(self, mm):
        return cool68.mm_to_raw(mm, self.prec)

    def refresh_heat(self):
        fills, sub = {}, {}
        for pos, (d, _) in self.travel.items():
            mm = self.mm(d)
            fills[pos] = heat_color(mm)
            sub[pos] = f"{mm:.2f}" + ("·RT" if self.rt.get(pos, {}).get("enable") else "")
        self.view.fills, self.view.sub = fills, sub
        self.view.update()

    def on_key(self, pos, additive):
        if additive:
            self.view.selected ^= {pos}
        else:
            self.view.selected = {pos}
        self.view.update()
        if self.view.selected:
            self.show_key(pos if pos in self.view.selected else min(self.view.selected))

    def select_all(self):
        self.select_set(KEY_POS)

    def select_set(self, positions):
        self.view.selected = set(positions)
        self.view.update()
        if positions:
            self.show_key(positions[0])

    def show_key(self, pos):
        if self.live_toggle.isChecked():
            self.retrack()
        if pos not in self.travel:
            return
        self.act.set_value(self.mm(self.travel[pos][0]))
        r, s = self.rt[pos], self.safe[pos]
        self.rt_on.set_silent(r["enable"])
        self.rt_up.set_value(max(self.mm(r["up"]), self.rt_up.lo))
        self.rt_down.set_value(max(self.mm(r["down"]), self.rt_down.lo))
        self.safe_top.set_value(self.mm(s["up"]) if s["enable"] else 0.0)
        self.safe_bot.set_value(self.mm(s["down"]) if s["enable"] else 0.0)
        self.update_gauge()

    def update_gauge(self):
        self.gauge.set_values(self.act.value(), self.rt_on.isChecked(), self.rt_up.value(), self.rt_down.value(),
                              self.safe_top.value(), self.safe_bot.value())

    def _entries(self):
        a = self.raw(self.act.value())
        rt = dict(enable=self.rt_on.isChecked(), up=self.raw(self.rt_up.value()), down=self.raw(self.rt_down.value()))
        sa = dict(up=self.raw(self.safe_top.value()), down=self.raw(self.safe_bot.value()),
                  enable=self.safe_top.value() > 0 or self.safe_bot.value() > 0)
        return a, rt, sa

    @guarded
    def write(self, positions, use_global):
        a, rt, sa = self._entries()
        kb = self.ctx.kb
        t = {p: (a, use_global) for p in positions}
        r = {p: dict(rt, use_global=use_global) for p in positions}
        s = {p: dict(sa, use_global=use_global) for p in positions}
        kb.set_travel(t)
        kb.set_rapid_trigger(r)
        kb.set_safe_area(s)
        self.travel.update(t)
        self.rt.update(r)
        self.safe.update(s)
        self.refresh_heat()
        self.ctx.toast(f"Applied to {len(positions)} key{'s' if len(positions) != 1 else ''}")

    def apply_selected(self):
        if not self.view.selected:
            self.ctx.toast("Select at least one key", "info")
            return
        self.write(sorted(self.view.selected), False)

    def apply_all(self):
        if QMessageBox.question(self, "Apply to all keys", "Use these values on every key?") == QMessageBox.Yes:
            self.write(list(KEY_POS), True)

    def preset(self, v):
        self.act.set_value(v["act"])
        self.rt_on.set_silent(v["rt"])
        self.rt_up.set_value(max(v["up"], self.rt_up.lo))
        self.rt_down.set_value(max(v["down"], self.rt_down.lo))
        self.safe_top.set_value(v["top"])
        self.safe_bot.set_value(v["bot"])
        self.update_gauge()

    # ---- live travel
    def _live_positions(self):
        sel = sorted(self.view.selected) or [30]
        return sel[:cool68.LIVE_MAX_KEYS]

    @guarded
    def toggle_live(self, on):
        kb = self.ctx.kb
        if on:
            self.live_keys = self._live_positions()
            if len(self.view.selected) > cool68.LIVE_MAX_KEYS:
                self.ctx.toast(f"Following the first {cool68.LIVE_MAX_KEYS} selected keys", "info")
            kb.live_start(self.live_keys)
            self.live_timer.start()
        else:
            self.stop_live()

    def stop_live(self):
        self.live_timer.stop()
        self.view.live = {}
        self.view.update()
        self.gauge.set_live(None)
        self.live_toggle.set_silent(False)
        try:
            self.ctx.kb.live_stop()
        except Exception:
            pass

    def retrack(self):
        keys = self._live_positions()
        if keys != self.live_keys:
            self.live_keys = keys
            self.view.live = {}
            try:
                self.ctx.kb.live_track(keys)
            except Exception:
                self.stop_live()

    def poll_live(self):
        try:
            events = self.ctx.kb.live_poll()
        except Exception as e:                  # unplugged or the stream died
            self.stop_live()
            self.ctx.fail(e)
            return
        if not events:
            return
        primary = self.live_keys[0] if self.live_keys else None
        for pos, dist, ad, pressed in events:
            if pos not in self.live_keys:
                continue
            mm = cool68.raw_to_mm(dist, self.prec)
            self.view.live[pos] = min(mm / 4.0, 1.0)
            if pos == (min(self.view.selected) if self.view.selected else primary):
                self.gauge.set_live(mm, pressed)
        self.view.update()

    def on_leave(self):
        if self.live_toggle.isChecked():
            self.stop_live()

    def reset_selected(self):
        d = DEFAULTS
        self.act.set_value(self.mm(d["travel"][0]))
        self.rt_on.set_silent(False)
        self.rt_up.set_value(self.mm(d["rt"]["up"]))
        self.rt_down.set_value(self.mm(d["rt"]["down"]))
        self.safe_top.set_value(0.0)
        self.safe_bot.set_value(0.0)
        self.update_gauge()
        self.apply_selected()


class KeyChooser(QComboBox):
    """Searchable list of everything a key can send (letters, modifiers, media...)."""

    def __init__(self, skip=("Lighting / Fn", "Mouse", "Shortcuts")):
        super().__init__()
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        for cat, items in keys.catalogue().items():
            if cat in skip:
                continue
            for name, value in items:
                self.addItem(f"{name}   ·  {cat}", value)
        c = QCompleter(self.model(), self)
        c.setCaseSensitivity(Qt.CaseInsensitive)
        c.setFilterMode(Qt.MatchContains)
        self.setCompleter(c)

    def value(self):
        i = self.findText(self.currentText())
        return self.itemData(i if i >= 0 else self.currentIndex())

    def set_value(self, v):
        i = self.findData(v)
        if i >= 0:
            self.setCurrentIndex(i)


class MacrosPage(Page):
    def __init__(self, ctx):
        super().__init__(ctx, "Macros", "Record or build key sequences, then upload them to the keyboard")
        self.store = ctx.macros
        self.current = -1
        self.recording = False
        self.clock = QElapsedTimer()
        left = Card("Your macros")
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.select)
        left.lay.addWidget(self.list, 1)
        lb = QHBoxLayout()
        lb.addWidget(button("New", accent=True, slot=self.new))
        lb.addWidget(button("Rename", slot=self.rename))
        lb.addWidget(button("Delete", danger=True, slot=self.delete))
        left.lay.addLayout(lb)
        left.lay.addWidget(button("Upload all to keyboard", accent=True, slot=self.upload))
        left.lay.addWidget(label("Uploading replaces every macro stored on the keyboard.", "muted", True))
        right = Card("Steps")
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Action", "Key", "Wait after (ms)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        right.lay.addWidget(self.table, 1)
        self.recorder = QLabel("Click “Record”, then type in this box")
        self.recorder.setAlignment(Qt.AlignCenter)
        self.recorder.setFixedHeight(54)
        self.recorder.setFocusPolicy(Qt.StrongFocus)
        self.recorder.setStyleSheet(f"background:{theme.CARD_HI}; border:1px dashed {theme.BORDER}; border-radius:12px; color:{theme.MUTED};")
        self.recorder.keyPressEvent = lambda e: self.record_key(e, True)
        self.recorder.keyReleaseEvent = lambda e: self.record_key(e, False)
        self.recorder.focusNextPrevChild = lambda nxt: False if self.recording else QLabel.focusNextPrevChild(self.recorder, nxt)
        right.lay.addWidget(self.recorder)
        rb = QHBoxLayout()
        self.rec_btn = button("● Record", accent=True, slot=self.toggle_record)
        rb.addWidget(self.rec_btn)
        self.key = QComboBox()
        self.key.addItems(MACRO_KEYS)
        self.key.setEditable(True)
        self.key.setCurrentText("KeyA")
        self.down = Segmented([("Press", True), ("Release", False)])
        self.down.set_value(True)
        self.delay = spin(0, cool68.MACRO_DELAY_MAX_MS, 20, " ms")
        for w in (self.key, self.down, self.delay):
            rb.addWidget(w)
        rb.addWidget(button("Add step", slot=self.add_step))
        right.lay.addLayout(rb)
        tb = QHBoxLayout()
        self.text = QLineEdit()
        self.text.setPlaceholderText("…or type text to turn into steps")
        tb.addWidget(self.text, 1)
        tb.addWidget(button("Add text", slot=self.add_text))
        tb.addWidget(button("Remove step", slot=self.remove_step))
        tb.addWidget(button("Clear", danger=True, slot=self.clear))
        right.lay.addLayout(tb)
        lay = QHBoxLayout()
        lay.setSpacing(16)
        lay.addWidget(left, 2)
        lay.addWidget(right, 5)
        self.body.addLayout(lay, 1)

    def load(self):
        self.list.blockSignals(True)
        self.list.clear()
        self.list.addItems(self.store.names())
        self.list.blockSignals(False)
        if self.store.macros:
            self.list.setCurrentRow(max(self.current, 0))
        else:
            self.current = -1
            self.show_steps()

    def select(self, i):
        self.current = i
        self.show_steps()

    def events(self):
        return self.store.macros[self.current]["events"] if 0 <= self.current < len(self.store.macros) else None

    def show_steps(self):
        ev = self.events() or []
        self.table.setRowCount(len(ev))
        for r, e in enumerate(ev):
            for c, text in enumerate(("▼ press" if e["down"] else "▲ release", e["key"], str(e["delay"]))):
                self.table.setItem(r, c, QTableWidgetItem(text))
        self.table.scrollToBottom()

    def new(self):
        name, ok = QInputDialog.getText(self, "New macro", "Name:", text=f"Macro {len(self.store.macros) + 1}")
        if ok and name.strip():
            self.store.add(name.strip()[:cool68.MACRO_NAME_MAX])
            self.current = len(self.store.macros) - 1
            self.load()
            self.ctx.refresh_macro_lists()

    def rename(self):
        if self.events() is None:
            return
        name, ok = QInputDialog.getText(self, "Rename", "Name:", text=self.store.macros[self.current]["name"])
        if ok and name.strip():
            self.store.macros[self.current]["name"] = name.strip()[:cool68.MACRO_NAME_MAX]
            self.store.save()
            self.load()
            self.ctx.refresh_macro_lists()

    def delete(self):
        if self.events() is not None and QMessageBox.question(self, "Delete macro", "Delete this macro?") == QMessageBox.Yes:
            self.store.remove(self.current)
            self.current = min(self.current, len(self.store.macros) - 1)
            self.load()
            self.ctx.refresh_macro_lists()

    def commit(self):
        self.store.save()
        self.show_steps()

    def add_step(self):
        ev = self.events()
        if ev is None or self.key.currentText() not in MACRO_KEYS:
            self.ctx.toast("Create a macro and choose a valid key first", "info")
            return
        ev.append({"key": self.key.currentText(), "down": bool(self.down.group.checkedButton() is self.down.buttons[True]),
                   "delay": self.delay.value()})
        self.commit()

    def add_text(self):
        ev = self.events()
        if ev is not None:
            ev.extend(text_to_events(self.text.text()))
            self.text.clear()
            self.commit()

    def remove_step(self):
        ev = self.events()
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            del ev[r]
        self.commit()

    def clear(self):
        if self.events():
            self.events().clear()
            self.commit()

    def toggle_record(self):
        if self.events() is None:
            self.ctx.toast("Create a macro first", "info")
            return
        self.recording = not self.recording
        self.rec_btn.setText("■ Stop" if self.recording else "● Record")
        if self.recording:
            self.recorder.setText("Recording… press keys in here")
            self.recorder.setStyleSheet(f"background:{theme.CARD_HI}; border:2px solid {theme.BAD}; border-radius:12px; color:white;")
            self.recorder.setFocus()
            self.clock.start()
            self.pressed = set()
        else:
            self.recorder.setText("Click “Record”, then type in this box")
            self.recorder.setStyleSheet(f"background:{theme.CARD_HI}; border:1px dashed {theme.BORDER}; border-radius:12px; color:{theme.MUTED};")

    def record_key(self, e, down):
        if not self.recording or e.isAutoRepeat():
            return
        name = key_name(e)
        if name is None:
            return
        ev = self.events()
        if ev:  # time since the previous step becomes that step's "wait after"
            ev[-1]["delay"] = min(max(self.clock.restart(), 1), cool68.MACRO_DELAY_MAX_MS)
        else:
            self.clock.restart()
        ev.append({"key": name, "down": down, "delay": 20})
        self.commit()

    @guarded
    def upload(self):
        if not self.store.macros:
            self.ctx.toast("No macros to upload", "info")
            return
        if QMessageBox.question(self, "Upload macros", "This replaces all macros on the keyboard. Continue?") != QMessageBox.Yes:
            return
        self.ctx.kb.upload_macros(self.store.for_device())
        self.ctx.toast(f"Uploaded {len(self.store.macros)} macro(s). Assign them on the Keymap page.")


ADV_ABBR = {"toggle": "TGL", "mod_tap": "MT", "socd": "SOCD", "multi": "MPT", "dks": "DKS", "end": "END"}


class AdvancedPage(Page):
    def __init__(self, ctx):
        super().__init__(ctx, "Advanced keys", "Toggle, tap/hold, SOCD and multi-point behaviours")
        self.layer = 0
        self.existing = {}
        top = row(None)
        self.layers = Segmented([("Layer 0", 0), ("Fn layer 1", 1), ("Layer 2", 2)])
        self.layers.set_value(0)
        self.layers.changed.connect(self.set_layer)
        top.insertWidget(0, self.layers)
        self.body.addLayout(top)
        left = Card("Keys", "Tags show keys that already have a behaviour")
        self.view = KeyboardView(170)
        self.view.clicked.connect(self.on_key)
        left.lay.addWidget(self.view, 1)
        right = Card("Behaviour")
        self.kind = Segmented([("Toggle", "toggle"), ("Tap / hold", "mod_tap"), ("SOCD", "socd"), ("Multi-point", "multi")])
        self.kind.set_value("toggle")
        self.kind.changed.connect(lambda k: self.stack.setCurrentIndex(["toggle", "mod_tap", "socd", "multi"].index(k)))
        head = QHBoxLayout()
        head.addWidget(self.kind)
        head.addStretch()
        head.addWidget(button("Remove from key", danger=True, slot=self.remove))
        head.addWidget(button("Apply", accent=True, slot=self.apply))
        right.lay.addLayout(head)
        self.stack = QStackedWidget()
        self.build_forms()
        right.lay.addWidget(self.stack, 1)
        self.note = label("Select a key", "muted", True)
        right.lay.addWidget(self.note)
        self.body.addWidget(left, 2)
        self.body.addWidget(right, 3)

    def build_forms(self):
        def page(*rows):
            w = QWidget()
            lay = QVBoxLayout(w)
            lay.setContentsMargins(0, 8, 0, 0)
            lay.setSpacing(10)
            for r in rows:
                lay.addWidget(r) if isinstance(r, QWidget) else lay.addLayout(r)
            lay.addStretch()
            self.stack.addWidget(w)
        self.t_key, self.t_delay = KeyChooser(), LabeledSlider("Hold time", 0, 1000, 1, 0, " ms", 200)
        page(label("Tap the key to toggle it on/off (like a latch). Hold for normal behaviour.", "muted", True),
             label("Key to send"), self.t_key, self.t_delay)
        self.m_hold, self.m_tap = KeyChooser(), KeyChooser()
        self.m_delay = LabeledSlider("Hold time", 0, 1000, 1, 0, " ms", 200)
        page(label("One key, two jobs: a quick tap sends one thing, holding sends another.", "muted", True),
             label("While held"), self.m_hold, label("On tap"), self.m_tap, self.m_delay)
        self.s_mode = QComboBox()
        for v, name in cool68.SOCD_MODES.items():
            self.s_mode.addItem(name, v)
        page(label("Pick two keys on the keyboard (Ctrl+click the second). When both are pressed, this decides who wins.", "muted", True),
             label("When both keys are down"), self.s_mode)
        self.p_keys, self.p_dist = [KeyChooser() for _ in range(3)], []
        rows = [label("One key, up to three actions at different press depths.", "muted", True)]
        for i, kc in enumerate(self.p_keys):
            s = LabeledSlider(f"Action {i + 1} depth", 0.1, 4.0, 0.005, 2, " mm", 0.5 + i * 0.5)
            self.p_dist.append(s)
            rows += [kc, s]
        page(*rows)

    @guarded
    def load(self):
        self.read()

    def read(self):
        kb = self.ctx.kb
        self.existing = {p: kb.get_advanced_key(self.layer, p) for p in kb.list_advanced_keys(self.layer)}
        self.view.sub = {p: ADV_ABBR.get(a["type"], a["type"]) for p, a in self.existing.items()}
        self.view.fills = {p: QColor(theme.ACCENT) for p in self.existing}
        self.view.update()

    def set_layer(self, layer):
        self.layer = layer
        self.load()

    def on_key(self, pos, additive):
        if additive:
            self.view.selected ^= {pos}
        else:
            self.view.selected = {pos}
        self.view.update()
        cur = self.existing.get(pos)
        self.note.setText(f"{KEY_NAMES.get(pos)}: " + (f"currently {ADV_ABBR.get(cur['type'], cur['type'])}" if cur else "no behaviour set"))
        if cur and cur["type"] in ("toggle", "mod_tap"):
            self.kind.set_value(cur["type"])
            self.stack.setCurrentIndex(0 if cur["type"] == "toggle" else 1)
            if cur["type"] == "toggle":
                self.t_key.set_value(cur["value"])
                self.t_delay.set_value(cur["delay"])
            else:
                self.m_hold.set_value(cur["pressed"])
                self.m_tap.set_value(cur["click"])
                self.m_delay.set_value(cur["delay"])

    @guarded
    def apply(self):
        sel = sorted(self.view.selected)
        kb, kind = self.ctx.kb, next(k for k, b in self.kind.buttons.items() if b.isChecked())
        if not sel:
            self.ctx.toast("Select a key first", "info")
            return
        if kind == "toggle":
            for p in sel:
                kb.set_toggle_key(self.layer, p, self.t_key.value(), int(self.t_delay.value()))
        elif kind == "mod_tap":
            for p in sel:
                kb.set_mod_tap_key(self.layer, p, self.m_hold.value(), self.m_tap.value(), int(self.m_delay.value()))
        elif kind == "socd":
            if len(sel) != 2:
                self.ctx.toast("SOCD needs exactly two keys selected", "info")
                return
            kb.set_socd(self.layer, sel, self.s_mode.currentData())
        else:
            prec = kb.get_precision()[1]
            for p in sel:
                kb.set_multi_point(self.layer, p, [(kc.value(), cool68.mm_to_raw(s.value(), prec))
                                                   for kc, s in zip(self.p_keys, self.p_dist)])
        self.read()
        self.ctx.toast("Behaviour applied")

    @guarded
    def remove(self):
        for p in sorted(self.view.selected):
            self.ctx.kb.remove_advanced_key(self.layer, p)
        self.read()
        self.ctx.toast("Behaviour removed")


class SettingsPage(Page):
    def __init__(self, ctx):
        super().__init__(ctx, "Settings", "Polling rate, power, behaviour and profiles")
        cols = QHBoxLayout()
        cols.setSpacing(16)
        a = Card("Performance & power")
        a.lay.addWidget(label("Polling rate", "muted"))
        self.polling = Segmented([(f"{hz} Hz", hz) for hz in cool68.POLLING_LEVELS])
        self.polling.changed.connect(self.set_polling)
        a.lay.addWidget(self.polling)
        a.lay.addWidget(label("Higher rates feel snappier but use more CPU. The keyboard is a Hall-effect board that supports up to 8000 Hz.", "muted", True))
        self.sleep = QComboBox()
        self.sleep.addItem("Choose…", None)
        for name, v in cool68.SLEEP_LEVELS.items():
            self.sleep.addItem(name, v)
        self.sleep.activated.connect(self.set_sleep)
        a.lay.addLayout(setting_row("Sleep after", "The keyboard can't report this, so it shows blank until you set it", self.sleep))
        self.toggles = {}
        b = Card("Behaviour")
        for key, title, desc, getter, setter in (
                ("win", "Windows key lock", "Ignore the Win key", cool68.Cool68.get_win_lock, cool68.Cool68.set_win_lock),
                ("mac", "Mac layout", "Swap Alt and Win for macOS", cool68.Cool68.get_mac_mode, cool68.Cool68.set_mac_mode),
                ("combo", "Key-combo mode", "Vendor setting for multi-key combos", cool68.Cool68.get_key_combo, cool68.Cool68.set_key_combo),
                ("cal", "Auto calibration", "Let the keyboard re-learn its sensor range", cool68.Cool68.get_auto_calibrate, cool68.Cool68.set_auto_calibrate),
                ("over", "Overdrive", "Vendor performance mode", cool68.Cool68.get_overdrive, cool68.Cool68.set_overdrive)):
            t = Toggle()
            t.toggled.connect(lambda on, s=setter, n=title: self.flag(s, n, on))
            self.toggles[key] = (t, getter)
            b.lay.addLayout(setting_row(title, desc, t))
        a.lay.addStretch()
        b.lay.addStretch()
        cols.addWidget(a, 1)
        cols.addWidget(b, 1)
        self.body.addLayout(cols)
        c = Card("Profiles", "Three separate sets of settings. Names are stored on the keyboard.")
        self.names = [QLineEdit() for _ in range(3)]
        for i, e in enumerate(self.names):
            e.setPlaceholderText(f"Profile {i + 1}")
            e.setMaxLength(cool68.PROFILE_NAME_MAX)
            c.lay.addLayout(row(label(f"Profile {i + 1}"), e, stretch=[0, 1]))
        c.lay.addLayout(row(button("Save names", accent=True, slot=self.save_names), None))
        d = Card("Sensors")
        self.cal = label("Read the recorded min/max sensor values for every key.", "muted", True)
        d.lay.addWidget(self.cal)
        d.lay.addWidget(button("Read calibration", slot=self.read_cal))
        d.lay.addStretch()
        c.lay.addStretch()
        bottom = QHBoxLayout()
        bottom.setSpacing(16)
        bottom.addWidget(c, 1)
        bottom.addWidget(d, 1)
        self.body.addLayout(bottom)
        about = Card("About")
        about.lay.addWidget(label(f"COOL 68 Control Center  ·  version {__version__}"))
        about.lay.addWidget(label("An unofficial, open-source tool for the Dareu COOL 68. It is not made by or affiliated "
                                  "with Dareu. It only sends configuration commands and never flashes firmware. "
                                  "Use it at your own risk.", "muted", True))
        self.body.addWidget(about)
        self.body.addStretch()

    @guarded
    def load(self):
        kb = self.ctx.kb
        self.polling.set_value(kb.get_polling())
        for t, getter in self.toggles.values():
            t.set_silent(getter(kb))
        for i, e in enumerate(self.names):
            e.setText(kb.get_profile_name(i) or "")

    @guarded
    def set_polling(self, hz):
        self.ctx.kb.set_polling(hz)
        self.ctx.toast(f"Polling rate set to {hz} Hz")
        self.ctx.reconnect_soon()

    @guarded
    def set_sleep(self, i):
        if self.sleep.itemData(i) is not None:
            self.ctx.kb.set_sleep(self.sleep.itemData(i))
            self.ctx.toast(f"Sleep after {self.sleep.itemText(i)}")

    @guarded
    def flag(self, setter, name, on):
        setter(self.ctx.kb, on)
        self.ctx.toast(f"{name} {'on' if on else 'off'}")

    @guarded
    def save_names(self):
        for i, e in enumerate(self.names):
            if e.text().strip():
                self.ctx.kb.set_profile_name(i, e.text().strip())
        self.ctx.toast("Profile names saved")

    @guarded
    def read_cal(self):
        r = self.ctx.kb.get_calibration_range()
        lo = min(v[0] for v in r.values())
        hi = max(v[1] for v in r.values())
        bad = [KEY_NAMES[p] for p, (a, b) in r.items() if b - a < 4000]
        self.cal.setText(f"{len(r)} keys. Sensor range {lo}–{hi}. "
                         + (f"Small range on: {', '.join(bad)}." if bad else "All keys look healthy."))
