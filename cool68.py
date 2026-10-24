"""Driver for the Dareu COOL 68 hall-effect keyboard (USB VID 372E, PID 1083), wired mode.

It speaks the keyboard's own configuration protocol (a 64-byte HID report on the vendor interface):
byte 0 = report id 9, then a 63-byte payload whose last byte is a checksum,
255 - (sum of all previous bytes including the report id) % 256. See docs/PROTOCOL.md.

Only configuration commands are used. Nothing here flashes firmware.

    from cool68 import Cool68
    kb = Cool68()
    print(kb.get_light())
    kb.close()
"""
import time

import hid

VID, PID = 0x372E, 0x1083
REPORT_ID = 0x09
PAYLOAD_LEN = 63

CMD_SET = 0x04
CMD_GET = 0x84
SUB_LIGHT = 0x01
CMD_KEYS_SET = 0x03
CMD_KEYS_GET = 0x83
KEYS_PER_REQ = 9
SUB_SIDE_LIGHT = 0x06
CMD_COLOR_SET = 0x06
CMD_COLOR_GET = 0x86
COLORS_PER_REQ = 11
LIGHT_CUSTOM = 19
CMD_ADVANCED, CMD_ADVANCED_GET = 0x12, 0x92
CMD_CALIBRATE = 0x94
CMD_LIVE = 0x98          # realtime travel stream: sub 0 start, 1 = which keys, 2 stop
LIVE_MAX_KEYS = 9        # 9 keys per request is fine; a 28-key request once dropped the USB connection
ADV_TYPES = {0: "none", 1: "toggle", 2: "mod_tap", 3: "dks", 4: "socd", 5: "multi", 6: "end"}

# single-byte settings: name -> sub-command (read with 0x84, write with 0x04 and one data byte)
SUB_OS_MODE, SUB_SLEEP, SUB_POLLING, SUB_KEY_COMBO, SUB_AUTO_CALIBRATE, SUB_WIN_LOCK, SUB_OVERDRIVE = (
    0x11, 0x13, 0x17, 0x18, 0x19, 0x15, 0x1F)
POLLING_LEVELS = {1000: 0, 2000: 6, 4000: 5, 8000: 4}  # Hz -> level byte
# sleep timeout byte is in units of 30 s (0 = never); the vendor offers these
SLEEP_LEVELS = {"30 s": 1, "1 min": 2, "90 s": 3, "2 min": 4, "3 min": 6, "5 min": 10, "10 min": 20,
                "15 min": 30, "20 min": 40, "30 min": 60, "60 min": 120, "never": 0}
CMD_MACRO_SET = 0x05
# macro trigger modes (tested: REPEAT plays the macro; mode 0 does nothing)
MACRO_LOOP, MACRO_HOLD, MACRO_REPEAT = 1, 2, 4

# Key positions on layer 0 (from the vendor layout): name -> pos
KEY_NAMES = {
    1: "Esc", 15: "1", 16: "2", 17: "3", 18: "4", 19: "5", 20: "6", 21: "7", 22: "8", 23: "9",
    24: "0", 25: "-", 26: "=", 27: "Backspace", 98: "Insert",
    28: "Tab", 29: "Q", 30: "W", 31: "E", 32: "R", 33: "T", 34: "Y", 35: "U", 36: "I", 37: "O",
    38: "P", 39: "[", 40: "]", 41: "\\", 99: "Delete",
    42: "Caps", 43: "A", 44: "S", 45: "D", 46: "F", 47: "G", 48: "H", 49: "J", 50: "K", 51: "L",
    52: ";", 53: "'", 54: "Enter", 102: "PgUp",
    55: "LShift", 56: "Z", 57: "X", 58: "C", 59: "V", 60: "B", 61: "N", 62: "M", 63: ",", 64: ".",
    65: "/", 66: "RShift", 74: "Up", 103: "PgDn",
    67: "LCtrl", 68: "LWin", 69: "LAlt", 70: "Space", 71: "RAlt", 72: "Fn", 73: "RCtrl",
    75: "Down", 76: "Left", 77: "Right",
}
KEY_POS = list(KEY_NAMES)


def mix_byte(mix):
    """True -> 7 (the vendor's "multicolour"), False/None -> 0 (single colour), an int -> that raw bitmask."""
    if mix is True:
        return 7
    return 0 if not mix else int(mix) & 0xFF


def _frame(cmd, sub, data=()):
    p = [0] * PAYLOAD_LEN
    head = [cmd, sub, 0, 1, 0, len(data)]
    p[: len(head)] = head
    p[len(head) : len(head) + len(data)] = data
    p[-1] = 255 - (REPORT_ID + sum(p[:-1])) % 256
    return bytes([REPORT_ID] + p)


