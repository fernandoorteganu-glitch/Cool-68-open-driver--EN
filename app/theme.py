"""Colours, fonts and the global stylesheet."""
import sys
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase

BG = "#0a0c11"
SIDEBAR = "#0d1016"
CARD = "#141824"
CARD_HI = "#1a2030"
BORDER = "#242b3d"
TEXT = "#e8ebf4"
MUTED = "#8a93aa"
ACCENT = "#8b5cf6"
ACCENT2 = "#22d3ee"
GOOD = "#3ddc97"
BAD = "#ff5d73"
WARN = "#ffb84d"
PINK = "#ff4fa3"
ORANGE = "#ff9f43"
BLUE = "#4f8cff"

# page title -> (colour 1, colour 2): used for the title gradient, nav icon, card edge and background glow
PAGE_COLORS = {
    "Dashboard": ("#8b5cf6", "#22d3ee"),
    "Keymap": ("#4f8cff", "#22d3ee"),
    "Lighting": ("#ff4fa3", "#8b5cf6"),
    "Performance": ("#ff9f43", "#ff4f6d"),
    "Macros": ("#3ddc97", "#22d3ee"),
    "Advanced keys": ("#22d3ee", "#8b5cf6"),
    "Settings": ("#9fb0d6", "#4f8cff"),
}

BODY_FONT = "Poppins"
HEAD_FONT = "Rajdhani"


def load_fonts():
    """Register the bundled fonts (falls back to Segoe UI if they are missing)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent)) / "app" / "fonts"
    for f in sorted(base.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(f))

ICON_FONT = "Segoe Fluent Icons"


def _family(preferred, *fallback):
    fams = set(QFontDatabase.families())
    return next((f for f in (preferred, *fallback) if f in fams), "Arial")


def ui_font(size=10, weight=QFont.Normal):
    f = QFont(_family(BODY_FONT, "Segoe UI Variable Text", "Segoe UI"), size)
    f.setWeight(weight)
    return f


def head_font(size=16, weight=QFont.Bold):
    f = QFont(_family(HEAD_FONT, "Bahnschrift", "Segoe UI"), size)
    f.setWeight(weight)
    return f


def icon_font(size=14):
    return QFont(ICON_FONT, size)


def mix(a, b, t):
    """Blend colour a towards b by t (0..1)."""
    a, b = QColor(a), QColor(b)
    return QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t))


def stylesheet():
    return f"""
* {{ outline: 0; }}
QWidget {{ color: {TEXT}; font-family: '{BODY_FONT}','Segoe UI'; font-size: 9pt; }}
QMainWindow, #root {{ background: {BG}; }}
#sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
#card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 16px; }}
#cardInner {{ background: {CARD_HI}; border: 1px solid {BORDER}; border-radius: 12px; }}
QLabel {{ background: transparent; }}
QLabel#gtitle {{ font-family: '{HEAD_FONT}'; font-size: 30pt; font-weight: 700; letter-spacing: 1px; }}
QLabel#h2 {{ font-family: '{HEAD_FONT}'; font-size: 16pt; font-weight: 700; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#value {{ color: {ACCENT2}; font-weight: 600; }}
QLabel#brand {{ font-family: '{HEAD_FONT}'; font-size: 20pt; font-weight: 700; letter-spacing: 2px; }}

QPushButton {{ background: {CARD_HI}; border: 1px solid {BORDER}; border-radius: 10px; padding: 8px 16px; }}
QPushButton:hover {{ border-color: {ACCENT}; background: #1f2640; }}
QPushButton:pressed {{ background: #262e4d; }}
QPushButton:disabled {{ color: #5b6379; }}
QPushButton[accent="true"] {{ border: none; font-weight: 600;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {ACCENT}, stop:1 {BLUE}); }}
QPushButton[accent="true"]:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #a078ff, stop:1 #6fa4ff); }}
QPushButton[danger="true"] {{ border: 1px solid #5a2a36; color: {BAD}; }}
QPushButton[pill="true"] {{ border-radius: 14px; padding: 6px 16px; background: transparent; border: 1px solid {BORDER}; color: {MUTED}; }}
QPushButton[pill="true"]:checked {{ color: white; border: 1px solid {ACCENT};
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(139,92,246,190), stop:1 rgba(34,211,238,140)); }}
QPushButton[tile="true"] {{ border-radius: 12px; padding: 10px 6px; text-align: center; background: {CARD_HI}; }}
QPushButton[tile="true"]:checked {{ border: 2px solid {ACCENT2}; background: #1a2740; color: white; }}
QPushButton[chip="true"] {{ border-radius: 8px; padding: 5px 10px; min-width: 34px; }}
QPushButton[chip="true"]:checked {{ border: 2px solid {ACCENT2}; color: white; font-weight: 600;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(139,92,246,200), stop:1 rgba(34,211,238,150)); }}

QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{ background: {CARD_HI}; border: 1px solid {BORDER}; border-radius: 10px;
    padding: 7px 10px; selection-background-color: {ACCENT}; }}
QComboBox:hover, QLineEdit:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {CARD}; border: 1px solid {BORDER}; selection-background-color: {ACCENT}; outline: 0; }}

QSlider::groove:horizontal {{ height: 6px; background: #232a3b; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ border-radius: 3px;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {ACCENT}, stop:1 {ACCENT2}); }}
QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; background: white; border: 3px solid {ACCENT}; }}
QSlider::handle:horizontal:hover {{ border-color: {ACCENT2}; }}
QSlider::groove:vertical {{ width: 6px; background: #232a3b; border-radius: 3px; }}
QSlider::add-page:vertical {{ border-radius: 3px;
    background: qlineargradient(x1:0,y1:1,x2:0,y2:0, stop:0 {ACCENT}, stop:1 {ACCENT2}); }}
QSlider::handle:vertical {{ height: 16px; width: 16px; margin: 0 -6px; border-radius: 8px; background: white; border: 3px solid {ACCENT}; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #2b3350; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ height: 10px; background: transparent; }}
QScrollBar::handle:horizontal {{ background: #2b3350; border-radius: 4px; }}
QToolTip {{ background: {CARD_HI}; color: {TEXT}; border: 1px solid {ACCENT}; padding: 6px; border-radius: 6px; }}
QListWidget {{ background: {CARD_HI}; border: 1px solid {BORDER}; border-radius: 12px; padding: 4px; }}
QListWidget::item {{ padding: 8px 10px; border-radius: 8px; }}
QListWidget::item:selected {{ background: rgba(139,92,246,110); color: white; }}
QTableWidget {{ background: {CARD_HI}; border: 1px solid {BORDER}; border-radius: 12px; gridline-color: {BORDER}; }}
QHeaderView::section {{ background: {CARD}; border: none; padding: 6px; color: {MUTED}; }}
QPlainTextEdit {{ background: {CARD_HI}; border: 1px solid {BORDER}; border-radius: 12px; padding: 8px; }}
"""
