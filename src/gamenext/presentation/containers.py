"""Reusable elevated surfaces, field blocks and compact control chips."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFormLayout
from gamenext.presentation.components import label


def container(name="settingsCard"):
    widget = QWidget()
    widget.setObjectName(name)
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    return widget


def field_block(title: str, widget: QWidget, hint: str = "") -> QWidget:
    """Labeled field block for crisp 2-column settings grids."""
    wrapper = QWidget()
    wrapper.setStyleSheet("background: transparent;")
    box = QVBoxLayout(wrapper)
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(5)
    box.addWidget(label(title, "fieldLabel"))
    box.addWidget(widget)
    if hint:
        box.addWidget(label(hint, "muted", True))
    return wrapper


class SettingsRows(QVBoxLayout):
    def addRow(self, title, field=None):
        card = container()
        form = QFormLayout(card)
        form.setContentsMargins(18, 14, 18, 14)
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        if field is None:
            form.addRow(title)
        else:
            caption = label(title, "fieldLabel")
            caption.setMinimumWidth(160)
            form.addRow(caption, field)
        self.addWidget(card)


def control_chip(widget, symbol):
    from gamenext.presentation.icons import icon
    surface = container("controlChip")
    row = QHBoxLayout(surface)
    row.setContentsMargins(9, 2, 4, 2)
    row.setSpacing(4)
    image = label("")
    image.setPixmap(icon(symbol).pixmap(14, 14))
    image.setFixedSize(14, 14)
    row.addWidget(image)
    row.addWidget(widget)
    return surface
