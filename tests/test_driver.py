"""Driver tests that need no keyboard: framing, encodings, tables."""
import cool68
from cool68 import (FACTORY_KEYMAP, KEY_POS, MACRO_KEYS, REPORT_ID, _frame, basic_key, consumer_key, light_capabilities,
                    macro_event, macro_key, mix_byte, mm_to_raw, modifier_key, raw_to_mm)


def test_frame_is_64_bytes_with_report_id():
    f = _frame(0x84, 0x01)
    assert len(f) == 64 and f[0] == REPORT_ID == 9


def test_frame_header_layout():
    f = _frame(0x04, 0x01, [16, 7, 255, 0, 0, 20, 2])
    assert list(f[1:8]) == [0x04, 0x01, 0, 1, 0, 7, 16]


def test_frame_checksum_formula():
    for cmd, sub, data in ((0x84, 1, ()), (0x04, 1, (1, 2, 3)), (0x83, 2, tuple(range(18))), (0x12, 0, (255,) * 40)):
        f = _frame(cmd, sub, data)
        assert f[-1] == 255 - sum(f[:-1]) % 256
        assert (sum(f[:-1]) + f[-1]) % 256 == 255


def test_mix_byte():
    assert mix_byte(True) == 7 and mix_byte(False) == 0 and mix_byte(None) == 0
    assert mix_byte(5) == 5 and mix_byte(0) == 0


def test_distance_conversion_round_trips():
    assert raw_to_mm(200, 5) == 1.0
    assert abs(raw_to_mm(82, 5) - 0.41) < 1e-9
    for mm in (0.1, 0.83, 1.5, 4.0):
        assert abs(raw_to_mm(mm_to_raw(mm, 5), 5) - mm) <= 0.0025


def test_key_value_encodings():
    assert basic_key(0x04) == 0x04                       # A
    assert modifier_key(0x02) == 0x00020000              # left shift
    assert basic_key(0x06, 0x01) == 0x00010600           # Ctrl+C
    assert consumer_key(0xCD) == 0x020000CD              # play/pause
    assert macro_key(4, 1, 0) == 0x03040100


def test_macro_event_encoding():
    assert macro_event("KeyA", True, 50) == [0, 0, 50, 4]
    assert macro_event("KeyA", False, 0) == [0x80, 0, 0, 4]
    assert macro_event("ShiftLeft", False, 0) == [0x90, 0, 0, 225]
    assert macro_event("MouseKey0", True, 0)[0] == 0x20
    big = macro_event("KeyA", True, 0xABCDE)             # the delay is 20 bits: top nibble lives in byte 0
    assert big == [0x0A, 0xBC, 0xDE, 4]


def test_all_macro_keys_have_valid_kinds():
    assert len(MACRO_KEYS) == 108
    assert all(kind in (0, 1, 2) for _, kind in MACRO_KEYS.values())


def test_factory_keymaps_cover_every_key():
    for layer in (0, 1):
        assert set(FACTORY_KEYMAP[layer]) == set(KEY_POS)
    assert len(KEY_POS) == 68
    assert FACTORY_KEYMAP[0][72] >> 24 == 0x0D            # the Fn key


def test_fn_layer_matches_the_documented_guide():
    fn = FACTORY_KEYMAP[1]
    names = {v: k for k, v in cool68.KEY_NAMES.items()}
    assert fn[names["Z"]] == 0x020000B6 and fn[names["X"]] == 0x020000CD and fn[names["C"]] == 0x020000B5
    assert fn[names["["]] == 0x08000000 and fn[names["]"]] == 0x08020000
    assert fn[names["LWin"]] == 0x07000001
    assert fn[names["Esc"]] == 0x35                       # Fn+Esc is ` (Shift+Fn+Esc gives ~)
    assert fn[names["-"]] == 0x44 and fn[names["="]] == 0x45   # F11, F12
    assert [fn[names[str(d)]] for d in (1, 2, 3)] == [0x3A, 0x3B, 0x3C]     # F1 F2 F3


def test_light_capabilities():
    assert light_capabilities(0) == ()
    assert "color" not in light_capabilities(16) and "color" not in light_capabilities(3)
    assert "speed" not in light_capabilities(1)
    assert set(light_capabilities(7)) == {"mix", "color", "brightness", "speed"}
    assert "color" not in light_capabilities(2, side=True)


def test_light_modes_table():
    assert sorted(cool68.LIGHT_MODES) == list(range(20))
    assert cool68.LIGHT_MODES[19].startswith("Custom")


def test_polling_levels():
    assert cool68.POLLING_LEVELS == {1000: 0, 2000: 6, 4000: 5, 8000: 4}
