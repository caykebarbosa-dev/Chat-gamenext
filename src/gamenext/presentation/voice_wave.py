"""Click Next VoiceBeam live microphone wave overlay rendered at 60 FPS with QPainter."""
from __future__ import annotations

import math
import time
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath
from PyQt6.QtWidgets import QWidget

GREEN_WAVE_LOBES = (
    ((156, 244, 110), 0.50, 0.26, 2.3, 1.55, 0.0, 1.00),
    ((57, 201, 77), 0.38, 0.32, 1.8, -1.15, 1.3, 0.88),
    ((74, 222, 128), 0.62, 0.32, 2.0, 1.25, 2.5, 0.86),
    ((16, 185, 129), 0.26, 0.28, 2.7, 1.80, 3.7, 0.64),
    ((34, 197, 94), 0.74, 0.28, 2.5, -1.65, 4.9, 0.64),
)


class VoiceWaveOverlay(QWidget):
    """Smooth multi-lobe audio-reactive VoiceBeam overlay for the chat composer."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._active = False
        self._closing = False
        self._envelope = 0.14
        self._opacity = 0.0
        self._bands = [0.0, 0.0, 0.0, 0.0, 0.0]
        self._start_ts = time.perf_counter()
        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60 FPS
        self._timer.timeout.connect(self._tick)
        self.hide()

    def start(self):
        self._active = True
        self._closing = False
        self._opacity = max(self._opacity, 0.15)
        self._start_ts = time.perf_counter()
        self.show()
        self.lower()
        if not self._timer.isActive():
            self._timer.start()

    def stop(self):
        if not self._active and not self._timer.isActive():
            return
        self._closing = True
        self._active = False

    def set_levels(self, bands: list[float]):
        if len(bands) >= 5:
            self._bands = [max(0.0, min(1.0, float(v))) for v in bands[:5]]

    def _tick(self):
        t = time.perf_counter() - self._start_ts
        raw = sum(self._bands) / 5.0 * 1.45 if self._active else 0.0
        if self._active and raw < 0.04:
            # Gentle green breathing wave while waiting for speech.
            raw = 0.08 + 0.05 * (0.5 + 0.5 * math.sin(t * 2.2))
        target = 0.0 if self._closing else min(1.0, raw * 1.25)
        rate = 0.34 if target > self._envelope else 0.14
        self._envelope += (target - self._envelope) * rate

        if self._closing:
            self._opacity = max(0.0, self._opacity - 0.10)
            if self._opacity <= 0.01:
                self._timer.stop()
                self._opacity = 0.0
                self.hide()
                return
        else:
            self._opacity = min(1.0, self._opacity + 0.12)
        self.update()

    def paintEvent(self, event):
        if self._opacity <= 0.01:
            return
        w = float(self.width())
        h = float(self.height())
        if w < 20 or h < 20:
            return
        t = time.perf_counter() - self._start_ts
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Clip cleanly to composer's 16px rounded corners.
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(1.0, 1.0, w - 2.0, h - 2.0), 15.0, 15.0)
        painter.setClipPath(clip)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

        steps = max(44, min(96, int(w / 9)))
        base_h = h * (0.28 + self._envelope * 0.44)

        for idx, (rgb, center, width, freq, speed, phase, amp) in enumerate(GREEN_WAVE_LOBES):
            band = self._bands[idx] if idx < len(self._bands) else self._envelope
            band_boost = 0.65 + max(band, self._envelope) * 0.9
            peak_h = min(h * 0.84, base_h * amp * band_boost)

            path = QPainterPath()
            path.moveTo(0.0, h)
            for s in range(steps + 1):
                u = s / steps
                x = u * w
                dist = (u - center) / width
                gauss = math.exp(-0.5 * dist * dist)
                ripple = 0.72 + 0.28 * math.sin(u * math.pi * freq * 2.0 + t * speed * 3.1 + phase)
                y = h - peak_h * gauss * max(0.2, ripple)
                path.lineTo(x, y)
            path.lineTo(w, h)
            path.closeSubpath()

            grad = QLinearGradient(0.0, h - peak_h, 0.0, h)
            r, g, b = rgb
            grad.setColorAt(0.0, QColor(r, g, b, 0))
            grad.setColorAt(0.55, QColor(r, g, b, int(56 * self._opacity)))
            grad.setColorAt(1.0, QColor(r, g, b, int(112 * self._opacity)))
            painter.fillPath(path, grad)

        # Signature glowing horizontal VoiceBeam along the bottom edge.
        beam_h = max(2.5, h * 0.032)
        beam_grad = QLinearGradient(0.0, 0.0, w, 0.0)
        beam_grad.setColorAt(0.05, QColor(57, 201, 77, 0))
        beam_grad.setColorAt(0.35, QColor(57, 201, 77, int(140 * self._opacity)))
        beam_grad.setColorAt(0.50, QColor(156, 244, 110, int(224 * self._opacity)))
        beam_grad.setColorAt(0.65, QColor(57, 201, 77, int(140 * self._opacity)))
        beam_grad.setColorAt(0.95, QColor(57, 201, 77, 0))
        painter.fillRect(QRectF(0.0, h - beam_h, w, beam_h), beam_grad)
        painter.end()
