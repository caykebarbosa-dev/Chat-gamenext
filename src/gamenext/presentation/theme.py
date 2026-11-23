"""Original seven-color monochrome palette (#0B0B0B, #141414, #1C1C1C, #252525, #858585, #BDBDBD, #F2F2F2)."""
from pathlib import Path

_CHECK_ICON = (Path(__file__).resolve().parent / "check.svg").as_posix()
_CHEVRON_DOWN = (Path(__file__).resolve().parent / "chevron_down.svg").as_posix()
_CHEVRON_UP = (Path(__file__).resolve().parent / "chevron_up.svg").as_posix()

STYLE = f"""
* {{
    font-family: 'Segoe UI';
    font-size: 13px;
    font-weight: 400;
    color: #F2F2F2;
    border: none;
}}

QMainWindow, QWidget {{
    background: #0B0B0B;
}}

QWidget#sidebar, QWidget#tasks {{
    background: #141414;
    border-right: 1px solid #252525;
}}

QWidget#tasks {{
    border-right: none;
    border-left: 1px solid #252525;
}}

QWidget#sidebar QLabel, QWidget#tasks QLabel {{
    background: transparent;
}}

QWidget#composer {{
    background: #1C1C1C;
    border: 1px solid #252525;
    border-radius: 16px;
}}

QWidget#composer QTextEdit {{
    background: transparent;
}}

QWidget#settingsCard {{
    background: #141414;
    border: 1px solid #252525;
    border-radius: 10px;
}}

QWidget#infoBanner {{
    background: #1C1C1C;
    border: 1px solid #252525;
    border-radius: 8px;
}}

QWidget#settingsFooter {{
    background: #141414;
    border: 1px solid #252525;
    border-radius: 10px;
}}

QWidget#settingsCard QLabel,
QWidget#infoBanner QLabel,
QWidget#settingsFooter QLabel,
QWidget#controlChip QLabel,
QWidget#messageMetrics QLabel {{
    background: transparent;
}}

QWidget#controlChip {{
    background: #252525;
    border-radius: 7px;
}}

QWidget#controlChip QComboBox {{
    background: transparent;
    border: none;
    padding: 5px 4px;
}}

QWidget#messageMetrics {{
    background: #141414;
    border-radius: 8px;
}}

QPushButton {{
    padding: 6px 10px;
    border-radius: 6px;
    text-align: left;
    background: transparent;
    color: #F2F2F2;
}}

QPushButton:hover, QPushButton:focus, QPushButton:checked {{
    background: #252525;
}}

QPushButton:disabled {{
    color: #858585;
}}

QWidget#settingsPage QPushButton,
QDialog QPushButton {{
    background: #1C1C1C;
    border: 1px solid #252525;
    border-radius: 7px;
    padding: 7px 14px;
    color: #F2F2F2;
    text-align: center;
}}

QWidget#settingsPage QPushButton:hover,
QWidget#settingsPage QPushButton:focus,
QWidget#settingsPage QPushButton:checked,
QDialog QPushButton:hover,
QDialog QPushButton:focus,
QDialog QPushButton:checked {{
    background: #252525;
    border: 1px solid #858585;
}}

QWidget#settingsPage QPushButton:disabled,
QDialog QPushButton:disabled {{
    background: #141414;
    border: 1px solid #252525;
    color: #858585;
}}

QPushButton#primaryControl,
QWidget#settingsPage QPushButton#primaryControl,
QDialog QPushButton#primaryControl {{
    background: #BDBDBD;
    color: #0B0B0B;
    border: 1px solid #BDBDBD;
    border-radius: 7px;
    padding: 7px 16px;
    text-align: center;
}}

QPushButton#primaryControl:hover,
QWidget#settingsPage QPushButton#primaryControl:hover,
QDialog QPushButton#primaryControl:hover {{
    background: #F2F2F2;
    border: 1px solid #F2F2F2;
    color: #0B0B0B;
}}

QPushButton#primaryControl:disabled,
QWidget#settingsPage QPushButton#primaryControl:disabled {{
    background: #252525;
    border: 1px solid #252525;
    color: #858585;
}}

QPushButton#dangerControl,
QWidget#settingsPage QPushButton#dangerControl {{
    background: #1C1C1C;
    border: 1px solid #858585;
    color: #F2F2F2;
    border-radius: 7px;
    padding: 7px 14px;
    text-align: center;
}}

QPushButton#dangerControl:hover,
QWidget#settingsPage QPushButton#dangerControl:hover {{
    background: #252525;
    border: 1px solid #BDBDBD;
}}

QPushButton#presetControl,
QWidget#settingsPage QPushButton#presetControl {{
    background: #1C1C1C;
    border: 1px solid #252525;
    color: #F2F2F2;
    border-radius: 7px;
    padding: 8px 13px;
    text-align: center;
}}

QPushButton#presetControl:hover,
QWidget#settingsPage QPushButton#presetControl:hover {{
    background: #252525;
    border: 1px solid #858585;
}}

QPushButton#attachmentControl, QPushButton#microphoneControl, QPushButton#kiloCatalogControl {{
    background: #252525;
    border-radius: 7px;
    text-align: center;
    color: #BDBDBD;
    font-size: 12px;
    padding: 4px 10px;
}}

QPushButton#attachmentControl:hover, QPushButton#kiloCatalogControl:hover {{
    background: #252525;
    border: 1px solid #858585;
    color: #F2F2F2;
}}

QPushButton#microphoneControl[recording="true"] {{
    background: rgba(57, 201, 77, 0.22);
    border: 1px solid rgba(57, 201, 77, 0.75);
}}

QPushButton#send {{
    background: #BDBDBD;
    color: #0B0B0B;
    border-radius: 8px;
    text-align: center;
}}

QPushButton#send:hover {{
    background: #F2F2F2;
}}

QCheckBox {{
    background: transparent;
    spacing: 10px;
    color: #F2F2F2;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    background: #1C1C1C;
    border: 1px solid #858585;
    border-radius: 4px;
}}

QCheckBox::indicator:hover {{
    border: 1px solid #BDBDBD;
}}

QCheckBox::indicator:checked {{
    background: #BDBDBD;
    border: 1px solid #BDBDBD;
    image: url("{_CHECK_ICON}");
}}

QLabel#muted {{
    color: #858585;
    font-size: 12px;
}}

QLabel#silver {{
    color: #BDBDBD;
    font-size: 12px;
}}

QLabel#fieldLabel {{
    color: #F2F2F2;
    font-size: 12px;
}}

QLabel#sectionTitle {{
    color: #F2F2F2;
    font-size: 15px;
}}

QLabel#statusBadge {{
    background: #1C1C1C;
    border: 1px solid #252525;
    border-radius: 7px;
    padding: 8px 11px;
    color: #BDBDBD;
    font-size: 12px;
}}

QLabel#headline {{
    font-size: 28px;
    color: #F2F2F2;
}}

QLabel#brand {{
    font-size: 17px;
    color: #F2F2F2;
}}

QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
    background: #1C1C1C;
    border: 1px solid #252525;
    padding: 7px 10px;
    border-radius: 7px;
    color: #F2F2F2;
    selection-background-color: #252525;
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{
    background: #252525;
    border: 1px solid #858585;
}}

QLineEdit:read-only {{
    color: #BDBDBD;
    background: #1C1C1C;
}}

QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background: #252525;
    border-left: 1px solid #141414;
    width: 22px;
}}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url("{_CHEVRON_UP}");
    width: 10px;
    height: 10px;
}}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url("{_CHEVRON_DOWN}");
    width: 10px;
    height: 10px;
}}

QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background: #858585;
}}

QTextEdit {{
    background: transparent;
    padding: 4px;
    selection-background-color: #252525;
}}

QComboBox {{
    background: #1C1C1C;
    border: 1px solid #252525;
    padding: 7px 10px;
    border-radius: 7px;
    font-size: 13px;
    color: #F2F2F2;
}}

QComboBox:focus, QComboBox:hover {{
    background: #252525;
    border: 1px solid #858585;
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 26px;
    border-left: 1px solid #252525;
}}

QComboBox::down-arrow {{
    image: url("{_CHEVRON_DOWN}");
    width: 12px;
    height: 12px;
}}

QWidget#controlChip QComboBox {{
    color: #BDBDBD;
    font-size: 12px;
}}

QWidget#controlChip QComboBox::drop-down {{
    border-left: none;
    width: 20px;
}}

QComboBox QAbstractItemView {{
    background: #1C1C1C;
    border: 1px solid #252525;
    color: #F2F2F2;
    selection-background-color: #252525;
    padding: 4px;
}}

QListWidget {{
    background: transparent;
    outline: none;
}}

QListWidget::item {{
    padding: 9px 8px;
    border-radius: 6px;
    color: #BDBDBD;
}}

QListWidget::item:selected, QListWidget::item:hover {{
    background: #252525;
}}

QTreeWidget {{
    background: #1C1C1C;
    border: 1px solid #252525;
    border-radius: 8px;
    outline: none;
    color: #F2F2F2;
    font-size: 12px;
}}

QTreeWidget::item {{
    padding: 7px 6px;
    border-bottom: 1px solid #141414;
    color: #F2F2F2;
}}

QTreeWidget::item:hover, QTreeWidget::item:selected {{
    background: #252525;
    color: #F2F2F2;
}}

QTreeWidget::indicator {{
    width: 15px;
    height: 15px;
    background: #141414;
    border: 1px solid #858585;
    border-radius: 3px;
}}

QTreeWidget::indicator:checked {{
    background: #BDBDBD;
    border: 1px solid #BDBDBD;
    image: url("{_CHECK_ICON}");
}}

QHeaderView::section {{
    background: #141414;
    color: #BDBDBD;
    border: none;
    border-bottom: 1px solid #252525;
    padding: 7px 8px;
    font-size: 12px;
}}

QScrollArea {{
    background: transparent;
}}

QScrollBar:vertical {{
    width: 6px;
    background: transparent;
}}

QScrollBar::handle:vertical {{
    background: #252525;
    min-height: 25px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical:hover {{
    background: #858585;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

QTabWidget::pane {{
    border: none;
    margin-top: 8px;
}}

QTabBar::tab {{
    background: #141414;
    color: #858585;
    border: 1px solid #252525;
    padding: 8px 15px;
    margin-right: 6px;
    border-radius: 6px;
}}

QTabBar::tab:hover {{
    color: #BDBDBD;
    background: #1C1C1C;
}}

QTabBar::tab:selected {{
    color: #F2F2F2;
    background: #252525;
    border: 1px solid #858585;
}}

QProgressBar {{
    background: #1C1C1C;
    border-radius: 2px;
    max-height: 4px;
}}

QProgressBar::chunk {{
    background: #BDBDBD;
    border-radius: 2px;
}}

QToolTip, QMenu, QDialog {{
    background: #1C1C1C;
    border: 1px solid #252525;
    color: #F2F2F2;
}}

QMenu::item {{
    padding: 8px 15px;
}}

QMenu::item:selected {{
    background: #252525;
}}
"""
