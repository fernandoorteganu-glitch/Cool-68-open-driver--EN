"""Main window: sidebar navigation, page stack with fade transitions, connection handling."""
import ctypes
import os
import sys
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import (QApplication, QMessageBox, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMainWindow,
                               QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

import cool68

from . import __version__, theme
from .pages_a import DashboardPage, KeymapPage, LightingPage
from .pages_b import AdvancedPage, MacrosPage, PerformancePage, SettingsPage
from .widgets import Card
from .store import MacroStore
from .widgets import NavButton, Toast, button, label

NAV = [("", "Dashboard"), ("", "Keymap"), ("", "Lighting"), ("", "Performance"),
       ("", "Macros"), ("", "Advanced keys"), ("", "Settings")]


def app_icon():
    pm = QPixmap(256, 256)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, 256, 256)
    g.setColorAt(0, QColor(theme.ACCENT))
    g.setColorAt(1, QColor(theme.ACCENT2))
    p.setBrush(g)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(8, 8, 240, 240, 56, 56)
    p.setBrush(QColor(255, 255, 255, 235))
    for r, c in ((0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)):
        p.drawRoundedRect(46 + c * 56, 70 + r * 56, 44, 44, 11, 11)
    p.end()
    return QIcon(pm)


class Root(QWidget):
    """Window background with two soft colour glows that follow the current page."""

    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.colors = theme.PAGE_COLORS["Dashboard"]

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.BG))
        w, h = self.width(), self.height()
        for (cx, cy, r), col, a in (((w * 0.88, -h * 0.02, w * 0.62), self.colors[0], 70),
                                    ((w * 0.35, h * 1.10, w * 0.55), self.colors[1], 52)):
            g = QRadialGradient(cx, cy, r)
            c = QColor(col)
            c.setAlpha(a)
            g.setColorAt(0, c)
            c.setAlpha(0)
            g.setColorAt(1, c)
            p.fillRect(self.rect(), g)


