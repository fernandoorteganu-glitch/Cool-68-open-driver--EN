"""Custom-painted widgets: keyboard, colour wheel, toggle, travel gauge, toast, nav button."""
import math
import random
import time

from PySide6.QtCore import (QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, QVariantAnimation,
                            Signal)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QFont, QFontMetrics, QLinearGradient, QPainter,
                           QPainterPath, QPen, QRadialGradient)
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSlider, QVBoxLayout, QWidget)

from . import effects, theme
from cool68 import KEY_NAMES

# (pos, width in key units) per row; every row is 16 units wide
ROWS = [
    [(1, 1)] + [(p, 1) for p in range(15, 27)] + [(27, 2), (98, 1)],
    [(28, 1.5)] + [(p, 1) for p in range(29, 41)] + [(41, 1.5), (99, 1)],
    [(42, 1.75)] + [(p, 1) for p in range(43, 54)] + [(54, 2.25), (102, 1)],
    [(55, 2.25)] + [(p, 1) for p in range(56, 66)] + [(66, 1.75), (74, 1), (103, 1)],
    [(67, 1.25), (68, 1.25), (69, 1.25), (70, 6.25), (71, 1), (72, 1), (73, 1), (76, 1), (75, 1), (77, 1)],
]


def _luminance(c):
    c = QColor(c)
    return 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()


HEAT_STOPS = [(0.1, "#ff4d6d"), (0.5, "#ff9f43"), (1.0, "#ffd84d"), (2.0, "#5ee6a8"), (4.0, "#5aa9ff")]


def heat_color(mm):
    """Heat-map colour for an actuation distance: hot pink (very sensitive) to blue (deep)."""
    mm = min(max(mm, HEAT_STOPS[0][0]), HEAT_STOPS[-1][0])
    for (a, ca), (b, cb) in zip(HEAT_STOPS, HEAT_STOPS[1:]):
        if mm <= b:
            return theme.mix(ca, cb, (mm - a) / (b - a))
    return QColor(HEAT_STOPS[-1][1])


