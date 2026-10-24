"""Software preview of the keyboard's built-in lighting effects.

The keyboard runs these effects in firmware and cannot report its LED state, so these are
approximations built from the effect names; speed, brightness, colour and the multicolour flag are
honoured. Coordinates are in key units (x 0..16, y 0..5)."""
import math

from PySide6.QtGui import QColor

YELLOW_WHEN_MULTICOLOUR = (1, 14)   # Always on and Scan turn yellow with multicolour on (seen on the keyboard)
REACTIVE = (4, 7, 9, 12)        # burst, key ripples, snow trail, follow: driven by key presses
# (title, note, modes): grouped by what the colour controls do, as the keyboard's own capabilities dictate
GROUPS = [
    ("Static", "", [0, 1]),
    ("Full RGB", "Own rainbow palette, no colour picker", [3, 15, 16]),
    ("Ambient", "Uses your colour (or multicolour)", [2, 8, 5, 10, 11, 13, 14, 17, 18, 6]),
    ("Reactive", "Lights up as you press keys", [4, 7, 9, 12]),
    ("Custom", "Per-key colours", [19]),
]


def _phase(pos, salt=0):
    """Stable pseudo-random 0..1 per key."""
    return ((pos * 2654435761 + salt * 40503) % 1000) / 1000.0


_ORDER_CACHE = {}


def _reading_order(centers):
    """{pos: rank} going along each row left to right, then the next row (Esc is 0)."""
    key = id(centers)
    if key not in _ORDER_CACHE:
        order = sorted(centers, key=lambda p: (round(centers[p][1]), centers[p][0]))
        _ORDER_CACHE[key] = {p: i for i, p in enumerate(order)}
    return _ORDER_CACHE[key]


def _scale(c, k):
    k = max(0.0, min(1.0, k))
    return QColor(round(c.red() * k), round(c.green() * k), round(c.blue() * k))


def _hue(h):
    return QColor.fromHsvF(h % 1.0, 1.0, 1.0)


def _presses_at(presses, t, x, y, centers, shape):
    best = 0.0
    for pos, t0 in presses:
        age = t - t0
        if age < 0 or age > 3.2 or pos not in centers:
            continue
        px, py = centers[pos]
        d = math.hypot(x - px, y - py)
        best = max(best, shape(d, age))
    return best


