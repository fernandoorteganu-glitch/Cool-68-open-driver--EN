# COOL 68 USB configuration protocol

Reference for the keyboard's configuration protocol as implemented by `cool68.py`. It was worked out from USB captures of
the keyboard's own traffic and by testing every command on real hardware. **Only configuration commands are
documented here; nothing in this project flashes firmware.**

## Transport

| | |
|---|---|
| Device | USB `372E:1083`, "COOL 68 BY Tech" (wired) |
| Interfaces | 0 = keyboard, 1 = media keys / mouse, **2 = configuration** |
| Config channel | interface 2, usage page `0xFF60`, usage `0x61` (the `0xFF00` collection does not answer) |
| Reports | report id `0x09`, 64 bytes each way (endpoints OUT `0x02`, IN `0x83`) |
| Not VIA | a VIA "get version" gets no reply |

## Frame

```
byte 0      report id = 0x09
byte 1      cmd
byte 2      sub (a setting number, layer number, key group ...)
byte 3      0   (advanced keys use this as the type)
byte 4      1   (number of packets in a multi-packet transfer)
byte 5      0   (packet index)
byte 6      data length
bytes 7..   data
byte 63     checksum = 255 - (sum(bytes 0..62) mod 256)
```

The reply echoes `cmd` and `sub` in bytes 1 and 2; reply data starts at byte 7. A *get* command is the *set* command
with bit 7 set (`0x84` reads what `0x04` writes). The checksum includes the report id.

The IN endpoint is shared: replies and pushed events (the live stream) arrive on the same pipe, so match on `cmd`/`sub`.

## Commands

### Lighting

| | cmd | sub | data |
|---|---|---|---|
| Backlight | `0x04` / `0x84` | `0x01` | `mode, mix, R, G, B, brightness, speed` |
| Side light | `0x04` / `0x84` | `0x06` | same layout |

* `mode` 0 = off, 1–18 effects, **19 = custom (per-key colours)**. Brightness 0–20, speed 0–4.
* `mix` = **multicolour**. Only `0` (single colour) and `7` (multicolour) mean anything: the keyboard stores any value
  0–255 but treats every non-7 value as a single colour. **While mix is on, the RGB bytes of a write are ignored** and the
  last single colour is kept, so to store a colour write it with `mix = 0` first.
* In multicolour, *Always on* and *Scan* show one palette colour (yellow); other effects use their own palette.
* **After a power cycle the keyboard reads its colour back as `0, 0, 0`** while the LEDs still show the real colour
  (checked by unplugging and replugging). Mode, brightness, speed and `mix` read back correctly. Do not treat a black
  read-back as the actual colour; writing one back would change the LEDs.
* Which controls an effect honours: Neon (3), Windmill (15) and Waterfall (16) ignore the colour; Always on (1) has no speed;
  Off has none; Custom has colour and brightness only.

### Per-key colours

| | cmd | data |
|---|---|---|
| Set | `0x06` | `[0x06, 0, 0, nchunks, idx, len, (pos_hi, pos_lo, R, G, B) * 11]` |
| Get | `0x86` | list of 2-byte key ids, 11 keys per request, reply entries are 5 bytes |

Colours only show while the backlight mode is 19, and a write made *before* switching to mode 19 can be lost: **switch to
mode 19 first, then write the colours.**

### Keymap

| | cmd | sub | data |
|---|---|---|---|
| Get | `0x83` | layer 0–2 | list of 2-byte key ids (9 per request); reply entries `pos(2) + value(4)` |
| Set | `0x03` | layer | entries `pos(2) + value(4)`, 9 per request |

Key value (32 bits, big-endian):

| Kind | Value |
|---|---|
| Plain key | `0x000000UU`, `UU` = HID usage (`0x04` = A) |
| Modifier | `0x00MM0000`, `MM` bits: LCtrl 01, LShift 02, LAlt 04, LWin 08, then R* = `<<4` |
| Shortcut | `0x00MMUU00` (e.g. Ctrl+C `0x00010600`) |
| Media | `0x02000000 | usage` (e.g. play/pause `0x020000CD`) |
| Mouse | `0x01xx0100` (left `0x01010100`, right `0x01020100`) |
| Macro | `0x03, mode, count, index` (mode 4 = repeat `count` times works; 1 loop and 2 hold are defined by the vendor tool) |
| Fn | `0x0D000000` (Fn), `0x0D010000` (Fn1) |
| Fn-layer functions | `0x08 fn dir zone`: fn 00 mode / 02 colour / 03 brightness / 04 speed, dir 01 up / 02 down, zone 00 backlight / 01 side light; `0x07000001` Win-lock. `0x07000004` and `0x07000012` do nothing |

