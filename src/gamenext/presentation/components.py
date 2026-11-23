"""Shared layout primitives with consistent density and accessible labels."""
from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout
from gamenext.presentation.icons import icon


def label(text: str, kind: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(kind)
    widget.setWordWrap(wrap)
    return widget


def button(text: str, action=None, symbol: str = "", tooltip: str = "") -> QPushButton:
    widget = QPushButton(text)
    widget.setMinimumHeight(30)
    if symbol:
        widget.setIcon(icon(symbol))
        widget.setIconSize(QSize(14, 14))
    widget.setToolTip(tooltip or text)
    widget.setAccessibleName(tooltip or text)
    if action:
        widget.clicked.connect(action)
    return widget


def vertical(widget, margins=(0, 0, 0, 0), spacing=8) -> QVBoxLayout:
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return layout