def render(mode, t, centers, base, mix, bright, speed, presses):
    """Return {pos: QColor} for every lit key."""
    if mode == 0 or bright <= 0:
        return {}
    if mix and mode in YELLOW_WHEN_MULTICOLOUR:      # observed on the real keyboard: these show one palette colour
        base, mix = QColor("#ffd60a"), False
    sp = 0.35 + speed * 0.4
    k = bright / 20.0
    out = {}
    cx, cy = 8.0, 2.5
    for pos, (x, y) in centers.items():
        h = None
        b = 1.0
        if mode == 1:                                    # always on (multicolour = the palette's first colour)
            h = 0.14 if mix else None
        elif mode == 2:                                  # breathing
            b = 0.08 + 0.92 * (math.sin(t * sp * 1.5) * 0.5 + 0.5)
            h = (t * 0.05 * sp) if mix else None
        elif mode == 3:                                  # neon: vivid colours chasing across the board
            b = 0.55 + 0.45 * math.sin((x + y * 0.6) * 0.5 - t * sp * 2.2)
            h = ((x + y * 0.6) * 0.05 + t * 0.22 * sp) if mix else None
        elif mode == 4:                                  # burst: spreads sideways along the pressed key's row only
            v = 0.0
            for ppos, t0 in presses:
                age = t - t0
                if age < 0 or age > 1.6 or ppos not in centers:
                    continue
                px, py = centers[ppos]
                if abs(y - py) > 0.3:
                    continue
                dx = abs(x - px)
                front = age * sp * 8.0
                v = max(v, math.exp(-dx * dx / 0.4) * max(0.0, 1 - age / 0.5),
                        math.exp(-((dx - front) ** 2) / 0.9) * max(0.0, 1 - age / 1.5))
            b = 0.04 + v
            h = (x / 16.0) if mix else None
        elif mode == 5:                                  # rain: drops of varying speed falling down each column
            ph = _phase(int(x), 3)
            head = (t * (1.1 + ph) * sp * 1.5 + ph * 9) % 9.5 - 1.5
            d = head - y
            b = (1.0 if d < 0.55 else 1 - (d - 0.55) / 2.4) if 0 <= d < 2.95 else 0.0
            h = (x / 16.0) if mix else None
        elif mode == 6:                                  # rainbow wheel
            ang = math.atan2(y - cy, x - cx) / (2 * math.pi)
            b = (math.cos((ang - t * 0.18 * sp) * 2 * math.pi) * 0.5 + 0.5) ** 1.4 * 0.9 + 0.1
            h = (ang + t * 0.18 * sp) if mix else None
        elif mode == 7:                                  # key ripples
            b = 0.06 + _presses_at(presses, t, x, y, centers,
                                   lambda d, a: math.exp(-((d - a * sp * 4.0) ** 2) / 0.7) * max(0.0, 1 - a / 2.4))
            h = ((x + y) / 20.0) if mix else None
        elif mode == 8:                                  # starry sky: twinkling
            ph, rate = _phase(pos, 4), 0.6 + _phase(pos, 5)
            b = max(0.0, math.sin(t * sp * rate * 2 + ph * 6.28)) ** 3
            h = _phase(pos, 6) if mix else None
        elif mode == 9:                                  # snow trail: lit board, your key leaves a dark footprint that refills
            dark = _presses_at(presses, t, x, y, centers,
                               lambda d, a: (1.0 if d < 0.3 else 0.0) * max(0.0, 1 - a / 2.8))
            b = 0.9 * (1.0 - dark)
            h = (x / 16.0) if mix else None
        elif mode == 10:                                 # flow: snakes Esc -> last key, row by row
            order = _reading_order(centers)
            n = len(order)
            head = (t * sp * 9.0) % n
            gap = (head - order[pos]) % n               # keys the head has already passed (behind)
            if gap < n / 2:
                b = math.exp(-gap / 8.0)                 # long fading tail behind the head
            else:
                b = 0.9 * math.exp(-(n - gap) / 3.0)     # shorter glow in front of it
            h = (order[pos] / n + t * 0.04) if mix else None
        elif mode == 11:                                 # drift: slow diagonal colours
            b = 0.55 + 0.45 * math.sin((x + y * 1.2) * 0.35 - t * sp * 0.9)
            h = ((x + y) * 0.045 + t * 0.07 * sp) if mix else None
        elif mode == 12:                                 # follow: only the pressed key lights
            b = 0.03 + _presses_at(presses, t, x, y, centers,
                                   lambda d, a: (1.0 if d < 0.3 else 0.0) * max(0.0, 1 - a / 0.8))
            h = (x / 16.0) if mix else None
        elif mode == 13:                                 # sine wave
            b = math.sin(x * 0.5 + y * 0.9 + t * sp * 2.2) * 0.5 + 0.5
            h = ((x + y) / 20.0 + t * 0.04) if mix else None
        elif mode == 14:                                 # scan: bar sweeping left-right at constant speed
            tri = abs(((t * sp * 0.32) % 2.0) - 1.0)
            sweep = -0.5 + 17.0 * tri
            b = math.exp(-((x - sweep) ** 2) / 1.3)
            h = (x / 16.0) if mix else None
        elif mode == 15:                                 # windmill: four rotating blades
            a = math.atan2(y - cy, x - cx) - t * sp * 1.3
            b = max(0.0, math.cos(2 * a)) ** 3 * min(1.0, math.hypot(x - cx, (y - cy) * 1.6) / 2.0)
            h = (math.atan2(y - cy, x - cx) / (2 * math.pi)) if mix else None
        elif mode == 16:                                 # waterfall: bands of colour pouring down the board
            b = 0.35 + 0.65 * (math.sin(y * 1.6 - t * sp * 2.6 + x * 0.10) * 0.5 + 0.5)
            h = (y * 0.16 + x * 0.015 - t * 0.12 * sp) if mix else None
        elif mode == 17:                                 # bloom: rings expanding from the middle
            r = (t * sp * 3.2) % 10.0
            d = math.hypot((x - cx) * 0.8, (y - cy) * 1.4)
            b = math.exp(-((d - r) ** 2) / 1.6)
            h = (r / 10.0) if mix else None
        elif mode == 18:                                 # spin storm: rotating spiral
            a = math.atan2(y - cy, x - cx) / (2 * math.pi)
            r = math.hypot((x - cx) * 0.6, y - cy)
            b = 0.55 + 0.45 * math.sin(r * 1.2 + a * 6.28 * 2 - t * sp * 2.5)
            h = (a + r * 0.12 - t * 0.2 * sp) if mix else None
        if b <= 0.03:
            continue
        col = _hue(h) if h is not None else base
        out[pos] = _scale(col, b * k)
    return out
