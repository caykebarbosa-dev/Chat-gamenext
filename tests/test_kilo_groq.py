"""Unit tests for Kilo Gateway API, Groq voice API, unified chat selector and VoiceBeam."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
import httpx
import numpy as np
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gamenext.infrastructure.storage import Repository
from gamenext.infrastructure.kilo_api import (
    calculate_request_cost_usd,
    fetch_kilo_catalog,
    format_brl_per_million,
    load_enabled_kilo_ids,
    load_kilo_models,
    save_kilo_catalog,
)
from gamenext.infrastructure.groq_api import (
    transcribe_audio_with_groq,
    validate_groq_connection,
)
from gamenext.application.audio_controller import compute_spectrum_bands
from gamenext.presentation.kilo_model_dialog import KiloModelDetailDialog
from gamenext.presentation.voice_wave import VoiceWaveOverlay


SAMPLE_MODELS_PAYLOAD = {
    "data": [
        {
            "id": "google/gemini-2.5-flash:free",
            "name": "Gemini 2.5 Flash (Free)",
            "description": "Modelo multimodal rápido e gratuito.",
            "context_length": 1000000,
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"input_modalities": ["text", "image", "pdf"], "output_modalities": ["text"]},
            "supported_parameters": ["tools", "reasoning", "temperature"],
        },
        {
            "id": "anthropic/claude-sonnet-4",
            "name": "Claude Sonnet 4",
            "description": "Excelente para código e agentes.",
            "context_length": 200000,
            "pricing": {
                "prompt": "0.000003",
                "completion": "0.000015",
                "input_cache_read": "0.0000003",
            },
            "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]},
            "supported_parameters": ["tools", "reasoning"],
        },
    ]
}


class KiloGroqTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_kilo_catalog_parsing_pricing_and_selection(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if "api.kilo.ai/api/profile" in str(request.url):
                return httpx.Response(200, json={"ok": True})
            if "/models" in str(request.url):
                return httpx.Response(200, json=SAMPLE_MODELS_PAYLOAD)
            return httpx.Response(404)

        def fx_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"USDBRL": {"bid": "5.50"}})

        models, rate = fetch_kilo_catalog(
            "test-kilo-key",
            transport=httpx.MockTransport(handler),
            fx_transport=httpx.MockTransport(fx_handler),
        )
        self.assertEqual(len(models), 2)
        self.assertAlmostEqual(rate, 5.50)
        free_m = next(m for m in models if m.id.endswith(":free"))
        paid_m = next(m for m in models if "sonnet" in m.id)
        self.assertTrue(free_m.is_free)
        self.assertTrue(free_m.supports_image_input)
        self.assertTrue(free_m.supports_reasoning)
        self.assertEqual(paid_m.power_tier, "Ultra")
        self.assertEqual(format_brl_per_million(paid_m.input_usd_per_m, 5.50), "R$ 16,50")

        cost = calculate_request_cost_usd(paid_m, {"prompt_tokens": 1000, "completion_tokens": 500})
        self.assertAlmostEqual(cost, 0.0105, places=6)

        with tempfile.TemporaryDirectory() as folder:
            repo = Repository(Path(folder) / "db.sqlite3")
            enabled = save_kilo_catalog(repo, models, rate)
            self.assertEqual(enabled, [free_m.id])
            save_kilo_catalog(repo, models, rate, [paid_m.id])
            self.assertEqual(load_enabled_kilo_ids(repo), [paid_m.id])
            self.assertEqual(len(load_kilo_models(repo)), 2)
            repo.close()

        # Verify details popup builds cleanly with all model metadata.
        dialog = KiloModelDetailDialog(paid_m, rate, True)
        self.assertIn("Claude Sonnet 4", dialog.windowTitle())
        dialog.close()

    def test_groq_validation_and_transcription(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "whisper-large-v3-turbo"}, {"id": "llama-3.3-70b"}]})
            if request.url.path.endswith("/audio/transcriptions"):
                return httpx.Response(200, json={"text": "Olá GameNext com Groq"})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        models = validate_groq_connection("gsk_test_key", transport=transport)
        self.assertIn("whisper-large-v3-turbo", models)
        text = transcribe_audio_with_groq(b"RIFF....", suffix=".wav", api_key="gsk_test_key", transport=transport)
        self.assertEqual(text, "Olá GameNext com Groq")

    def test_voice_spectrum_bands_and_wave_overlay(self):
        pcm = (np.sin(np.linspace(0, 40, 1024)) * 12000).astype("<i2").tobytes()
        bands = compute_spectrum_bands(pcm)
        self.assertEqual(len(bands), 5)
        self.assertTrue(all(0.0 <= b <= 1.0 for b in bands))
        wave = VoiceWaveOverlay()
        wave.resize(600, 120)
        wave.start()
        wave.set_levels(bands)
        wave.repaint()
        wave.stop()
        wave.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
