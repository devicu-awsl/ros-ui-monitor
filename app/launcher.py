"""Qt launcher window shown when the server starts.

Lets the operator pick which installed browser to open the dashboard in, and
copy either the local or the LAN URL — the LAN one is what you send to a
tablet or phone in Phase B.

PySide6 is an optional extra (``pip install ".[gui]"``). The application runs
without it; only ``--chooser`` needs it.
"""

from __future__ import annotations

import math
import sys

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .browsers import Browser, find_browsers
from .qr import qr_available, qr_png

# Matches the dashboard palette so the launcher does not look like a
# different application.
STYLE = """
QWidget#root { background: #0e1116; }
QLabel { color: #e6eaef; }
QLabel#title { font-size: 16px; font-weight: 600; }
QLabel#status { color: #6ec28a; font-size: 12px; }
QLabel#caption { color: #97a3b2; font-size: 11px; }
QLabel#hint { color: #97a3b2; font-size: 11px; }
QFrame#card { background: #151a21; border: 1px solid #262e39; border-radius: 8px; }
QFrame#qrcard { background: #ffffff; border: 1px solid #262e39; border-radius: 8px; }
QLabel#qrcaption { color: #4a5560; font-size: 10px; }
QLineEdit {
    background: #0e1116; border: 1px solid #262e39; border-radius: 6px;
    color: #e6eaef; padding: 6px 8px; font-size: 12px;
}
QListWidget {
    background: #0e1116; border: 1px solid #262e39; border-radius: 6px;
    color: #e6eaef; font-size: 13px; outline: none;
}
QListWidget::item { padding: 7px 8px; border-radius: 4px; }
QListWidget::item:selected { background: #1e3a4c; color: #ffffff; }
QPushButton {
    background: #1b222b; border: 1px solid #262e39; border-radius: 6px;
    color: #e6eaef; padding: 7px 14px; font-size: 12px;
}
QPushButton:hover { border-color: #6ea8c7; }
QPushButton#primary { background: #6ea8c7; border: none; color: #0b1116; font-weight: 600; }
QPushButton#primary:hover { background: #86bcd8; }
QPushButton:disabled { color: #97a3b2; background: #151a21; }
"""


def _browser_icon(browser: Browser) -> QIcon:
    """Best-effort icon; falls back to an empty icon when none is available."""
    if browser.icon_path:
        pixmap = QPixmap(browser.icon_path)
        if not pixmap.isNull():
            return QIcon(pixmap)
    return QIcon()


class UrlRow(QWidget):
    """A read-only URL with a Copy button that confirms in place, and
    optionally a QR button for URLs meant to be opened on another device."""

    qr_toggled = Signal()

    def __init__(self, caption: str, url: str, with_qr: bool = False) -> None:
        super().__init__()
        self.url = url
        self.qr_button: QPushButton | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        label = QLabel(caption)
        label.setObjectName("caption")
        layout.addWidget(label)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.field = QLineEdit(url)
        self.field.setReadOnly(True)
        self.field.setCursorPosition(0)
        row.addWidget(self.field, 1)

        self.copy_button = QPushButton("Copy URL")
        self.copy_button.setFixedWidth(96)
        self.copy_button.clicked.connect(self._copy)
        row.addWidget(self.copy_button)

        # Only offered when a QR encoder is present, so a missing optional
        # dependency hides the button rather than showing a broken one.
        if with_qr and qr_available():
            self.qr_button = QPushButton("QR Code")
            self.qr_button.setFixedWidth(96)
            self.qr_button.setCheckable(True)
            self.qr_button.clicked.connect(self.qr_toggled.emit)
            row.addWidget(self.qr_button)

        layout.addLayout(row)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.url)
        self.field.selectAll()
        self.copy_button.setText("Copied")
        QTimer.singleShot(1200, lambda: self.copy_button.setText("Copy URL"))


