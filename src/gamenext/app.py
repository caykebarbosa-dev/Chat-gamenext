"""Desktop entry point."""
import sys
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication
from gamenext.bootstrap import build_window
from gamenext.presentation.theme import STYLE


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("GameNext")
    app.setOrganizationName("GameNext")
    app.setFont(QFont("Segoe UI", 10, QFont.Weight.Normal))
    app.setStyleSheet(STYLE)
    window = build_window()
    window.show()
    if "--settings" in sys.argv:
        window.navigate(2)
        window.settings.tabs.setCurrentIndex(1)
    sys.exit(app.exec())