def device_present():
    """True when the keyboard's configuration interface is on the bus (cheap; safe to poll)."""
    try:
        _find_path()
        return True
    except RuntimeError:
        return False


def _find_path():
    for d in hid.enumerate(VID, PID):
        if d["interface_number"] == 2 and d["usage_page"] == 0xFF60:
            return d["path"]
    raise RuntimeError("COOL 68 config interface not found (is it plugged in?)")


class Cool68:
    def __init__(self):
        self.dev = hid.device()
        self.dev.open_path(_find_path())

    def close(self):
        try:
            if getattr(self, "_live", False):
                self.live_stop()
        except Exception:
            pass
        self.dev.close()

    def _xfer(self, frame, timeout_ms=1000):
        """Send a frame and wait for its echo. A dropped reply is retried once (resending is harmless:
        every command here is idempotent)."""
        for attempt in range(2):
            self.dev.write(frame)
            for _ in range(8):
                r = self.dev.read(64, timeout_ms)
                if r and r[1] == frame[1] and r[2] == frame[2]:
                    return bytes(r)
        raise TimeoutError("no response from keyboard")

    def get_light(self):
        r = self._xfer(_frame(CMD_GET, SUB_LIGHT))
        d = r[7:14]
        return dict(mode=d[0], mix=d[1] != 0, mix_mask=d[1], r=d[2], g=d[3], b=d[4], brightness=d[5], speed=d[6])

    def set_light(self, mode, r=255, g=0, b=0, brightness=20, speed=2, mix=False):
        data = [mode, mix_byte(mix), r, g, b, brightness, speed]
        self._xfer(_frame(CMD_SET, SUB_LIGHT, data))

    def _get_byte(self, sub):
        return self._xfer(_frame(CMD_GET, sub))[7]

    def _set_byte(self, sub, value):
        self._xfer(_frame(CMD_SET, sub, [value]))

    def get_polling(self):
        """Polling rate in Hz."""
        level = self._get_byte(SUB_POLLING)
        return {v: k for k, v in POLLING_LEVELS.items()}.get(level, level)

    def set_polling(self, hz):
        """Set the polling rate in Hz. The keyboard re-enumerates on USB as soon as the new rate applies,
        which can cut off its reply, so a read error here is expected: close this object and reopen it."""
        try:
            self._set_byte(SUB_POLLING, POLLING_LEVELS[hz])
        except OSError:
            pass

    def get_win_lock(self):
        return self._get_byte(SUB_WIN_LOCK) == 1

    def set_win_lock(self, on):
        self._set_byte(SUB_WIN_LOCK, int(on))

    def get_mac_mode(self):
        return self._get_byte(SUB_OS_MODE) == 1

    def set_mac_mode(self, on):
        self._set_byte(SUB_OS_MODE, int(on))

    def get_key_combo(self):
        return self._get_byte(SUB_KEY_COMBO) == 1

    def set_key_combo(self, on):
        self._set_byte(SUB_KEY_COMBO, int(on))

    def get_auto_calibrate(self):
        return self._get_byte(SUB_AUTO_CALIBRATE) == 1

    def set_auto_calibrate(self, on):
        self._set_byte(SUB_AUTO_CALIBRATE, int(on))

    def get_overdrive(self):
        return self._get_byte(SUB_OVERDRIVE) == 1

    def set_overdrive(self, on):
        self._set_byte(SUB_OVERDRIVE, int(on))

    def set_sleep(self, level):
        """level is a SLEEP_LEVELS value. The keyboard does not answer a read of this setting."""
        self._set_byte(SUB_SLEEP, level)

    def get_firmware_version(self):
        r = self._xfer(_frame(0x82, 2))
        return r[8] << 8 | r[7]

    def get_device_id(self):
        r = self._xfer(_frame(0x82, 1))
        return int.from_bytes(r[7:13], "big")

    def get_profile(self):
        return self._xfer(_frame(0x90, 0))[7]

    def set_profile(self, idx):
        self._xfer(_frame(0x10, 0, [idx]))

    def get_profile_name(self, idx):
        r = self._xfer(_frame(0x9A, idx))
        n = r[7]
        return None if n == 255 else bytes(r[8 : 8 + n]).decode("utf-8", "replace")

    def set_profile_name(self, idx, name):
        raw = name.encode("utf-8")[:55]
        self._xfer(_frame(0x1A, idx, [len(raw)] + list(raw) + [0] * (55 - len(raw))))

    def upload_macros(self, macros):
        """Replace ALL macros on the keyboard. macros = [(name, [MacroEvent bytes...])]; see macro_events()."""
        bodies = []
        for name, events in macros:
            raw = name.encode("utf-8")
            bodies.append([len(raw)] + list(raw) + [b for ev in events for b in ev])
        offset, heads = len(bodies) * 4, []
        for body in bodies:
            heads += [offset & 0xFF, offset >> 8, len(body) & 0xFF, len(body) >> 8]
            offset += len(body)
        blob = heads + [b for body in bodies for b in body]
        chunks = [blob[i : i + 56] for i in range(0, len(blob), 56)]
        for idx, c in enumerate(chunks):
            p = [0] * PAYLOAD_LEN
            p[:6] = [CMD_MACRO_SET, 0, 0, len(chunks), idx, len(c)]
            p[6 : 6 + len(c)] = c
            p[-1] = 255 - (REPORT_ID + sum(p[:-1])) % 256
            for attempt in range(5):  # the vendor app also retries a chunk up to 5 times
                try:
                    self._xfer(bytes([REPORT_ID] + p), timeout_ms=1000)
                    break
                except TimeoutError:
                    if attempt == 4:
                        raise

    def _per_key(self, cmd, positions, per_req, entry, parse, sub=0):
        """Read a per-key table: send pos lists, get fixed-size entries back, keep those echoing the pos."""
        positions = list(positions if positions is not None else KEY_POS)
        out = {}
        for i in range(0, len(positions), per_req):
            chunk = positions[i : i + per_req]
            data = [b for p in chunk for b in (p >> 8, p & 0xFF)]
            r = self._xfer(_frame(cmd, sub, data))
            for j in range(len(chunk)):
                e = r[7 + j * entry : 7 + (j + 1) * entry]
                if len(e) == entry and (e[0] << 8 | e[1]) == chunk[j]:
                    out[chunk[j]] = parse(e)
        return out

    def get_precision(self):
        """(rapid-trigger step, travel step): raw per-key values are multiples of these (units of 0.01 mm
        is the vendor app's assumption; check against get_travel before trusting)."""
        rt = self._xfer(_frame(0x82, 6))[7]
        dist = self._xfer(_frame(0x82, 8))[7]
        return rt, (dist or rt)

    def get_travel(self, positions=None):
        """{pos: (actuation distance raw, uses_global)}"""
        return self._per_key(0x93, positions, 11, 5, lambda e: (e[2] << 8 | e[3], bool(e[4])))

    def get_rapid_trigger(self, positions=None):
        """{pos: dict(enable, up, down, global)}; up/down are raw sensitivity steps."""
        return self._per_key(0x99, positions, 6, 8, lambda e: dict(
            enable=bool(e[2]), up=e[3] << 8 | e[4], down=e[5] << 8 | e[6], use_global=bool(e[7])))

    def get_safe_area(self, positions=None):
        """{pos: dict(up, down, use_global, enable)}"""
        return self._per_key(0x96, positions, 6, 8, lambda e: dict(
            up=e[2] << 8 | e[3], down=e[4] << 8 | e[5], use_global=bool(e[6]), enable=bool(e[7])))

    def get_key_types(self, positions=None):
        """{pos: raw key-type byte} (the vendor maps this to a key-feature type)."""
        return self._per_key(0x95, positions, 18, 3, lambda e: e[2])

    def _set_per_key(self, cmd, entries, per_req, sub=0):
        for i in range(0, len(entries), per_req):
            data = [b for e in entries[i : i + per_req] for b in e]
            self._xfer(_frame(cmd, sub, data))

    def set_travel(self, mapping):
        """{pos: (distance_raw, uses_global)}"""
        self._set_per_key(0x13, [(p >> 8, p & 0xFF, d >> 8, d & 0xFF, int(g)) for p, (d, g) in mapping.items()], 11)

    def set_rapid_trigger(self, mapping):
        """{pos: dict(enable, up, down, use_global)}"""
        self._set_per_key(0x19, [(p >> 8, p & 0xFF, int(v["enable"]), v["up"] >> 8, v["up"] & 0xFF,
                                  v["down"] >> 8, v["down"] & 0xFF, int(v["use_global"]))
                                 for p, v in mapping.items()], 6)

    def set_safe_area(self, mapping):
        """{pos: dict(up, down, use_global, enable)}"""
        self._set_per_key(0x16, [(p >> 8, p & 0xFF, v["up"] >> 8, v["up"] & 0xFF, v["down"] >> 8,
                                  v["down"] & 0xFF, int(v["use_global"]), int(v["enable"]))
                                 for p, v in mapping.items()], 6)

    def _adv_frame(self, layer, kind, data=(), length=None):
        p = [0] * PAYLOAD_LEN
        p[:6] = [CMD_ADVANCED, layer, kind, 1, 0, len(data) if length is None else length]
        p[6 : 6 + len(data)] = data
        p[-1] = 255 - (REPORT_ID + sum(p[:-1])) % 256
        return bytes([REPORT_ID] + p)

    def list_advanced_keys(self, layer=0):
        """Positions on a layer that have an advanced-key feature (dual-function, toggle, SOCD ...).

        The keyboard's fast "list" reply is only trusted when it is short and every entry checks out;
        after some removals it answers with its whole key table, so we then scan every key instead."""
        p = [0] * PAYLOAD_LEN
        p[:6] = [CMD_ADVANCED_GET, layer, 0, 1, 0, 0]
        p[-1] = 255 - (REPORT_ID + sum(p[:-1])) % 256
        r = self._xfer(bytes([REPORT_ID] + p))
        n = r[6]
        if n == 0:
            return []
        listed = [r[7 + i] << 8 | r[8 + i] for i in range(0, min(n, 56) - 1, 2)]
        if n <= 56 and all(pos in KEY_POS and self.get_advanced_key(layer, pos)["type"] != "none" for pos in listed):
            return listed
        return [pos for pos in KEY_POS if self.get_advanced_key(layer, pos)["type"] != "none"]

    def get_advanced_key(self, layer, pos):
        """dict(type=..., ...) for one key; types: none, toggle, mod_tap, dks, socd, multi, end.
        dks/end are returned with their raw bytes in 'raw' (not decoded)."""
        r = self._xfer(_frame(CMD_ADVANCED_GET, layer, [pos >> 8, pos & 0xFF]))
        t = r[3]
        name = ADV_TYPES.get(t, t)
        d = r[7:]
        if t == 1:
            return dict(type=name, value=int.from_bytes(d[2:6], "big"), delay=d[6] << 8 | d[7])
        if t == 2:
            return dict(type=name, pressed=int.from_bytes(d[2:6], "big"),
                        click=int.from_bytes(d[6:10], "big"), delay=d[10] << 8 | d[11])
        if t == 4:
            n = d[0]
            return dict(type=name, keys=[d[1 + 2 * i] << 8 | d[2 + 2 * i] for i in range(n)], mode=d[1 + 2 * n])
        if t == 5:
            n = d[2]
            return dict(type=name, steps=[(int.from_bytes(d[3 + 6 * i : 7 + 6 * i], "big"),
                                           d[7 + 6 * i] << 8 | d[8 + 6 * i]) for i in range(n)])
        return dict(type=name, raw=bytes(d[:56]))

    def _adv_send(self, layer, kind, data, length=None):
        self._xfer(self._adv_frame(layer, kind, data, length))

    def set_toggle_key(self, layer, pos, value, delay=0):
        self._adv_send(layer, 1, [pos >> 8, pos & 0xFF, *value.to_bytes(4, "big"), delay >> 8, delay & 0xFF], 8)

    def set_mod_tap_key(self, layer, pos, pressed, click, delay=200):
        """pressed = value sent while held, click = value sent on a quick tap, delay in the vendor's units."""
        self._adv_send(layer, 2, [pos >> 8, pos & 0xFF, *pressed.to_bytes(4, "big"), *click.to_bytes(4, "big"),
                                  delay >> 8, delay & 0xFF], 11)

    def set_socd(self, layer, positions, mode):
        """SOCD group: when the keys in `positions` conflict, `mode` decides (vendor values, see get)."""
        data = [len(positions)] + [b for p in positions for b in (p >> 8, p & 0xFF)] + [mode]
        self._adv_send(layer, 4, data, len(data))

    def set_multi_point(self, layer, pos, steps):
        """steps = [(key value, distance raw)]: send a different key at each travel distance."""
        data = [pos >> 8, pos & 0xFF, len(steps)] + [b for v, d in steps for b in (*v.to_bytes(4, "big"), d >> 8, d & 0xFF)]
        self._adv_send(layer, 5, data, len(steps) * 6 + 3)

    def remove_advanced_key(self, layer, pos):
        self._adv_send(layer, 0, [pos >> 8, pos & 0xFF, 0], 2)

    def live_start(self, positions):
        """Start the realtime travel stream for up to LIVE_MAX_KEYS keys. Poll with live_poll(); always
        pair with live_stop(). Read-only: it does not touch calibration or any setting."""
        self._live = True
        self.dev.write(_frame(CMD_LIVE, 0))
        time.sleep(0.1)
        self.live_track(positions)

    def live_track(self, positions):
        positions = list(positions)[:LIVE_MAX_KEYS]
        self.dev.write(_frame(CMD_LIVE, 1, [b for p in positions for b in (p >> 8, p & 0xFF)]))

    def live_poll(self, max_reports=40):
        """Non-blocking: [(pos, distance_raw, sensor_value, pressed)] for everything received so far.
        Distance in mm = raw * precision / 1000 (see raw_to_mm)."""
        out = []
        self.dev.set_nonblocking(1)        # hid's read(n, 0) would otherwise block until the next report
        try:
            for _ in range(max_reports):
                r = self.dev.read(64)
                if not r:
                    break
                if r[1] == CMD_LIVE and r[2] == 1:
                    n = r[6]
                    d = r[7 : 7 + n]
                    for i in range(0, n - 5, 6):
                        w = d[i + 4] << 8 | d[i + 5]
                        out.append((d[i] << 8 | d[i + 1], d[i + 2] << 8 | d[i + 3], w & 0x7FFF, bool(w & 0x8000)))
        finally:
            self.dev.set_nonblocking(0)
        return out

    def live_stop(self):
        self._live = False
        self.dev.write(_frame(CMD_LIVE, 2))
        time.sleep(0.2)
        while self.dev.read(64, 30):
            pass

    def calibration_start(self):
        """Enter calibration mode. The vendor app re-sends this every second while it is active, so a
        caller that stays in calibration should call it periodically. Always pair with calibration_stop()."""
        self._xfer(_frame(CMD_CALIBRATE, 0))

    def calibration_stop(self):
        self._xfer(_frame(CMD_CALIBRATE, 4))

    def get_calibration_range(self, positions=None):
        """{pos: (min, max)} raw sensor readings seen so far in calibration mode."""
        positions = list(positions if positions is not None else KEY_POS)
        out = {}
        for i in range(0, len(positions), 9):
            chunk = positions[i : i + 9]
            data = [b for p in chunk for b in (p >> 8, p & 0xFF)]
            r = self._xfer(_frame(CMD_CALIBRATE, 5, data))
            for j in range(len(chunk)):
                e = r[7 + j * 6 : 13 + j * 6]
                if len(e) == 6 and (e[0] << 8 | e[1]) == chunk[j]:
                    out[chunk[j]] = (e[4] << 8 | e[5], e[2] << 8 | e[3])
        return out

    def get_side_light(self):
        r = self._xfer(_frame(CMD_GET, SUB_SIDE_LIGHT))
        d = r[7:14]
        return dict(mode=d[0], mix=d[1] != 0, mix_mask=d[1], r=d[2], g=d[3], b=d[4], brightness=d[5], speed=d[6])

    def set_side_light(self, mode, r=255, g=0, b=0, brightness=20, speed=2, mix=False):
        # the vendor app sends a 4-byte body when mix is on; the layout is otherwise the main light's
        data = [mode, mix_byte(mix), r, g, b, brightness, speed]
        self._xfer(_frame(CMD_SET, SUB_SIDE_LIGHT, data))

    def get_key_colors(self, positions=None):
        """Return {pos: (r, g, b)} for the per-key (custom mode) colours, 11 keys per request."""
        positions = list(positions if positions is not None else KEY_POS)
        out = {}
        for i in range(0, len(positions), COLORS_PER_REQ):
            chunk = positions[i : i + COLORS_PER_REQ]
            data = [b for p in chunk for b in (p >> 8, p & 0xFF)]
            r = self._xfer(_frame(CMD_COLOR_GET, 0, data))
            for j in range(len(chunk)):
                e = r[7 + j * 5 : 12 + j * 5]
                if (e[0] << 8 | e[1]) == chunk[j]:
                    out[chunk[j]] = (e[2], e[3], e[4])
        return out

    def set_key_colors(self, colors):
        """Write {pos: (r, g, b)}. Shown while the light mode is custom (19)."""
        flat = [b for pos, (r, g, b_) in colors.items() for b in (pos >> 8, pos & 0xFF, r, g, b_)]
        chunks = [flat[i : i + 55] for i in range(0, len(flat), 55)]
        for idx, c in enumerate(chunks):
            p = [0] * PAYLOAD_LEN
            p[:6] = [CMD_COLOR_SET, 0, 0, len(chunks), idx, len(c)]
            p[6 : 6 + len(c)] = c
            p[-1] = 255 - (REPORT_ID + sum(p[:-1])) % 256
            self._xfer(bytes([REPORT_ID] + p))

    def get_keymap(self, layer=0, positions=None):
        """Return {pos: value} for the given layer (0..2). Reads 9 keys per request."""
        positions = list(positions if positions is not None else KEY_POS)
        out = {}
        for i in range(0, len(positions), KEYS_PER_REQ):
            chunk = positions[i : i + KEYS_PER_REQ]
            data = [b for p in chunk for b in (p >> 8, p & 0xFF)]
            r = self._xfer(_frame(CMD_KEYS_GET, layer, data))
            for j in range(len(chunk)):
                e = r[7 + j * 6 : 13 + j * 6]
                pos = e[0] << 8 | e[1]
                if pos == chunk[j]:
                    out[pos] = int.from_bytes(e[2:6], "big")
        return out

    def set_keys(self, layer, mapping):
        """Write {pos: value} on a layer. Value is the 32-bit code (see basic_key/consumer helpers)."""
        items = list(mapping.items())
        for i in range(0, len(items), KEYS_PER_REQ):
            data = []
            for pos, val in items[i : i + KEYS_PER_REQ]:
                data += [pos >> 8, pos & 0xFF, *val.to_bytes(4, "big")]
            self._xfer(_frame(CMD_KEYS_SET, layer, data))

    def set_key(self, layer, pos, value):
        self.set_keys(layer, {pos: value})

    def restore_layer(self, layer):
        """Write the factory keymap back to layer 0 or 1."""
        self.set_keys(layer, FACTORY_KEYMAP[layer])


