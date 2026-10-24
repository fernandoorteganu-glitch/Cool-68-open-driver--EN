"""App logic that needs Qt classes but no window and no keyboard."""
from PySide6.QtGui import QColor

import cool68
from app import effects, keys
from app.widgets import KEY_CENTERS, ROWS, heat_color


def test_layout_matches_the_driver_key_positions():
    layout = [pos for row in ROWS for pos, _ in row]
    assert sorted(layout) == sorted(cool68.KEY_POS)
    assert set(KEY_CENTERS) == set(cool68.KEY_POS)


def test_every_row_is_16_units_wide():
    for row in ROWS:
        assert abs(sum(w for _, w in row) - 16) < 1e-9


def test_describe_labels():
    assert keys.describe(0x04) == "A"
    assert keys.describe(0x00020000) == "LShift"
    assert keys.describe(0x00010600) == "Copy"
    assert keys.describe(0x020000E9) == "Vol +"
    assert keys.describe(0x07000001, short=True) == "Win lock"
    assert keys.describe(0x08000000, short=True) == "Light mode"
    assert keys.describe(0x03040100) == "Macro 1"
    assert keys.describe(0) == "—"


def test_the_two_idle_fn_keys_are_labelled_no_function():
    assert keys.describe(0x07000004) == keys.describe(0x07000012) == "No function"


def test_catalogue_values_round_trip_through_describe():
    for category, items in keys.catalogue().items():
        for name, value in items:
            assert keys.describe(value)       # every assignable key has a readable label


def test_every_effect_renders_without_errors():
    base = QColor("#ff2d55")
    for mode in range(20):
        for mix in (False, True):
            for t in (0.0, 1.7, 9.3, 120.0):
                out = effects.render(mode, t, KEY_CENTERS, base, mix, 20, 2, [(30, t - 0.4), (70, t - 1.5)])
                assert all(isinstance(c, QColor) for c in out.values())


def test_off_and_zero_brightness_render_nothing():
    assert effects.render(0, 1.0, KEY_CENTERS, QColor("red"), False, 20, 2, []) == {}
    assert effects.render(1, 1.0, KEY_CENTERS, QColor("red"), False, 0, 2, []) == {}


def test_single_colour_effects_stay_on_the_chosen_hue():
    base = QColor("#2979ff")
    for mode in range(1, 19):
        out = effects.render(mode, 2.0, KEY_CENTERS, base, False, 20, 2, [(30, 1.7)])
        for c in out.values():
            if c.saturationF() > 0.15 and c.valueF() > 0.05:
                assert abs(c.hueF() - base.hueF()) < 0.03


def test_flow_snakes_through_the_keys_in_reading_order():
    order = effects._reading_order(KEY_CENTERS)
    assert order[1] == 0                                  # Esc is first
    assert order[77] == len(order) - 1                    # Right arrow is last


def test_effect_groups_cover_every_mode_once():
    modes = [m for _, _, group in effects.GROUPS for m in group]
    assert sorted(modes) == list(range(20))


def test_heat_color_runs_from_hot_to_cold():
    assert heat_color(0.1).red() > heat_color(0.1).blue()
    assert heat_color(4.0).blue() > heat_color(4.0).red()
