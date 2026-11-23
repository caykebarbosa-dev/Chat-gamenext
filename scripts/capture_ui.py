"""Capture actual Qt widgets on Windows, including API tab, Model Details Popup and VoiceBeam."""
import sys
import tempfile
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gamenext.bootstrap import build_window
from gamenext.infrastructure.kilo_api import extract_models, save_kilo_catalog
from gamenext.presentation.kilo_model_dialog import KiloModelDetailDialog
from gamenext.presentation.theme import STYLE

app = QApplication([])
app.setStyleSheet(STYLE)
data = Path(tempfile.mkdtemp(prefix="gamenext-visual-"))
window = build_window(data)

# Seed sample Kilo models for visual inspection of API tab, popup and unified chat selector.
sample_models = extract_models({
    "data": [
        {
            "id": "google/gemini-2.5-flash:free",
            "name": "Gemini 2.5 Flash (Free)",
            "description": "Modelo rápido multimodal com amplo contexto e suporte a ferramentas.",
            "context_length": 1000000,
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"input_modalities": ["text", "image", "pdf"], "output_modalities": ["text"]},
            "supported_parameters": ["tools", "reasoning", "temperature"],
        },
        {
            "id": "anthropic/claude-sonnet-4",
            "name": "Claude Sonnet 4",
            "description": "Alta precisão em programação, arquitetura de software e uso autônomo de ferramentas.",
            "context_length": 200000,
            "pricing": {"prompt": "0.000003", "completion": "0.000015", "input_cache_read": "0.0000003"},
            "architecture": {"input_modalities": ["text", "image", "pdf"], "output_modalities": ["text"]},
            "supported_parameters": ["tools", "reasoning", "temperature", "max_tokens"],
        },
        {
            "id": "openai/o3-pro",
            "name": "OpenAI o3 Pro",
            "description": "Raciocínio profundo de classe Ultra para problemas complexos.",
            "context_length": 200000,
            "pricing": {"prompt": "0.00002", "completion": "0.00008"},
            "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]},
            "supported_parameters": ["tools", "reasoning"],
        },
    ]
})
save_kilo_catalog(window.repository, sample_models, 5.78, [sample_models[0].id, sample_models[1].id])
if window.settings.api_settings:
    window.settings.api_settings.sync_from_repository()
window.refresh_chat_models()

window.show()
window.resize(1440, 900)
QTest.qWait(2500)
out = ROOT / "output"
out.mkdir(exist_ok=True)
print("Catalog:", [entry["name"] for entry in window.settings.model_panel.catalog], flush=True)
window.grab().save(str(out / "gamenext-home.png"))

# Capture VoiceBeam active wave effect inside the composer.
window.composer.set_voice_recording(True)
window.composer.set_voice_levels([0.75, 0.92, 0.88, 0.65, 0.72])
QTest.qWait(200)
window.grab().save(str(out / "gamenext-voice-wave.png"))
window.composer.set_voice_recording(False)
QTest.qWait(100)

window.navigate(2)
window.settings.tabs.setCurrentIndex(1)
QTest.qWait(150)
window.grab().save(str(out / "gamenext-models.png"))
window.settings.tabs.setCurrentIndex(2)
QTest.qWait(150)
window.grab().save(str(out / "gamenext-performance.png"))
window.settings.tabs.setCurrentIndex(3)
QTest.qWait(150)
window.grab().save(str(out / "gamenext-tools.png"))
window.settings.tabs.setCurrentIndex(5)
QTest.qWait(150)
window.grab().save(str(out / "gamenext-api.png"))

# Capture Kilo Model Details popup.
popup = KiloModelDetailDialog(sample_models[1], 5.78, True, window)
popup.show()
QTest.qWait(150)
popup.grab().save(str(out / "gamenext-model-popup.png"))
popup.close()

window.resize(960, 640)
window.navigate(0)
QTest.qWait(150)
window.grab().save(str(out / "gamenext-compact.png"))
window.close()
app.processEvents()
print("Screenshots saved", flush=True)