def basic_key(usage, mods=0):
    """Plain HID key. With mods (LCtrl 1, LShift 2, LAlt 4, LWin 8, R* = <<4) it becomes a
    shortcut, which the vendor table encodes as mods<<16 | usage<<8 (not yet tested on hardware)."""
    return usage if not mods else mods << 16 | usage << 8


MODS_BY_BIT = {0x01: "LCtrl", 0x02: "LShift", 0x04: "LAlt", 0x08: "LWin",
               0x10: "RCtrl", 0x20: "RShift", 0x40: "RAlt", 0x80: "RWin"}


def modifier_key(mods):
    return mods << 16


def consumer_key(usage):
    return 0x02000000 | usage


# ---- value ranges (measured from the vendor app's UI limits for this model) ----
BRIGHTNESS_RANGE = (0, 20)
SPEED_RANGE = (0, 4)
LIGHT_MODES = {  # mode byte -> short name; mode 18 defaults to brightness 10, mode 3 brings its own colours
    0: "Off", 1: "Always on", 2: "Breathing", 3: "Neon", 4: "Burst", 5: "Rain", 6: "Rainbow wheel",
    7: "Key ripples", 8: "Starry sky", 9: "Snow trail", 10: "Flow", 11: "Drift", 12: "Follow",
    13: "Sine wave", 14: "Scan", 15: "Windmill", 16: "Waterfall", 17: "Bloom", 18: "Spin storm",
    19: "Custom (per key)",
}
# Distances: millimetres = raw * precision / 1000, where precision comes from get_precision() (5 here, so
# one raw step is 0.005 mm). The limits below are in thousandths of a millimetre.
# Which controls the vendor app offers per effect: "mix" = multicolour switch, "color" = single colour,
# "brightness", "speed". Effects without "color" always use their own RGB palette.
LIGHT_CAPABILITIES_DEFAULT = ("mix", "color", "brightness", "speed")
LIGHT_CAPABILITIES = {0: (), 1: ("mix", "color", "brightness"), 3: ("mix", "brightness", "speed"),
                      15: ("mix", "brightness", "speed"), 16: ("mix", "brightness", "speed"),
                      19: ("color", "brightness")}
