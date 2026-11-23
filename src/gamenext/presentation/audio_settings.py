"""Windows microphone selection and local transcription settings."""
import subprocess
from PyQt6.QtWidgets import QWidget, QComboBox, QDialog, QHBoxLayout
from gamenext.presentation.components import label, button, vertical
from gamenext.presentation.containers import container, field_block


def microphone_combo(audio):
    combo = QComboBox()
    combo.setAccessibleName("Dispositivo de entrada do Windows")
    selected = bytes(audio.selected_input().id()).hex()
    for device in audio.inputs():
        identifier = bytes(device.id()).hex()
        combo.addItem(device.description(), identifier)
        if identifier == selected:
            combo.setCurrentIndex(combo.count() - 1)
    return combo


class MicrophoneDialog(QDialog):
    def __init__(self, audio, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Microfone · GameNext")
        self.setMinimumWidth(440)
        layout = vertical(self, (20, 20, 20, 20), 14)
        layout.addWidget(label("Escolha o microfone do Windows", "sectionTitle"))
        card = container()
        inside = vertical(card, (16, 16, 16, 16), 12)
        self.devices = microphone_combo(audio)
        inside.addWidget(field_block("Dispositivo de entrada", self.devices))
        inside.addWidget(label(
            "Whisper Tiny · português · CPU INT8.\n"
            "Fale normalmente; o texto aparece a cada breve pausa até você desligar o microfone.",
            "silver",
            True,
        ))
        layout.addWidget(card)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(button("Cancelar", self.reject))
        record = button("Ligar ditado", self.accept, "mic")
        record.setObjectName("primaryControl")
        record.setEnabled(bool(audio.inputs()))
        actions.addWidget(record)
        layout.addLayout(actions)


class AudioSettings(QWidget):
    def __init__(self, audio):
        super().__init__()
        self.audio = audio
        layout = vertical(self, spacing=14)

        card = container()
        content = vertical(card, (18, 16, 18, 16), 12)
        content.addWidget(label("Entrada de áudio", "sectionTitle"))
        content.addWidget(label("Selecione o microfone usado pelo ditado local contínuo.", "silver", True))
        self.devices = microphone_combo(audio)
        self.devices.currentIndexChanged.connect(self.save_device)
        content.addWidget(field_block("Microfone do Windows", self.devices))
        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(button("Atualizar dispositivos", self.refresh))
        actions.addWidget(button("Configurações de som do Windows", self.windows_sound, "settings"))
        actions.addStretch()
        content.addLayout(actions)
        layout.addWidget(card)

        card = container()
        content = vertical(card, (18, 16, 18, 16), 10)
        content.addWidget(label("Transcrição local (Whisper)", "sectionTitle"))
        content.addWidget(label(
            "Whisper Tiny multilíngue · INT8 · 2 threads CPU · ditado contínuo em português com pausas de 450 ms.",
            "silver",
            True,
        ))
        self.status = label(
            "Modelo local pronto" if (audio.model_dir / "model.bin").is_file() else "Modelo Whisper não encontrado",
            "statusBadge",
            True,
        )
        content.addWidget(self.status)
        content.addWidget(label(
            "As gravações temporárias são excluídas automaticamente após a transcrição. Nada é enviado à nuvem.",
            "muted",
            True,
        ))
        audio.state.connect(self.status.setText)
        audio.error.connect(self.status.setText)
        layout.addWidget(card)

    def save_device(self):
        if self.devices.currentData():
            self.audio.repository.set_preference("microphone_id", self.devices.currentData())

    def refresh(self):
        fresh = microphone_combo(self.audio)
        self.devices.blockSignals(True)
        self.devices.clear()
        for index in range(fresh.count()):
            self.devices.addItem(fresh.itemText(index), fresh.itemData(index))
        self.devices.setCurrentIndex(fresh.currentIndex())
        self.devices.blockSignals(False)
        fresh.deleteLater()

    def windows_sound(self):
        subprocess.Popen(["explorer.exe", "ms-settings:sound"])