class QrPanel(QFrame):
    """The QR code, shown at the bottom of the window on request.

    Sized to roughly a quarter of the window, and always drawn dark-on-light
    inside its own light panel so phone cameras read it reliably.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("qrcard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(6)

        self.image = QLabel()
        self.image.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.image)

        self.caption = QLabel()
        self.caption.setObjectName("qrcaption")
        self.caption.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.caption)

    def show_url(self, url: str, side_px: int) -> None:
        pixmap = QPixmap()
        pixmap.loadFromData(qr_png(url, side_px), "PNG")
        self.image.setPixmap(pixmap)
        self.caption.setText(f"Scan with a phone camera to open\n{url}")


class LauncherWindow(QWidget):
    def __init__(self, local_url: str, lan_url: str | None = None,
                 auth_enabled: bool = False) -> None:
        super().__init__()
        self.local_url = local_url
        self.browsers = find_browsers()

        self.setObjectName("root")
        self.setWindowTitle("RB5009 Monitor")
        self.setStyleSheet(STYLE)
        self.setMinimumWidth(430)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        title = QLabel("RB5009 Monitor")
        title.setObjectName("title")
        outer.addWidget(title)

        status = QLabel("● Server running" + ("  ·  login required" if auth_enabled else ""))
        status.setObjectName("status")
        outer.addWidget(status)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(10)

        self.local_row = UrlRow("This computer", local_url)
        card_layout.addWidget(self.local_row)
        self.lan_row: UrlRow | None = None
        if lan_url:
            self.lan_row = UrlRow("On the LAN — open this on a tablet or phone", lan_url,
                                  with_qr=True)
            self.lan_row.qr_toggled.connect(self._toggle_qr)
            card_layout.addWidget(self.lan_row)
        outer.addWidget(card)

        pick = QLabel("Open in")
        pick.setObjectName("caption")
        outer.addWidget(pick)

        self.list = QListWidget()
        for browser in self.browsers:
            item = QListWidgetItem(_browser_icon(browser), browser.name)
            if browser.is_default:
                item.setText(f"{browser.name}  (default)")
                font = QFont()
                font.setBold(True)
                item.setFont(font)
            item.setData(Qt.UserRole, browser)
            self.list.addItem(item)
        if self.browsers:
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _: self._open())
        # Keep the list a sensible height without a fixed pixel guess, and give
        # it a floor so showing the QR panel cannot squeeze it to a scroll box.
        rows = max(3, min(len(self.browsers), 5))
        self.list.setMinimumHeight(rows * 34 + 8)
        self.list.setMaximumHeight(rows * 34 + 8)
        outer.addWidget(self.list)

        if not self.browsers:
            empty = QLabel("No browsers detected. Copy the URL above and paste it into one.")
            empty.setObjectName("hint")
            empty.setWordWrap(True)
            outer.addWidget(empty)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        hint = QLabel("Closing this window leaves the server running.")
        hint.setObjectName("hint")
        buttons.addWidget(hint, 1)

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        buttons.addWidget(self.close_button)

        self.open_button = QPushButton("Open")
        self.open_button.setObjectName("primary")
        self.open_button.setDefault(True)
        self.open_button.setEnabled(bool(self.browsers))
        self.open_button.clicked.connect(self._open)
        buttons.addWidget(self.open_button)
        outer.addLayout(buttons)

        # Sits at the bottom, below the buttons, hidden until asked for.
        self.qr_panel = QrPanel()
        self.qr_panel.hide()
        outer.addWidget(self.qr_panel)

    # Padding and caption around the code inside the QR panel.
    _QR_CHROME = 60

    def _qr_side(self) -> int:
        """Side length giving the code roughly a quarter of the window area.

        Showing the code also makes the window taller, so a plain fraction of
        the width undershoots. Solving for the final size instead:

            s^2 = 0.25 * W * (H + chrome + s)

        where H is the current height with the panel hidden.
        """
        width = max(self.width(), self.minimumWidth())
        height = self.height()
        c = 0.25 * width
        side = (c + math.sqrt(c * c + 4 * c * (height + self._QR_CHROME))) / 2
        # Never let it dominate the window or vanish on a small one.
        return int(max(140, min(side, width * 0.8)))

    def _toggle_qr(self) -> None:
        if self.lan_row is None or self.lan_row.qr_button is None:
            return
        if self.lan_row.qr_button.isChecked():
            self.qr_panel.show_url(self.lan_row.url, self._qr_side())
            self.qr_panel.show()
            self.lan_row.qr_button.setText("Hide QR")
        else:
            self.qr_panel.hide()
            self.lan_row.qr_button.setText("QR Code")
        # Grow and shrink in height only: adjustSize() alone would also pull
        # the window narrower, truncating the URL fields.
        keep_width = self.width()
        self.adjustSize()
        self.resize(keep_width, self.height())

    def _open(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        browser: Browser = item.data(Qt.UserRole)
        try:
            browser.launch(self.local_url)
        except OSError as exc:
            self.open_button.setText("Failed")
            print(f"Could not start {browser.name}: {exc}", file=sys.stderr)
            QTimer.singleShot(1500, lambda: self.open_button.setText("Open"))


def run_launcher(local_url: str, lan_url: str | None = None,
                 auth_enabled: bool = False) -> int:
    """Show the launcher. Blocks until the window is closed."""
    qt_app = QApplication.instance() or QApplication(sys.argv[:1])
    window = LauncherWindow(local_url, lan_url, auth_enabled)
    window.show()
    return qt_app.exec()