SIDE_LIGHT_CAPABILITIES = {0: (), 2: ("mix", "brightness", "speed"), 3: ("mix", "color", "brightness")}


def light_capabilities(mode, side=False):
    table = SIDE_LIGHT_CAPABILITIES if side else LIGHT_CAPABILITIES
    return table.get(mode, LIGHT_CAPABILITIES_DEFAULT)


TRAVEL_RANGE_UM = (100, 4000)     # actuation point 0.1 - 4.0 mm
RAPID_TRIGGER_RANGE_UM = (None, 4000)  # lower bound = one precision step; 4.0 mm top
SAFE_AREA_RANGE_UM = (0, 500)     # dead zone 0 - 0.5 mm
MULTI_POINT_RANGE_UM = (200, 4000)  # the vendor slider is 0.10 - 4.00 mm in hundredths; raw = value * 10 / precision
TOGGLE_DELAY_MS = (0, 1000)       # default 200
MOD_TAP_DELAY_MS = (0, 1000)      # default 200
SOCD_MODES = {1: "last input wins", 3: "key 1 always wins", 4: "key 2 always wins", 0: "neutral (cancel both)"}
MACRO_NAME_MAX = 32
MACRO_REPEAT_COUNT = (1, 255)
MACRO_DELAY_MAX_MS = 0xFFFFF      # the 4-byte event only has 20 bits for the delay (the vendor UI allows more)
KEYMAP_LAYERS = 3
PROFILES = 3
PROFILE_NAME_MAX = 55
CALIBRATION_KEYS_PER_REQ = 9