class HeatLegend(QWidget):
    """Colour bar explaining the actuation heat map."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(40)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        bar = QRectF(8, 4, w - 16, 12)
        g = QLinearGradient(bar.left(), 0, bar.right(), 0)
        for mm, c in HEAT_STOPS:
            g.setColorAt((mm - 0.1) / 3.9, QColor(c))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(bar, 6, 6)
        p.setFont(theme.ui_font(7))
        p.setPen(QColor(theme.MUTED))
        for mm, txt in ((0.1, "0.1 mm  sensitive"), (1.0, "1"), (2.0, "2"), (3.0, "3"), (4.0, "4 mm  deep")):
            x = bar.left() + bar.width() * (mm - 0.1) / 3.9
            al = Qt.AlignLeft if mm == 0.1 else Qt.AlignRight if mm == 4.0 else Qt.AlignHCenter
            r = QRectF(x - 60, 19, 120, 16) if al == Qt.AlignHCenter else (QRectF(x, 19, 140, 16) if al == Qt.AlignLeft else QRectF(x - 140, 19, 140, 16))
            p.drawText(r, al | Qt.AlignVCenter, txt)


def _tints():
    t = {1: theme.BAD, 27: theme.ACCENT, 54: theme.ACCENT, 72: theme.ACCENT2, 70: "#3a4666"}
    for p in (28, 42, 55, 66, 67, 68, 69, 71, 73):
        t[p] = theme.BLUE
    for p in (74, 75, 76, 77):
        t[p] = theme.GOOD
    for p in (98, 99, 102, 103):
        t[p] = theme.ORANGE
    return t


KEY_TINTS = _tints()


class Card(QFrame):
    def __init__(self, title=None, subtitle=None):
        super().__init__()
        self.setObjectName("card")
        self.colors = (theme.ACCENT, theme.ACCENT2)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(20, 18, 20, 20)
        self.lay.setSpacing(12)
        if title:
            h = QLabel(title)
            h.setObjectName("h2")
            self.lay.addWidget(h)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("muted")
            s.setWordWrap(True)
            self.lay.addWidget(s)


    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 16, 16)
        p.setClipPath(path)
        g = QLinearGradient(0, 0, self.width(), 0)
        c1, c2 = QColor(self.colors[0]), QColor(self.colors[1])
        c1.setAlpha(230)
        c2.setAlpha(60)
        g.setColorAt(0, c1)
        g.setColorAt(1, c2)
        p.fillRect(QRectF(0, 0, self.width(), 3), g)
        glow = QLinearGradient(0, 0, 0, 90)
        t = QColor(self.colors[0])
        t.setAlpha(26)
        glow.setColorAt(0, t)
        t.setAlpha(0)
        glow.setColorAt(1, t)
        p.fillRect(QRectF(0, 3, self.width(), 90), glow)


class GradientLabel(QLabel):
    """Large page title painted with a two-colour gradient."""

    def __init__(self, text, colors):
        super().__init__(text)
        self.colors = colors
        self.setObjectName("gtitle")
        self.setMinimumHeight(58)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(self.font())
        w = p.fontMetrics().horizontalAdvance(self.text())
        g = QLinearGradient(0, 0, max(w, 1), 0)
        g.setColorAt(0, QColor(self.colors[0]))
        g.setColorAt(1, QColor(self.colors[1]))
        p.setPen(QPen(QBrush(g), 1))
        p.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter, self.text())


def label(text, kind=None, wrap=False):
    l = QLabel(text)
    if kind:
        l.setObjectName(kind)
    l.setWordWrap(wrap)
    return l


def button(text, accent=False, danger=False, pill=False, tile=False, chip=False, checkable=False, slot=None):
    b = QPushButton(text)
    for name, on in (("accent", accent), ("danger", danger), ("pill", pill), ("tile", tile), ("chip", chip)):
        if on:
            b.setProperty(name, True)
    b.setCheckable(checkable or pill or tile)
    b.setCursor(Qt.PointingHandCursor)
    if slot:
        b.clicked.connect(lambda *_: slot())
    return b


def spin(lo, hi, value=None, suffix=""):
    from PySide6.QtWidgets import QSpinBox
    b = QSpinBox()
    b.setRange(lo, hi)
    b.setButtonSymbols(QSpinBox.NoButtons)
    b.setSuffix(suffix)
    b.setMinimumWidth(80)
    if value is not None:
        b.setValue(value)
    return b


class Toggle(QAbstractButton):
    """Animated on/off switch."""

    def __init__(self, checked=False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 26)
        self._x = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._set)
        self.toggled.connect(self._go)

    def _set(self, v):
        self._x = v
        self.update()

    def _go(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._x)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def set_silent(self, on):
        self.blockSignals(True)
        self.setChecked(on)
        self._x = 1.0 if on else 0.0
        self.blockSignals(False)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        g = QLinearGradient(r.topLeft(), r.topRight())
        g.setColorAt(0, theme.mix("#2a3148", theme.ACCENT, self._x))
        g.setColorAt(1, theme.mix("#2a3148", theme.ACCENT2, self._x))
        p.setBrush(g)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = r.left() + 3 + (r.width() - d - 6) * self._x
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))


class Segmented(QWidget):
    """Row of pill buttons, one selected. value is whatever you pass as data."""
    changed = Signal(object)

    def __init__(self, options):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        for text, value in options:
            b = button(text, pill=True)
            self.group.addButton(b)
            self.buttons[value] = b
            b.clicked.connect(lambda _=False, v=value: self.changed.emit(v))
            lay.addWidget(b)
        lay.addStretch()

    def set_value(self, value):
        b = self.buttons.get(value)
        if b:
            b.setChecked(True)
        else:
            self.group.setExclusive(False)
            for x in self.buttons.values():
                x.setChecked(False)
            self.group.setExclusive(True)


class LabeledSlider(QWidget):
    """Slider with a caption and a live read-out. Works in real units via scale/decimals."""
    changed = Signal(float)   # fires on release / keyboard step
    moving = Signal(float)    # fires continuously

    def __init__(self, text, lo, hi, step=1.0, decimals=0, unit="", value=None):
        super().__init__()
        self.step, self.decimals, self.unit = step, decimals, unit
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        top = QHBoxLayout()
        top.addWidget(label(text))
        top.addStretch()
        self.read = label("", "value")
        top.addWidget(self.read)
        lay.addLayout(top)
        self.s = QSlider(Qt.Horizontal)
        self.s.setCursor(Qt.PointingHandCursor)
        lay.addWidget(self.s)
        self.set_range(lo, hi)
        self.s.valueChanged.connect(self._moved)
        self.s.sliderReleased.connect(lambda: self.changed.emit(self.value()))
        self.s.actionTriggered.connect(self._action)
        self.set_value(lo if value is None else value)

    def set_range(self, lo, hi):
        self.lo, self.hi = lo, hi
        self.s.setRange(0, round((hi - lo) / self.step))

    def value(self):
        return self.lo + self.s.value() * self.step

    def set_value(self, v):
        self.s.blockSignals(True)
        self.s.setValue(round((v - self.lo) / self.step))
        self.s.blockSignals(False)
        self._show()

    def _show(self):
        self.read.setText(f"{self.value():.{self.decimals}f}{self.unit}")

    def _moved(self, _):
        self._show()
        self.moving.emit(self.value())

    def _action(self, action):
        if not self.s.isSliderDown():  # keyboard / wheel step
            QTimer.singleShot(0, lambda: self.changed.emit(self.value()))


class ColorWheel(QWidget):
    changed = Signal(QColor)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(170, 170)
        self.h, self.s, self.v = 0.0, 1.0, 1.0
        self.setCursor(Qt.CrossCursor)

    def color(self):
        return QColor.fromHsvF(self.h % 1.0, self.s, self.v)

    def set_color(self, c, emit=False):
        h, s, v, _ = c.getHsvF()
        self.h = max(h, 0.0)
        self.s, self.v = s, v
        self.update()
        if emit:
            self.changed.emit(self.color())

    def set_value(self, v):
        self.v = v
        self.update()
        self.changed.emit(self.color())

    def _circle(self):
        d = min(self.width(), self.height()) - 12
        return QRectF((self.width() - d) / 2, (self.height() - d) / 2, d, d)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self._circle()
        c = r.center()
        g = QConicalGradient(c, 0)
        for i in range(7):
            g.setColorAt(i / 6, QColor.fromHsvF((i / 6) % 1.0, 1, 1))   # Qt sweeps counter-clockwise, like atan2
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(r)
        rg = QRadialGradient(c, r.width() / 2)
        rg.setColorAt(0, QColor(255, 255, 255, 255))
        rg.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(rg)
        p.drawEllipse(r)
        p.setBrush(QColor(0, 0, 0, int(255 * (1 - self.v))))
        p.drawEllipse(r)
        if not self.isEnabled():
            p.setBrush(QColor(10, 12, 17, 200))
            p.drawEllipse(r)
            p.setPen(QColor(theme.MUTED))
            p.setFont(theme.ui_font(8))
            p.drawText(r, Qt.AlignCenter | Qt.TextWordWrap, "This effect uses\nits own colours")
            return
        ang = self.h * 2 * math.pi
        pt = QPointF(c.x() + math.cos(ang) * self.s * r.width() / 2, c.y() - math.sin(ang) * self.s * r.width() / 2)
        p.setBrush(self.color())
        p.setPen(QPen(QColor("white"), 3))
        p.drawEllipse(pt, 9, 9)
        p.setPen(QPen(QColor(0, 0, 0, 120), 1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(pt, 10.5, 10.5)

    def _pick(self, pos):
        r = self._circle()
        dx, dy = pos.x() - r.center().x(), r.center().y() - pos.y()
        self.s = min(math.hypot(dx, dy) / (r.width() / 2), 1.0)
        self.h = (math.atan2(dy, dx) / (2 * math.pi)) % 1.0
        self.update()
        self.changed.emit(self.color())

    def mousePressEvent(self, e):
        self._pick(e.position())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._pick(e.position())


PRESETS = ["#ff2d55", "#ff8a00", "#ffd60a", "#34c759", "#00e5ff", "#2979ff", "#7c5cff", "#d946ef", "#ffffff"]


class ColorPicker(QWidget):
    """Wheel + brightness + hex box + preset swatches."""
    changed = Signal(QColor)

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.wheel = ColorWheel()
        self.wheel.setMaximumHeight(240)
        lay.addWidget(self.wheel, 1)
        self.val = QSlider(Qt.Horizontal)
        self.val.setRange(0, 100)
        self.val.setValue(100)
        lay.addWidget(self.val)
        row = QHBoxLayout()
        self.swatch = QFrame()
        self.swatch.setFixedSize(34, 34)
        self.hex = QLineEdit()
        self.hex.setMaxLength(7)
        row.addWidget(self.swatch)
        row.addWidget(self.hex, 1)
        lay.addLayout(row)
        pr = QHBoxLayout()
        pr.setSpacing(6)
        for c in PRESETS:
            b = QPushButton()
            b.setFixedSize(22, 22)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"background:{c}; border-radius:11px; border:2px solid #0a0c11; padding:0;")
            b.clicked.connect(lambda _=False, c=c: self.set_color(QColor(c), True))
            pr.addWidget(b)
        pr.addStretch()
        lay.addLayout(pr)
        self.wheel.changed.connect(self._from_wheel)
        self.val.valueChanged.connect(lambda v: self.wheel.set_value(v / 100))
        self.hex.editingFinished.connect(self._from_hex)
        self._sync()

    def color(self):
        return self.wheel.color()

    def set_color(self, c, emit=False):
        self.wheel.set_color(c)
        self.val.blockSignals(True)
        self.val.setValue(round(self.wheel.v * 100))
        self.val.blockSignals(False)
        self._sync()
        if emit:
            self.changed.emit(self.color())

    def _from_wheel(self, c):
        self._sync()
        self.changed.emit(c)

    def _from_hex(self):
        c = QColor(self.hex.text() if self.hex.text().startswith("#") else "#" + self.hex.text())
        if c.isValid():
            self.set_color(c, True)

    def _sync(self):
        c = self.color()
        self.swatch.setStyleSheet(f"background:{c.name()}; border-radius:10px; border:1px solid #2b3350;")
        self.hex.setText(c.name().upper())


class KeyboardView(QWidget):
    """The 68-key board. Shows labels, optional RGB fills and a sub-label (e.g. actuation mm)."""
    clicked = Signal(int, bool)   # key pos, additive (Ctrl held)

    def __init__(self, min_height=260):
        super().__init__()
        self.labels, self.sub, self.fills, self.selected = {}, {}, {}, set()
        self.hover = None
        self.glow = True
        self.tint = True
        self.solid = False          # draw fills as solid, high-contrast keycaps (heat maps)
        self.live = {}              # pos -> 0..1 live press depth, drawn as a bar inside the keycap
        self.setMouseTracking(True)
        self.setMinimumHeight(min_height)
        self.setCursor(Qt.PointingHandCursor)

    def _rects(self):
        u = min((self.width() - 16) / 16.0, (self.height() - 16) / 5.0)
        ox, oy = (self.width() - 16 * u) / 2, (self.height() - 5 * u) / 2
        out = {}
        for r, row in enumerate(ROWS):
            x = 0.0
            for pos, w in row:
                out[pos] = QRectF(ox + x * u, oy + r * u, w * u, u)
                x += w
        return out, u

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rects, u = self._rects()
        f = theme.ui_font(max(7, int(u / 5.2)), QFont.DemiBold)
        small = theme.ui_font(max(6, int(u / 7.5)))
        for pos, rc in rects.items():
            self._key(p, pos, rc.adjusted(2.5, 2.5, -2.5, -2.5), f, small)

    def _key(self, p, pos, r, font, small):
        fill = self.fills.get(pos)
        sel = pos in self.selected
        radius = r.height() * 0.16
        if fill is not None and self.glow:
            for i, a in ((5, 30), (3, 45), (1, 70)):
                c = QColor(fill)
                c.setAlpha(a)
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                p.drawRoundedRect(r.adjusted(-i, -i, i, i), radius + i, radius + i)
        base_top, base_bot = QColor("#2c3248"), QColor("#1a1f30")
        if pos == self.hover:
            base_top, base_bot = base_top.lighter(125), base_bot.lighter(125)
        if fill is not None and self.solid:
            base_top, base_bot = QColor(fill).lighter(112), QColor(fill).darker(128)
        elif fill is not None:
            base_top, base_bot = theme.mix(base_top, fill, 0.55), theme.mix(base_bot, fill, 0.40)
        elif self.tint and pos in KEY_TINTS:
            base_top, base_bot = theme.mix(base_top, KEY_TINTS[pos], 0.30), theme.mix(base_bot, KEY_TINTS[pos], 0.20)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, base_top)
        g.setColorAt(1, base_bot)
        p.setBrush(g)
        outline = QColor("white") if (sel and self.solid) else QColor(theme.ACCENT2)
        p.setPen(QPen(outline if sel else QColor("#0a0c11"), 3 if sel else 1))
        p.drawRoundedRect(r, radius, radius)
        face = r.adjusted(r.width() * 0.07, r.height() * 0.07, -r.width() * 0.07, -r.height() * 0.16)
        fg = QLinearGradient(face.topLeft(), face.bottomLeft())
        fg.setColorAt(0, theme.mix(base_top, "#ffffff", 0.10))
        fg.setColorAt(1, base_top)
        p.setPen(Qt.NoPen)
        p.setBrush(fg)
        p.drawRoundedRect(face, radius * 0.8, radius * 0.8)
        if sel:
            ring = QColor(theme.ACCENT2)
            ring.setAlpha(60)
            p.setBrush(ring)
            p.drawRoundedRect(face, radius * 0.8, radius * 0.8)
        frac = self.live.get(pos)
        if frac:                                   # live press depth: a dark bar rising from the bottom
            bar = QRectF(face.left(), face.bottom() - face.height() * min(frac, 1.0), face.width(),
                         face.height() * min(frac, 1.0))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(10, 12, 20, 150))
            p.drawRoundedRect(bar, radius * 0.8, radius * 0.8)
        text = self.labels.get(pos, KEY_NAMES.get(pos, ""))
        light = fill is not None and (_luminance(fill) > 0.42 if self.solid else fill.lightness() > 150)
        ink = QColor("#10131a") if light else QColor(theme.TEXT)
        sub = self.sub.get(pos)
        main_rect = face.adjusted(2, 0, -2, -face.height() * 0.30) if sub else face.adjusted(2, 0, -2, 0)
        p.setPen(ink)
        p.setFont(self._fit(text, main_rect, font))
        p.drawText(main_rect, Qt.AlignCenter | Qt.TextWordWrap, text)
        if sub:
            p.setFont(small)
            sub_ink = QColor(ink)
            sub_ink.setAlpha(190)
            p.setPen(sub_ink if (light or self.solid) else QColor(theme.MUTED))
            p.drawText(face.adjusted(0, face.height() * 0.45, 0, 0), Qt.AlignCenter, sub)

    @staticmethod
    def _fit(text, rect, font):
        """Largest font (down to 5pt) at which the text fits the keycap, wrapping on spaces."""
        f = QFont(font)
        flags = int(Qt.AlignCenter | Qt.TextWordWrap)
        size = f.pointSizeF()
        while size > 5.0:
            f.setPointSizeF(size)
            br = QFontMetrics(f).boundingRect(rect.toRect(), flags, text)
            if br.width() <= rect.width() + 1 and br.height() <= rect.height() + 1:
                break
            size -= 0.5
        f.setPointSizeF(max(size, 5.0))
        return f

    def _at(self, pt):
        for pos, rc in self._rects()[0].items():
            if rc.contains(pt):
                return pos
        return None

    def mouseMoveEvent(self, e):
        h = self._at(e.position())
        if h != self.hover:
            self.hover = h
            self.update()

    def leaveEvent(self, _):
        self.hover = None
        self.update()

    def mousePressEvent(self, e):
        pos = self._at(e.position())
        if pos is not None:
            self.clicked.emit(pos, bool(e.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)))


def _centers():
    out = {}
    for r, row in enumerate(ROWS):
        x = 0.0
        for pos, w in row:
            out[pos] = (x + w / 2, r + 0.5)
            x += w
    return out


KEY_CENTERS = _centers()


class EffectView(KeyboardView):
    """Keyboard that animates the selected lighting effect (a software approximation)."""

    def __init__(self, min_height=240):
        super().__init__(min_height)
        self.tint = False
        self.mode, self.color, self.mix, self.bright, self.speed = 0, QColor("#ff2d55"), False, 20, 2
        self.static_fills = {}
        self.side = None            # (QColor, brightness 0..20) or None
        self.presses = []           # (pos, time)
        self.demo = True
        self._t0 = time.monotonic()
        self._next_demo = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self.tick)

    def showEvent(self, e):
        super().showEvent(e)
        self._timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()

    def set_effect(self, mode, color, mix, bright, speed):
        self.mode, self.color, self.mix, self.bright, self.speed = mode, QColor(color), mix, bright, speed
        self.tick()

    def press(self, pos):
        self.presses = [x for x in self.presses if time.monotonic() - self._t0 - x[1] < 3.5][-12:]
        self.presses.append((pos, time.monotonic() - self._t0))

    def tick(self):
        t = time.monotonic() - self._t0
        if self.mode == 19:
            self.fills = {p: (QColor(*c) if isinstance(c, tuple) else QColor(c))
                          for p, c in self.static_fills.items() if c != (0, 0, 0)}
        else:
            if self.demo and self.mode in effects.REACTIVE and t > self._next_demo:
                self.press(random.choice(list(KEY_CENTERS)))
                self._next_demo = t + random.uniform(0.35, 0.9)
            self.fills = effects.render(self.mode, t, KEY_CENTERS, self.color, self.mix, self.bright, self.speed,
                                        self.presses)
        self.update()

    def paintEvent(self, e):
        if self.side is not None and self.side[1] > 0:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            rects, u = self._rects()
            xs = [r.left() for r in rects.values()] + [r.right() for r in rects.values()]
            ys = [r.top() for r in rects.values()] + [r.bottom() for r in rects.values()]
            box = QRectF(min(xs) - 6, min(ys) - 6, max(xs) - min(xs) + 12, max(ys) - min(ys) + 12)
            col = QColor(self.side[0])
            for i, a in ((14, 14), (9, 26), (5, 46), (2, 90)):
                col.setAlpha(int(a * self.side[1] / 20.0) + 4)
                p.setPen(QPen(col, i))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(box, 22, 22)
            p.end()
        super().paintEvent(e)


class TravelGauge(QWidget):
    """Cut-away drawing of a switch (redrawn as vector paths). The stem and spring move to the actuation
    depth; a 0-4 mm ruler marks the actuation point, rapid-trigger distances and dead zones.

    The drawing is laid out in a 720x720 design space (see the _poly calls) and scaled to fit."""

    LINE = QColor("#4a4b50")
    WHITE = QColor("#fbfcff")
    GREY = QColor("#e4e7f0")
    DARK = QColor("#b4b9c8")
    TOP_Y, HOUSING_Y = 62.0, 205.0       # stem top at rest, housing top plate: 4 mm of travel between them
    FLOOR_Y = 495.0                       # inside floor of the housing (the spring rests on it)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(360, 380)
        self.act, self.rt_on, self.rt_up, self.rt_down = 2.0, False, 0.3, 0.3
        self.safe_top, self.safe_bot = 0.0, 0.0
        self._shown = 0.0
        self.live, self.live_pressed = None, False   # live travel (mm) of the followed key
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(300)
        self._anim.setEasingCurve(QEasingCurve.OutBack)
        self._anim.valueChanged.connect(self._set_shown)

    def _set_shown(self, v):
        self._shown = v
        self.update()

    def set_values(self, act, rt_on, rt_up, rt_down, safe_top, safe_bot):
        self._anim.stop()
        self._anim.setStartValue(self._shown)
        self._anim.setEndValue(act)
        self.act, self.rt_on, self.rt_up, self.rt_down = act, rt_on, rt_up, rt_down
        self.safe_top, self.safe_bot = safe_top, safe_bot
        self._anim.start()

    def set_live(self, mm, pressed=False):
        """mm = live travel of the key (None switches live mode off and the stem returns to the actuation point)."""
        self.live, self.live_pressed = mm, pressed
        self.update()

    # ---- small drawing helpers (design-space coordinates)
    def _poly(self, p, pts, fill, dy=0.0, width=2.4):
        path = QPainterPath()
        path.moveTo(pts[0][0], pts[0][1] + dy)
        for x, y in pts[1:]:
            path.lineTo(x, y + dy)
        path.closeSubpath()
        p.setPen(QPen(self.LINE, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(fill)
        p.drawPath(path)

    def _housing(self, p):
        W, G, D = self.WHITE, self.GREY, self.DARK
        poly = self._poly
        # back plates (lighter panels inside the housing)
        poly(p, [(170, 357), (268, 357), (268, 508), (170, 508)], W)
        poly(p, [(185, 357), (268, 357), (268, 508), (185, 508)], G)
        poly(p, [(483, 372), (583, 372), (583, 495), (483, 495)], W)
        poly(p, [(493, 372), (550, 372), (550, 495), (493, 495)], G)
        # left shoulder with its arched window
        poly(p, [(128, 372), (128, 345), (165, 300), (170, 236), (186, 214), (212, 205), (268, 205), (268, 372)], W)
        arch = QPainterPath()
        arch.moveTo(178, 342)
        arch.lineTo(178, 252)
        arch.quadTo(180, 220, 213, 220)
        arch.quadTo(245, 222, 245, 256)
        arch.lineTo(245, 342)
        arch.closeSubpath()
        p.setBrush(G)
        p.setPen(QPen(self.LINE, 2.4))
        p.drawPath(arch)
        poly(p, [(210, 296), (245, 296), (245, 356), (210, 356)], G)
        poly(p, [(245, 296), (268, 296), (268, 372), (245, 372)], W)
        # left clip
        poly(p, [(111, 378), (137, 378), (153, 442), (156, 442), (156, 518), (142, 518), (142, 462), (124, 462),
                 (133, 452), (133, 404), (111, 404)], W)
        # right wall with the sloped top
        poly(p, [(458, 205), (486, 205), (596, 372), (558, 372), (558, 495), (483, 495), (483, 372), (458, 372)], W)
        poly(p, [(487, 214), (487, 352), (583, 352)], G)
        poly(p, [(558, 372), (583, 372), (583, 495), (558, 495)], W)
        poly(p, [(583, 378), (606, 378), (606, 404), (589, 404), (589, 460), (603, 462), (583, 495)], W)
        # floor + feet
        poly(p, [(142, 495), (582, 495), (582, 568), (142, 568)], W)
        poly(p, [(142, 551), (240, 551), (240, 568), (142, 568)], G)
        poly(p, [(181, 551), (181, 568), (183, 568), (183, 551)], G)
        poly(p, [(483, 495), (493, 495), (493, 568), (483, 568)], G)
        # pin
        poly(p, [(336, 568), (386, 568), (386, 628), (361, 657), (336, 628)], G)
        p.drawLine(QPointF(357, 568), QPointF(357, 630))
        p.drawLine(QPointF(366, 568), QPointF(366, 630))

    def _stem(self, p, dy):
        W, G, D = self.WHITE, self.GREY, self.DARK
        poly = self._poly
        p.save()
        p.setClipRect(QRectF(0, 0, 720, self.FLOOR_Y))
        # slider block inside the stem
        poly(p, [(321, 228), (402, 228), (402, 240), (420, 240), (426, 372), (298, 372), (305, 240), (321, 240)], G, dy)
        # spring: coils squeeze together as the stem goes down
        top = 322 + dy
        n = 6
        span = max(self.FLOOR_Y - 4 - top, 24.0)
        thick = min(11.0, span / n * 0.8)
        for i in range(n):
            y = top + span * (i + 0.5) / n
            poly(p, [(268, y + 9 - thick / 2), (455, y - 9 - thick / 2), (455, y - 9 + thick / 2), (268, y + 9 + thick / 2)],
                 W, 0, 2.0)
        # stem body, cap and its three windows
        poly(p, [(270, 62), (452, 62), (452, 308), (270, 308)], W, dy)
        poly(p, [(270, 308), (298, 308), (298, 338), (270, 338)], D, dy, 1.6)
        poly(p, [(424, 308), (452, 308), (452, 338), (424, 338)], D, dy, 1.6)
        poly(p, [(290, 64), (430, 64), (430, 186), (290, 186)], W, dy, 2.0)
        accent = QLinearGradient(0, 64 + dy, 0, 186 + dy)
        accent.setColorAt(0, QColor("#d7f3ff"))
        accent.setColorAt(1, QColor("#e3dcff"))
        poly(p, [(294, 70), (341, 70), (341, 176), (333, 183), (294, 183)], accent, dy, 2.0)
        poly(p, [(343, 78), (351, 68), (369, 68), (377, 78), (377, 176), (368, 184), (352, 184), (343, 176)],
             QColor("#eef0f8"), dy, 2.0)
        poly(p, [(379, 70), (426, 70), (426, 183), (388, 183), (379, 176)], accent, dy, 2.0)
        p.restore()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        # scale the drawing to fill the widget: ~725 design units wide, ~595 tall below the 74 px header
        scale = max(0.3, min((w - 16) / 725.0, (h - 84) / 595.0))
        ox, oy = max(8.0, (w - 725 * scale) / 2), 74.0 - self.TOP_Y * scale
        travel = self.HOUSING_Y - self.TOP_Y            # design-space distance that stands for 4 mm
        depth = self.live if self.live is not None else self._shown
        d = travel * min(max(depth, 0.0), 4.2) / 4.0
        # soft glow behind the switch
        glow = QRadialGradient(ox + 360 * scale, oy + 360 * scale, 330 * scale)
        glow.setColorAt(0, QColor(139, 92, 246, 55))
        glow.setColorAt(1, QColor(139, 92, 246, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawRect(self.rect())
        p.save()
        p.translate(ox, oy)
        p.scale(scale, scale)
        self._housing(p)
        self._stem(p, d)
        p.restore()

        # ---- ruler on the right (design x 640 -> screen)
        def sy(mm):
            return oy + (self.TOP_Y + travel * mm / 4.0) * scale
        rx = ox + 650 * scale
        y0, y4 = sy(0), sy(4)
        if self.safe_top > 0:
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(255, 93, 115, 150), Qt.BDiagPattern))
            p.drawRect(QRectF(rx - 7, y0, 14, sy(self.safe_top) - y0))
        if self.safe_bot > 0:
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(255, 93, 115, 150), Qt.BDiagPattern))
            p.drawRect(QRectF(rx - 7, sy(4 - self.safe_bot), 14, y4 - sy(4 - self.safe_bot)))
        rg = QLinearGradient(0, y0, 0, y4)
        rg.setColorAt(0, QColor(theme.ACCENT2))
        rg.setColorAt(1, QColor(theme.ACCENT))
        p.setPen(QPen(QColor("#2b3350"), 5, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(rx, y0), QPointF(rx, y4))
        p.setPen(QPen(QBrush(rg), 5, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(rx, y0), QPointF(rx, sy(min(depth, 4.0))))
        p.setFont(theme.ui_font(7))
        for mm in range(5):
            p.setPen(QPen(QColor("#5a6486"), 1.2))
            p.drawLine(QPointF(rx - 8, sy(mm)), QPointF(rx + 8, sy(mm)))
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(rx + 12, sy(mm) - 9, 44, 18), Qt.AlignLeft | Qt.AlignVCenter, f"{mm} mm")
        # ---- markers
        left = ox + 250 * scale
        if self.rt_on:
            for off, txt in ((-self.rt_up, f"reset −{self.rt_up:.2f}"), (self.rt_down, f"press +{self.rt_down:.2f}")):
                yy = sy(min(max(self._shown + off, 0.0), 4.0))
                p.setPen(QPen(QColor(theme.GOOD), 1.8, Qt.DashLine))
                p.drawLine(QPointF(left, yy), QPointF(rx - 8, yy))
                p.setPen(QColor(theme.GOOD))
                p.setFont(theme.ui_font(7))
                p.drawText(QRectF(ox + 8, yy + (1 if off > 0 else -17), 150, 16), Qt.AlignLeft | Qt.AlignVCenter, txt)
        ay = sy(min(self._shown, 4.0))
        p.setPen(QPen(QColor("white"), 2.6))
        p.drawLine(QPointF(left, ay), QPointF(rx + 6, ay))
        p.setBrush(QColor("white"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(rx, ay), 6, 6)
        if self.live is not None:
            p.setPen(QColor(theme.GOOD) if self.live_pressed else QColor("white"))
            p.setFont(theme.head_font(26))
            p.drawText(QRectF(0, 4, w, 40), Qt.AlignHCenter | Qt.AlignVCenter, f"{self.live:.2f} mm")
            p.setFont(theme.ui_font(8))
            p.setPen(QColor(theme.GOOD))
            p.drawText(QRectF(0, 42, w, 20), Qt.AlignHCenter | Qt.AlignVCenter,
                       f"● LIVE   (actuation set to {self.act:.2f} mm)")
        else:
            p.setPen(QColor("white"))
            p.setFont(theme.head_font(26))
            p.drawText(QRectF(0, 4, w, 40), Qt.AlignHCenter | Qt.AlignVCenter, f"{self.act:.2f} mm")
            p.setFont(theme.ui_font(8))
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(0, 42, w, 20), Qt.AlignHCenter | Qt.AlignVCenter, "actuation point")


class NavButton(QPushButton):
    def __init__(self, glyph, text, colors=(theme.ACCENT, theme.ACCENT2)):
        super().__init__()
        self.colors = colors
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(46)
        self.glyph, self.text_ = glyph, text
        self.setStyleSheet("QPushButton{border:none;background:transparent;border-radius:12px;}"
                           "QPushButton:hover{background:#151a28;}")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(6, 2, -6, -2)
        if self.isChecked():
            g = QLinearGradient(r.topLeft(), r.topRight())
            c1, c2 = QColor(self.colors[0]), QColor(self.colors[1])
            c1.setAlpha(95)
            c2.setAlpha(22)
            g.setColorAt(0, c1)
            g.setColorAt(1, c2)
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawRoundedRect(r, 12, 12)
            p.setBrush(QColor(self.colors[0]))
            p.drawRoundedRect(QRectF(r.left(), r.center().y() - 12, 4, 24), 2, 2)
        elif self.underMouse():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#151a28"))
            p.drawRoundedRect(r, 12, 12)
        p.setFont(theme.icon_font(15))
        icon = QColor(self.colors[0]) if self.isChecked() else theme.mix(self.colors[0], theme.MUTED, 0.45)
        p.setPen(icon)
        p.drawText(QRectF(r.left() + 14, r.top(), 30, r.height()), Qt.AlignCenter, self.glyph)
        p.setPen(QColor("white") if self.isChecked() else QColor(theme.MUTED))
        p.setFont(theme.ui_font(10, QFont.DemiBold if self.isChecked() else QFont.Normal))
        p.drawText(QRectF(r.left() + 54, r.top(), r.width() - 60, r.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text_)


class Toast(QLabel):
    """Small notification that fades in at the bottom of its parent and out again."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.hide()
        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._anim = QPropertyAnimation(self._fx, b"opacity", self)
        self._timer = QTimer(self, singleShot=True)
        self._timer.timeout.connect(self._fade_out)

    def show_message(self, text, kind="ok"):
        color = {"ok": theme.GOOD, "error": theme.BAD, "info": theme.ACCENT2}[kind]
        self.setStyleSheet(f"background:#10141f; border:1px solid {color}; border-left:5px solid {color};"
                           f"border-radius:12px; padding:12px 20px; color:{theme.TEXT};")
        self.setText(text)
        self.adjustSize()
        p = self.parentWidget()
        self.move((p.width() - self.width()) // 2, p.height() - self.height() - 28)
        self.raise_()
        self.show()
        self._anim.stop()
        self._anim.setDuration(160)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start(2600 if kind != "error" else 5000)

    def _fade_out(self):
        self._anim.stop()
        self._anim.setDuration(300)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self._done)
        self._anim.start()

    def _done(self):
        self._anim.finished.disconnect(self._done)
        if self._fx.opacity() < 0.05:
            self.hide()
