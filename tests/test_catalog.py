"""GGUF validation without loading weights or trusting file extensions."""
import struct
import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gamenext.infrastructure.catalog import read_metadata


class CatalogTests(unittest.TestCase):
    def test_invalid_and_truncated_headers(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fake.gguf"
            path.write_bytes(b"not a model")
            with self.assertRaises(ValueError):
                read_metadata(path)
            path.write_bytes(b"GGUF" + struct.pack("<I", 3))
            with self.assertRaises(ValueError):
                read_metadata(path)

    def test_metadata_after_skipped_token_array(self):
        def text(value):
            data = value.encode()
            return struct.pack("<Q", len(data)) + data
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "model.gguf"
            path.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 0, 2)
                             + text("tokenizer.ggml.tokens") + struct.pack("<IIQ", 9, 8, 2)
                             + text("one") + text("two")
                             + text("general.architecture") + struct.pack("<I", 8) + text("qwen35"))
            self.assertEqual(read_metadata(path), {"general.architecture": "qwen35"})
