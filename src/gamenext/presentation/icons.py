"""Small monochrome SVG icons, rendered by Qt at the display's pixel ratio."""
from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer

PATHS = {
    "model": '<path d="m10 2 7 4v8l-7 4-7-4V6zM3 6l7 4 7-4m-7 4v8"/>',
    "reasoning": '<path d="M7 15v-2a6 6 0 1 1 6 0v2M7 15h6m-5 3h4M8 8l2 2 2-2"/>',
    "chat": '<path d="M3 3h14v10H8l-5 4z"/>',
    "studio": '<rect x="3" y="3" width="14" height="14" rx="2"/><path d="m8 6 6 4-6 4z"/>',
    "settings": '<circle cx="10" cy="10" r="3"/><path d="M10 2v3m0 10v3M2 10h3m10 0h3M4 4l2 2m8 8 2 2M4 16l2-2M14 6l2-2"/>',
    "plus": '<path d="M10 3v14M3 10h14"/>',
    "panel": '<rect x="2" y="3" width="16" height="14" rx="2"/><path d="M7 3v14"/>',
    "attach": '<path d="m7 11 6-6a3 3 0 0 1 4 4l-8 8a5 5 0 0 1-7-7l8-8m-5 11 8-8"/>',
    "mic": '<rect x="7" y="2" width="6" height="10" rx="3"/><path d="M4 9a6 6 0 0 0 12 0M10 15v3m-3 0h6"/>',
    "send": '<path d="M10 16V4m-5 5 5-5 5 5"/>',
    "tasks": '<path d="m2 5 2 2 3-4m-5 9 2 2 3-4M10 5h8m-8 8h8"/>',
    "export": '<path d="M10 2v11m-4-4 4 4 4-4M3 13v5h14v-5"/>',
}


def icon(name: str, color: str = "#BDBDBD") -> QIcon:
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"><g fill="none" stroke="{color}" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</g></svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pixmap = QPixmap(40, 40)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)