# Factory keymaps captured from this keyboard (layer 0 = normal typing, layer 1 = Fn layer). Used by
# restore_layer(); they match the Fn guide for the COOL 68 exactly. Layer 2 is unused.
FACTORY_KEYMAP = {
    0: {
        1: 0x00000029, 15: 0x0000001E, 16: 0x0000001F, 17: 0x00000020,
        18: 0x00000021, 19: 0x00000022, 20: 0x00000023, 21: 0x00000024,
        22: 0x00000025, 23: 0x00000026, 24: 0x00000027, 25: 0x0000002D,
        26: 0x0000002E, 27: 0x0000002A, 28: 0x0000002B, 29: 0x00000014,
        30: 0x0000001A, 31: 0x00000008, 32: 0x00000015, 33: 0x00000017,
        34: 0x0000001C, 35: 0x00000018, 36: 0x0000000C, 37: 0x00000012,
        38: 0x00000013, 39: 0x0000002F, 40: 0x00000030, 41: 0x00000031,
        42: 0x00000039, 43: 0x00000004, 44: 0x00000016, 45: 0x00000007,
        46: 0x00000009, 47: 0x0000000A, 48: 0x0000000B, 49: 0x0000000D,
        50: 0x0000000E, 51: 0x0000000F, 52: 0x00000033, 53: 0x00000034,
        54: 0x00000028, 55: 0x00020000, 56: 0x0000001D, 57: 0x0000001B,
        58: 0x00000006, 59: 0x00000019, 60: 0x00000005, 61: 0x00000011,
        62: 0x00000010, 63: 0x00000036, 64: 0x00000037, 65: 0x00000038,
        66: 0x00200000, 67: 0x00010000, 68: 0x00080000, 69: 0x00040000,
        70: 0x0000002C, 71: 0x00400000, 72: 0x0D000000, 73: 0x00100000,
        74: 0x00000052, 75: 0x00000051, 76: 0x00000050, 77: 0x0000004F,
        98: 0x00000049, 99: 0x0000004C, 102: 0x0000004B, 103: 0x0000004E,
    },
    1: {
        1: 0x00000035, 15: 0x0000003A, 16: 0x0000003B, 17: 0x0000003C,
        18: 0x0000003D, 19: 0x0000003E, 20: 0x0000003F, 21: 0x00000040,
        22: 0x00000041, 23: 0x00000042, 24: 0x00000043, 25: 0x00000044,
        26: 0x00000045, 27: 0x0000002A, 28: 0x07000004, 29: 0x00000014,
        30: 0x0000001A, 31: 0x00000008, 32: 0x00000015, 33: 0x00000017,
        34: 0x0000001C, 35: 0x00000018, 36: 0x0000000C, 37: 0x00000012,
        38: 0x00000013, 39: 0x08000000, 40: 0x08020000, 41: 0x07000012,
        42: 0x00000039, 43: 0x00000004, 44: 0x00000016, 45: 0x00000007,
        46: 0x00000009, 47: 0x0000000A, 48: 0x0000000B, 49: 0x0000000D,
        50: 0x0000000E, 51: 0x0000000F, 52: 0x00000033, 53: 0x00000034,
        54: 0x00000028, 55: 0x00020000, 56: 0x020000B6, 57: 0x020000CD,
        58: 0x020000B5, 59: 0x020000E9, 60: 0x020000EA, 61: 0x020000E2,
        62: 0x00000010, 63: 0x00000036, 64: 0x00000037, 65: 0x00000038,
        66: 0x00200000, 67: 0x00010000, 68: 0x07000001, 69: 0x00040000,
        70: 0x08030000, 71: 0x08000001, 72: 0x0D000000, 73: 0x08020001,
        74: 0x08030101, 75: 0x08030201, 76: 0x08040200, 77: 0x08040100,
        98: 0x00000049, 99: 0x0000004C, 102: 0x0000004B, 103: 0x0000004E,
    },
}


