"""Pause detection and PCM conversion do not depend on a live microphone."""
import sys
import unittest
from pathlib import Path
import numpy as np
from PyQt6.QtMultimedia import QAudioFormat

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gamenext.application.audio_controller import PauseSegmenter, pcm_to_int16


class DictationTests(unittest.TestCase):
    def test_segments_after_pause_without_stopping_microphone(self):
        segmenter = PauseSegmenter(16000)
        voiced = np.full(1280, 2000, dtype="<i2").tobytes()
        silence = np.zeros(1280, dtype="<i2").tobytes()
        for _ in range(5):
            self.assertEqual(segmenter.feed(voiced), [])
        results = []
        for _ in range(6):
            results += segmenter.feed(silence)
        self.assertEqual(len(results), 1)
        # A second utterance uses the same active segmenter.
        for _ in range(5):
            segmenter.feed(voiced)
        second = []
        for _ in range(6):
            second += segmenter.feed(silence)
        self.assertEqual(len(second), 1)

    def test_silence_does_not_create_transcriptions(self):
        segmenter = PauseSegmenter(16000)
        self.assertEqual(segmenter.feed(np.zeros(16000, dtype="<i2").tobytes()), [])
        self.assertEqual(segmenter.flush(), b"")

    def test_native_stereo_float_is_mixed_to_mono(self):
        format_ = QAudioFormat()
        format_.setSampleRate(48000)
        format_.setChannelCount(2)
        format_.setSampleFormat(QAudioFormat.SampleFormat.Float)
        raw = np.array([[0.5, 0.5], [-0.5, -0.5]], dtype=np.float32).tobytes()
        samples = np.frombuffer(pcm_to_int16(raw, format_), dtype="<i2")
        self.assertEqual(len(samples), 2)
        self.assertAlmostEqual(samples[0], 16383, delta=1)