Key ids for the 68 keys are listed in `cool68.KEY_NAMES` (Esc = 1, `1`..`0` = 15..24, Space = 70, Fn = 72 ...).

### Hall-effect tuning

Distances are raw units: **mm = raw × precision / 1000**, precision read with `0x82` sub `6`/`8` (5 on this keyboard, so one
step is 0.005 mm).

| | get | set | entry |
|---|---|---|---|
| Actuation distance | `0x93` | `0x13` | `pos(2), distance(2), use_global(1)`, 11 keys / request |
| Rapid trigger | `0x99` | `0x19` | `pos(2), enable(1), up(2), down(2), use_global(1)`, 6 keys / request |
| Dead zones | `0x96` | `0x16` | `pos(2), up(2), down(2), use_global(1), enable(1)`, 6 keys / request |

Ranges used by the vendor tool: actuation 0.1–4.0 mm, rapid trigger one step–4.0 mm, dead zone 0–0.5 mm.

### Advanced keys

`cmd 0x12` (set) / `0x92` (get), header `[cmd, layer, TYPE, 1, 0, len, ...]`.

| TYPE | Meaning | Data |
|---|---|---|
| 0 | remove | `pos(2), 0` |
| 1 | toggle | `pos(2), value(4), delay(2)` |
| 2 | mod-tap | `pos(2), held(4), tap(4), delay(2)` |
| 3 | dynamic keystroke | not decoded |
| 4 | SOCD | `count, key ids(2 each)..., mode` (1 last input, 3 key 1, 4 key 2, 0 neutral) |
| 5 | multi-point | `pos(2), count, (value(4), distance(2)) * count` |
| 6 | "end" | not decoded |

The fast "list" read (`0x92` with no key) occasionally answers with the keyboard's whole key table instead of an empty
list; verify each entry (or scan every key) before trusting it.

### Macros

`cmd 0x05`, 56-byte chunks: `[0x05, 0, 0, nchunks, idx, len, ...]`. The blob is a table of `[offset(2), length(2)]` per
macro (offsets count from the start of the blob) followed by the bodies `[name_len, name, events...]`. An event is 4 bytes:
`[flags | delay>>16 & 0x0F, delay>>8, delay, code]` with flags `0x00/0x80` = key down/up, `0x10/0x90` modifier,
`0x20/0xA0` mouse button, delay 20 bits. **An upload replaces every macro on the keyboard.**

### Settings

Single-byte settings use `0x04`/`0x84` with these `sub` numbers:

| sub | Setting | Notes |
|---|---|---|
| `0x11` | Mac layout | 0/1 |
| `0x13` | Sleep timeout | write only; units of 30 s, 0 = never |
| `0x15` | Windows-key lock | 0/1 |
| `0x17` | Polling rate | `0`=1000 Hz, `6`=2000, `5`=4000, `4`=8000. **The keyboard re-enumerates on USB when this changes** and the reply can be lost |
| `0x18` | Key-combo mode | 0/1 |
| `0x19` | Auto-calibration | 0/1 |
| `0x1F` | Overdrive | 0/1 |

Info: `0x82` sub `1` = device id (6 bytes, big-endian), sub `2` = firmware (little-endian 16 bit).
Profiles: `0x90` / `0x10` current profile (0–2); `0x9A` / `0x1A` profile name (`sub` = profile, data `[len, utf-8...]`, reply length 255 = unnamed).

### Live key travel

| | cmd | sub | |
|---|---|---|---|
| Start | `0x98` | 0 | |
| Choose keys | `0x98` | 1 | list of 2-byte key ids |
| Stop | `0x98` | 2 | |

While running, the keyboard pushes about 20 reports per second: `cmd 0x98, sub 1`, entries of 6 bytes
`pos(2), distance(2), sensor(2)`, where bit 15 of `sensor` = pressed and its low 15 bits = the raw sensor value.
Distance converts to mm like the settings above. Without a key list it follows Enter. **Ask for at most 9 keys**; a 28-key
request once dropped the USB connection. Always send *stop*.

### Calibration (read only here)

`cmd 0x94` sub `5` with a list of key ids (9 per request) reads each key's recorded `(min, max)` sensor range. Sub `0`
starts and sub `4` stops the vendor's calibration mode, which streams every key and can **rewrite the calibration**;
this project does not use it.

## Implementation notes

* The Python `hid` package's `read(n, 0)` **blocks**; use `set_nonblocking(1)` to poll.
* Every command above is idempotent, so resending after a lost reply is safe.
* Writing a per-key table in chunks needs one request per chunk; a full 68-key frame takes about 50 ms.