def raw_to_mm(raw, precision):
    return raw * precision / 1000.0


def mm_to_raw(mm, precision):
    return round(mm * 1000.0 / precision)


def macro_event(key, down=True, delay_ms=0):
    """One macro step: a key/modifier/mouse-button press or release, then wait delay_ms.

    key is a name from MACRO_KEYS (the vendor table: 'KeyA', 'ShiftLeft', 'MouseKey0', ...)."""
    value, kind = MACRO_KEYS[key]
    flags = (0x00, 0x10, 0x20)[kind] | (0x00 if down else 0x80)
    return [flags | (delay_ms >> 16 & 0x0F), delay_ms >> 8 & 0xFF, delay_ms & 0xFF, value]


def macro_key(mode=MACRO_REPEAT, count=1, idx=0):
    """Key value that triggers macro #idx: mode MACRO_LOOP/HOLD/REPEAT, count used by REPEAT."""
    return 0x03000000 | mode << 16 | count << 8 | idx

# macro key table: name -> (code, kind) with kind 0 = keyboard, 1 = modifier, 2 = mouse button
MACRO_KEYS = {
    "MouseKey0": (1, 2),
    "MouseKey1": (4, 2),
    "MouseKey2": (2, 2),
    "MouseKey3": (8, 2),
    "MouseKey4": (16, 2),
    "Escape": (41, 0),
    "F1": (58, 0),
    "F2": (59, 0),
    "F3": (60, 0),
    "F4": (61, 0),
    "F5": (62, 0),
    "F6": (63, 0),
    "F7": (64, 0),
    "F8": (65, 0),
    "F9": (66, 0),
    "F10": (67, 0),
    "F11": (68, 0),
    "F12": (69, 0),
    "Delete": (76, 0),
    "Home": (74, 0),
    "End": (77, 0),
    "PageUp": (75, 0),
    "PageDown": (78, 0),
    "Backquote": (53, 0),
    "Digit1": (30, 0),
    "Digit2": (31, 0),
    "Digit3": (32, 0),
    "Digit4": (33, 0),
    "Digit5": (34, 0),
    "Digit6": (35, 0),
    "Digit7": (36, 0),
    "Digit8": (37, 0),
    "Digit9": (38, 0),
    "Digit0": (39, 0),
    "Minus": (45, 0),
    "Equal": (46, 0),
    "Backspace": (42, 0),
    "NumLock": (83, 0),
    "NumpadDivide": (84, 0),
    "NumpadMultiply": (85, 0),
    "NumpadSubtract": (86, 0),
    "Tab": (43, 0),
    "KeyQ": (20, 0),
    "KeyW": (26, 0),
    "KeyE": (8, 0),
    "KeyR": (21, 0),
    "KeyT": (23, 0),
    "KeyY": (28, 0),
    "KeyU": (24, 0),
    "KeyI": (12, 0),
    "KeyO": (18, 0),
    "KeyP": (19, 0),
    "BracketLeft": (47, 0),
    "BracketRight": (48, 0),
    "Backslash": (49, 0),
    "Numpad7": (95, 0),
    "Numpad8": (96, 0),
    "Numpad9": (97, 0),
    "NumpadAdd": (87, 0),
    "CapsLock": (57, 0),
    "KeyA": (4, 0),
    "KeyS": (22, 0),
    "KeyD": (7, 0),
    "KeyF": (9, 0),
    "KeyG": (10, 0),
    "KeyH": (11, 0),
    "KeyJ": (13, 0),
    "KeyK": (14, 0),
    "KeyL": (15, 0),
    "Semicolon": (51, 0),
    "Quote": (52, 0),
    "Enter": (40, 0),
    "Numpad4": (92, 0),
    "Numpad5": (93, 0),
    "Numpad6": (94, 0),
    "ShiftLeft": (225, 1),
    "KeyZ": (29, 0),
    "KeyX": (27, 0),
    "KeyC": (6, 0),
    "KeyV": (25, 0),
    "KeyB": (5, 0),
    "KeyN": (17, 0),
    "KeyM": (16, 0),
    "Comma": (54, 0),
    "Period": (55, 0),
    "Slash": (56, 0),
    "PrintScreen": (70, 0),
    "ScrollLock": (71, 0),
    "Pause": (72, 0),
    "Insert": (73, 0),
    "ShiftRight": (229, 1),
    "ArrowUp": (82, 0),
    "Numpad1": (89, 0),
    "Numpad2": (90, 0),
    "Numpad3": (91, 0),
    "NumpadEnter": (88, 0),
    "ControlLeft": (224, 1),
    "MetaLeft": (227, 1),
    "ContextMenu": (231, 1),
    "AltLeft": (226, 1),
    "Space": (44, 0),
    "AltRight": (230, 1),
    "ControlRight": (228, 1),
    "ArrowLeft": (80, 0),
    "ArrowDown": (81, 0),
    "ArrowRight": (79, 0),
    "Numpad0": (98, 0),
    "NumpadDecimal": (99, 0),
}


if __name__ == "__main__":
    kb = Cool68()
    print("firmware 0x%04X  profile %d  polling %d Hz" % (kb.get_firmware_version(), kb.get_profile(), kb.get_polling()))
    print("backlight:", kb.get_light())
    print("side light:", kb.get_side_light())
    kb.close()
