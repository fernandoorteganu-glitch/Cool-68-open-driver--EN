"""Widget behaviour that needs a QApplication (offscreen) but no keyboard."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from app.pages_a import ZonePanel


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def state(**kw):
    d = dict(mode=1, mix=False, mix_mask=0, r=0, g=255, b=255, brightness=20, speed=2)
    d.update(kw)
    return d


def test_known_colour_shows_no_note(qapp):
    p = ZonePanel()
    p.load(state())
    assert p.note.isHidden()
    assert p.picker.color().name() == "#00ffff"


def test_black_single_colour_after_power_cycle_shows_the_note_and_white(qapp):
    p = ZonePanel()
    p.load(state(r=0, g=0, b=0))
    assert not p.note.isHidden()
    assert p.picker.color().name() == "#ffffff"


def test_picking_a_colour_clears_the_note(qapp):
    p = ZonePanel()
    p.load(state(r=0, g=0, b=0))
    p.picker.changed.emit(QColor("#ff0000"))
    assert p.note.isHidden()


def test_multicolour_with_black_colour_needs_no_note(qapp):
    p = ZonePanel()
    p.load(state(r=0, g=0, b=0, mix=True, mix_mask=7))
    assert p.note.isHidden()


def test_note_hidden_for_effects_without_a_colour_picker(qapp):
    p = ZonePanel()
    p.load(state(r=0, g=0, b=0))
    p.set_caps(("mix", "brightness", "speed"))         # e.g. Waterfall: no colour choice
    assert p.note.isHidden()
