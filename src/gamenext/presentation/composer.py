"""Message composer, unified model selector, live VoiceBeam overlay and keyboard submission."""
from pathlib import Path
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QTextEdit, QHBoxLayout, QComboBox, QFileDialog
from gamenext.presentation.components import button, vertical
from gamenext.presentation.icons import icon
from gamenext.presentation.containers import control_chip
from gamenext.presentation.voice_wave import VoiceWaveOverlay


class MessageInput(QTextEdit):
    submit = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.submit.emit()
            return
        super().keyPressEvent(event)


class Composer(QWidget):
    submit = pyqtSignal()
    preference_changed = pyqtSignal()
    microphone_clicked = pyqtSignal()
    kilo_catalog_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("composer")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.attachments: list[str] = []

        # Live VoiceBeam overlay behind composer controls (Click Next audio-reactive effect).
        self.voice_wave = VoiceWaveOverlay(self)

        layout = vertical(self, (14, 12, 14, 10), 6)
        self.files = button("", self.clear_attachments, tooltip="Remover anexos")
        self.files.hide()
        layout.addWidget(self.files)
        self.input = MessageInput()
        self.input.setPlaceholderText("Envie uma mensagem…")
        self.input.setAccessibleName("Mensagem. Enter envia; Shift+Enter quebra linha")
        self.input.setFixedHeight(66)
        self.input.submit.connect(self.submit)
        layout.addWidget(self.input)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.model = QComboBox()
        self.model.addItems(["Qwen · demo", "Llama · demo", "Gemma · demo"])
        self.model.setToolTip("Escolha um modelo Local (GGUF) ou Kilo Gateway")
        self.model.setAccessibleName("Modelo")
        self.model.setMinimumWidth(210)
        self.model.setMaximumWidth(340)

        self.reasoning = QComboBox()
        self.reasoning.addItems(["Curto", "Médio", "Alto", "Livre"])
        self.reasoning.setCurrentIndex(3)
        self.reasoning.setToolTip("Local: Curto (1024) / Médio (2048) / Alto (4096) / Livre · Kilo: esforço de raciocínio")
        self.reasoning.setAccessibleName("Raciocínio / tamanho da resposta")

        self.mode = QComboBox()
        self.mode.addItems(["Chat", "Tarefas"])
        self.mode.setAccessibleName("Modo de trabalho")
        for combo in (self.model, self.reasoning, self.mode):
            combo.currentIndexChanged.connect(self.preference_changed)

        row.addWidget(control_chip(self.model, "model"))
        self.kilo_button = button("Kilo", self.kilo_catalog_clicked.emit, "settings", "Abrir catálogo e detalhes dos modelos Kilo Gateway")
        self.kilo_button.setObjectName("kiloCatalogControl")
        self.kilo_button.setFixedHeight(32)
        row.addWidget(self.kilo_button)
        row.addWidget(control_chip(self.reasoning, "reasoning"))
        self.mode.hide()
        row.addStretch()

        self.attachment_button = button("", self.attach, "attach", "Anexar arquivos, documentos ou imagens")
        self.attachment_button.setObjectName("attachmentControl")
        self.attachment_button.setFixedSize(34, 32)
        row.addWidget(self.attachment_button)

        self.microphone = button("", self.microphone_clicked.emit, "mic", "Ligar/desligar ditado por voz (Whisper local ou Groq API)")
        self.microphone.setFixedSize(34, 32)
        self.microphone.setObjectName("microphoneControl")
        self.microphone.setCheckable(True)
        row.addWidget(self.microphone)

        self.send = button("", self.submit.emit, "send", "Enviar mensagem")
        self.send.setObjectName("send")
        self.send.setIcon(icon("send", "#0B0B0B"))
        self.send.setFixedSize(32, 30)
        row.addWidget(self.send)
        layout.addLayout(row)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.voice_wave.setGeometry(self.rect())
        self.voice_wave.lower()

    def set_voice_recording(self, active: bool):
        self.microphone.setChecked(active)
        self.microphone.setProperty("recording", active)
        self.microphone.style().unpolish(self.microphone)
        self.microphone.style().polish(self.microphone)
        if active:
            self.voice_wave.setGeometry(self.rect())
            self.voice_wave.start()
        else:
            self.voice_wave.stop()

    def set_voice_levels(self, bands: list[float]):
        self.voice_wave.set_levels(bands)

    def attach(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Anexar arquivos")
        self.attachments = list(dict.fromkeys(self.attachments + files))
        self.files.setText("  ·  ".join(Path(p).name for p in self.attachments) + "   ×")
        self.files.setVisible(bool(self.attachments))

    def clear_attachments(self):
        self.attachments.clear()
        self.files.hide()

    def busy(self, active: bool):
        self.send.setText("■" if active else "")
        self.send.setIcon(QIcon() if active else icon("send", "#0B0B0B"))
        self.send.setToolTip("Parar resposta" if active else "Enviar mensagem")
        self.send.setAccessibleName(self.send.toolTip())