class Ctx:
    """What pages need from the app: the keyboard, macro storage, toasts and error handling."""

    def __init__(self, win):
        self.win = win
        self.kb = None
        self.macros = MacroStore()

    def toast(self, text, kind="ok"):
        self.win.toast.show_message(text, kind)

    def fail(self, e):
        if self.kb is None:
            self.toast("Keyboard not connected. Plug it in and the app reconnects by itself.", "error")
            return
        self.win.set_status(False)
        self.toast(str(e) or e.__class__.__name__, "error")

    def reconnect_soon(self, ms=1800):
        """After a change that makes the keyboard re-enumerate (polling rate), reopen the connection."""
        QTimer.singleShot(ms, lambda: self.win.connect(quiet=True))

    def reload_all(self):
        for p in self.win.pages:
            p.invalidate()

    def refresh_macro_lists(self):
        self.win.pages[1].fill_grid()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("COOL 68 Open Driver App")
        self.setWindowIcon(app_icon())
        self.resize(1340, 860)
        self.setMinimumSize(1280, 760)
        self.ctx = Ctx(self)
        root = Root()
        self.root = root
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.build_sidebar())
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.pages = [DashboardPage(self.ctx), KeymapPage(self.ctx), LightingPage(self.ctx), PerformancePage(self.ctx),
                      MacrosPage(self.ctx), AdvancedPage(self.ctx), SettingsPage(self.ctx)]
        for p in self.pages:
            for card in p.findChildren(Card):
                card.colors = p.page_colors
            sc = QScrollArea()
            sc.setWidgetResizable(True)
            sc.setFrameShape(QFrame.NoFrame)
            sc.viewport().setAutoFillBackground(False)
            sc.setWidget(p)
            p.setAutoFillBackground(False)
            self.stack.addWidget(sc)
        self.toast = Toast(root)
        self.navs[0].setChecked(True)
        self.online = False
        QTimer.singleShot(0, lambda: self.connect(quiet=True))
        self.watch = QTimer(self)               # reconnect after unplugging or a polling-rate change
        self.watch.setInterval(2000)
        self.watch.timeout.connect(self.check_connection)
        self.watch.start()

    def build_sidebar(self):
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(244)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(14, 22, 14, 18)
        lay.setSpacing(4)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(38, 38))
        brand.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(label("COOL 68", "brand"))
        col.addWidget(label("Open Driver App", "muted"))
        brand.addLayout(col)
        brand.addStretch()
        lay.addLayout(brand)
        lay.addSpacing(24)
        self.navs = []
        for i, (glyph, text) in enumerate(NAV):
            b = NavButton(glyph, text, theme.PAGE_COLORS[text])
            b.clicked.connect(lambda _=False, i=i: self.go(i))
            self.navs.append(b)
            lay.addWidget(b)
        lay.addStretch()
        card = QFrame()
        card.setObjectName("cardInner")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        self.dot = QLabel()
        cl.addWidget(self.dot)
        cl.addWidget(label("VID 372E  ·  PID 1083", "muted"))
        cl.addWidget(button("Reconnect", slot=self.connect))
        lay.addWidget(card)
        lay.addWidget(label(f"v{__version__}", "muted"), 0, Qt.AlignHCenter)
        self.set_status(False)
        return side

    def set_status(self, ok):
        self.online = ok
        color = theme.GOOD if ok else theme.BAD
        self.dot.setText(f"<span style='color:{color}'>●</span>&nbsp; {'Connected' if ok else 'Not connected'}")

    def connect(self, quiet=False):
        try:
            if self.ctx.kb:
                self.ctx.kb.close()
        except Exception:
            pass
        self.ctx.kb = None
        try:
            self.ctx.kb = cool68.Cool68()
        except Exception as e:  # not plugged in, or another program has the config interface open
            self.set_status(False)
            if not quiet:
                self.toast.show_message(f"Keyboard not found: {e}", "error")
            return
        self.set_status(True)
        self.ctx.reload_all()

    def check_connection(self):
        """Every 2 s: notice an unplugged keyboard, and reconnect when it comes back."""
        present = cool68.device_present()
        if present and not self.online:
            self.connect(quiet=True)
            if self.online:
                self.toast.show_message("Keyboard connected", "ok")
        elif not present and self.online:
            try:
                self.ctx.kb.close()
            except Exception:
                pass
            self.ctx.kb = None
            self.set_status(False)
            self.toast.show_message("Keyboard disconnected", "error")

    def go(self, i):
        if self.stack.currentIndex() == i:
            return
        self.pages[self.stack.currentIndex()].on_leave()
        self.stack.setCurrentIndex(i)
        self.root.colors = self.pages[i].page_colors
        self.root.update()
        w = self.stack.currentWidget()
        fx = QGraphicsOpacityEffect(w)
        w.setGraphicsEffect(fx)
        anim = QPropertyAnimation(fx, b"opacity", w)
        anim.setDuration(200)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.finished.connect(lambda: w.setGraphicsEffect(None))
        anim.start()
        self._anim = anim
        if self.ctx.kb:
            self.pages[i].on_show()

    def showEvent(self, e):
        super().showEvent(e)
        if self.ctx.kb:
            self.pages[self.stack.currentIndex()].on_show()
        try:  # dark title bar on Windows 10/11
            hwnd = int(self.winId())
            dwm = ctypes.windll.dwmapi
            for attr, val in ((20, 1), (35, 0x00110D0A), (34, 0x00110D0A)):
                dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(ctypes.c_int(val)), 4)
        except Exception:
            pass

    def closeEvent(self, e):
        if self.ctx.kb:
            self.ctx.kb.close()
        super().closeEvent(e)


LOG = Path(os.environ.get("APPDATA", Path.home())) / "COOL68" / "error.log"


def _install_excepthook():
    """The windowed exe has no console, so write unexpected errors to a log and tell the user."""
    def hook(kind, value, tb):
        try:
            LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} v{__version__}\n")
                f.write("".join(traceback.format_exception(kind, value, tb)))
        except OSError:
            pass
        sys.__excepthook__(kind, value, tb)
        try:
            QMessageBox.critical(None, "COOL 68", f"Something went wrong:\n{value}\n\nDetails were saved to:\n{LOG}")
        except Exception:
            pass
    sys.excepthook = hook


def run():
    _install_excepthook()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    theme.load_fonts()
    app.setFont(theme.ui_font(9))
    app.setStyleSheet(theme.stylesheet())
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
