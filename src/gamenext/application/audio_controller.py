"""Continuous dictation: Windows capture, real-time FFT bands, local Whisper or Groq API."""
from __future__ import annotations

import json
import sys
import tempfile
import time
import wave
from collections import deque
from pathlib import Path
import numpy as np
from PyQt6.QtCore import QObject, QTimer, QProcess, QThread, QByteArray, QBuffer, QIODevice, pyqtSignal
from PyQt6.QtMultimedia import QMediaDevices, QAudioSource, QAudioFormat, QAudio
from gamenext.infrastructure.groq_api import (
    DEFAULT_GROQ_STT_MODEL,
    resolve_groq_api_key,
    transcribe_audio_with_groq,
)


def pcm_to_int16(raw: bytes, format_: QAudioFormat) -> bytes:
    """Convert native PCM to mono PCM16, retaining the input sample rate."""
    formats = {
        QAudioFormat.SampleFormat.UInt8: (np.uint8, 128, 128),
        QAudioFormat.SampleFormat.Int16: (np.int16, 0, 32768),
        QAudioFormat.SampleFormat.Int32: (np.int32, 0, 2147483648),
        QAudioFormat.SampleFormat.Float: (np.float32, 0, 1),
    }
    if format_.sampleFormat() not in formats:
        raise ValueError("Formato de microfone não suportado")
    dtype, offset, scale = formats[format_.sampleFormat()]
    frame_size = np.dtype(dtype).itemsize * format_.channelCount()
    raw = raw[:len(raw) // frame_size * frame_size]
    samples = (np.frombuffer(raw, dtype=dtype).astype(np.float32) - offset) / scale
    samples = samples.reshape(-1, format_.channelCount()).mean(axis=1)
    return (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()


def compute_spectrum_bands(pcm: bytes) -> list[float]:
    """Compute 5 normalized frequency bands (0..1) from PCM16 for VoiceBeam visualization."""
    if len(pcm) < 64:
        return [0.0, 0.0, 0.0, 0.0, 0.0]
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    if len(samples) > 1024:
        samples = samples[-1024:]
    window = np.hanning(len(samples))
    spectrum = np.abs(np.fft.rfft(samples * window))
    # Focus on voice frequency region (lower 60% of bins).
    usable = max(5, int(len(spectrum) * 0.6))
    bands = []
    for b in range(5):
        start = max(1, int(b * usable / 5))
        end = max(start + 1, int((b + 1) * usable / 5))
        mag = float(np.mean(spectrum[start:end])) if end <= len(spectrum) else 0.0
        # Gentle logarithmic compression so normal speech produces lively waves.
        level = min(1.0, float(np.log1p(mag * 0.9) / 2.6))
        bands.append(level)
    return bands


class PauseSegmenter:
    """Collect speech and dispatch utterances after a 450 ms pause or 8 s of speech."""
    def __init__(self, sample_rate: int):
        self.rate = sample_rate
        self.reset()

    def reset(self):
        self.pre_roll = b""
        self.utterance = bytearray()
        self.silence = 0.0
        self.voiced = 0.0

    def feed(self, pcm: bytes) -> list[bytes]:
        if not pcm:
            return []
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
        duration = len(samples) / self.rate
        audible = float(np.sqrt(np.mean(samples * samples))) >= 180
        if audible:
            if not self.utterance:
                self.utterance.extend(self.pre_roll)
            self.utterance.extend(pcm)
            self.voiced += duration
            self.silence = 0.0
        elif self.utterance:
            self.utterance.extend(pcm)
            self.silence += duration
        self.pre_roll = (self.pre_roll + pcm)[-int(self.rate * 0.2) * 2:]
        if self.utterance and (self.silence >= 0.45 or len(self.utterance) / 2 / self.rate >= 8):
            segment = self.flush()
            return [segment] if segment else []
        return []

    def flush(self) -> bytes:
        pcm = bytes(self.utterance) if self.voiced >= 0.18 else b""
        self.utterance.clear()
        self.voiced = 0.0
        self.silence = 0.0
        return pcm


class GroqTranscribeThread(QThread):
    finished_result = pyqtSignal(dict)

    def __init__(self, path: Path, api_key: str, model: str, parent=None):
        super().__init__(parent)
        self.path = path
        self.api_key = api_key
        self.model = model

    def run(self):
        started = time.perf_counter()
        try:
            text = transcribe_audio_with_groq(
                self.path.read_bytes(),
                suffix=self.path.suffix or ".wav",
                api_key=self.api_key,
                model=self.model,
                language="pt",
            )
            self.finished_result.emit({"text": text, "elapsed": time.perf_counter() - started})
        except Exception as error:
            self.finished_result.emit({"error": str(error)})


class AudioController(QObject):
    state = pyqtSignal(str)
    recording_changed = pyqtSignal(bool)
    text_ready = pyqtSignal(str)
    error = pyqtSignal(str)
    levels = pyqtSignal(list)

    def __init__(self, repository, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.source = None
        self.buffer = None
        self.data = None
        self.format = None
        self.segmenter = None
        self.offset = 0
        self.recording = False
        self.transcribing = False
        self.worker_ready = False
        self.pending_path = None
        self.groq_thread: GroqTranscribeThread | None = None
        self.queue = deque()
        self.output = b""
        self.stopping = False
        self.worker = QProcess(self)
        self.worker.readyReadStandardOutput.connect(self.read_worker)
        self.worker.readyReadStandardError.connect(lambda: self.worker.readAllStandardError())
        self.worker.errorOccurred.connect(self.worker_error)
        self.worker.finished.connect(self.worker_finished)
        self.capture_timer = QTimer(self)
        self.capture_timer.setInterval(40)
        self.capture_timer.timeout.connect(self.consume_audio)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.transcription_timeout)

    @property
    def model_dir(self):
        return Path(__file__).resolve().parents[3] / "runtime/whisper-tiny"

    @property
    def provider(self) -> str:
        return "groq" if self.repository.preference("voice_provider", "whisper") == "groq" else "whisper"

    def inputs(self):
        return QMediaDevices.audioInputs()

    def selected_input(self):
        saved = self.repository.preference("microphone_id", "")
        return next((d for d in self.inputs() if bytes(d.id()).hex() == saved), QMediaDevices.defaultAudioInput())

    def ensure_worker(self):
        if self.provider == "groq":
            return
        if self.worker.state() == QProcess.ProcessState.NotRunning:
            self.worker_ready = False
            self.output = b""
            script = Path(__file__).resolve().parents[1] / "infrastructure/whisper_worker.py"
            self.worker.start(sys.executable, ["-u", str(script), str(self.model_dir)])

    def start_recording(self, device):
        if self.recording:
            return
        if device.isNull():
            self.error.emit("Nenhum microfone encontrado no Windows")
            return
        if self.provider == "groq":
            if not resolve_groq_api_key(self.repository):
                self.error.emit("Configure sua chave da Groq em Configurações → API ou use Whisper local.")
                return
        elif not (self.model_dir / "model.bin").is_file():
            self.error.emit("Whisper Tiny não encontrado em runtime/whisper-tiny")
            return
        self.repository.set_preference("microphone_id", bytes(device.id()).hex())
        requested = QAudioFormat()
        requested.setSampleRate(16000)
        requested.setChannelCount(1)
        requested.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self.format = requested if device.isFormatSupported(requested) else device.preferredFormat()
        self.segmenter = PauseSegmenter(self.format.sampleRate())
        self.offset = 0
        self.data = QByteArray()
        self.buffer = QBuffer(self.data, self)
        self.buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        self.source = QAudioSource(device, self.format, self)
        self.source.stateChanged.connect(self.audio_state)
        self.recording = True
        self.source.start(self.buffer)
        if self.source and self.source.error() != QAudio.Error.NoError:
            self.cancel_recording()
            self.error.emit("Verifique as permissões de microfone do Windows.")
            return
        self.ensure_worker()
        self.capture_timer.start()
        self.recording_changed.emit(True)
        engine = "Groq API" if self.provider == "groq" else "Whisper local"
        self.state.emit(f"Ditado ligado ({engine}) · fale normalmente · clique no microfone para desligar")

    def audio_state(self, state):
        if self.recording and self.source and state == QAudio.State.StoppedState and self.source.error() != QAudio.Error.NoError:
            self.cancel_recording()
            self.error.emit("Microfone interrompido. Confira o dispositivo e a privacidade do Windows.")

    def consume_audio(self):
        if not self.recording or not self.data:
            return
        frame = self.format.bytesPerFrame()
        end = len(self.data) // frame * frame
        raw = bytes(self.data.mid(self.offset, end - self.offset))
        self.offset = end
        if not raw:
            return
        pcm = pcm_to_int16(raw, self.format)
        self.levels.emit(compute_spectrum_bands(pcm))
        block = max(2, int(self.format.sampleRate() * 0.08) * 2)
        for start in range(0, len(pcm), block):
            for segment in self.segmenter.feed(pcm[start:start + block]):
                self.enqueue_pcm(segment)
        if self.offset > self.format.sampleRate() * frame * 15:
            self.buffer.seek(0)
            self.data.clear()
            self.offset = 0

    def enqueue_pcm(self, pcm):
        if len(self.queue) >= 12:
            self.error.emit("Ditado em processamento. Aguarde a transcrição antes de continuar.")
            self.stop_recording()
            return
        with tempfile.NamedTemporaryFile(prefix="gamenext-audio-", suffix=".wav", delete=False) as file:
            path = Path(file.name)
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(self.format.sampleRate())
            stream.writeframes(pcm)
        self.queue.append(path)
        self.pump()

    def transcribe_file(self, path: Path):
        self.queue.append(path)
        self.ensure_worker()
        self.pump()

    def pump(self):
        if self.transcribing or not self.queue:
            return
        if self.provider == "groq":
            api_key = resolve_groq_api_key(self.repository)
            if not api_key:
                self.error.emit("Chave da Groq ausente. Configure em Configurações → API.")
                while self.queue:
                    self.cleanup_audio(self.queue.popleft())
                return
            self.pending_path = self.queue.popleft()
            self.transcribing = True
            model = str(self.repository.preference("groq_model", DEFAULT_GROQ_STT_MODEL) or DEFAULT_GROQ_STT_MODEL)
            self.timeout.start(35000)
            self.groq_thread = GroqTranscribeThread(self.pending_path, api_key, model, self)
            self.groq_thread.finished_result.connect(self._on_groq_result)
            self.groq_thread.start()
            self.state.emit("Transcrevendo com Groq API…" if not self.recording else "Ouvindo e transcrevendo (Groq API)…")
            return

        self.ensure_worker()
        if not self.worker_ready:
            return
        self.pending_path = self.queue.popleft()
        self.transcribing = True
        self.timeout.start(120000)
        self.worker.write((json.dumps({"path": str(self.pending_path)}) + "\n").encode())
        self.state.emit("Ouvindo e transcrevendo…" if self.recording else "Finalizando o ditado…")

    def _on_groq_result(self, event: dict):
        self.timeout.stop()
        self.transcribing = False
        self.groq_thread = None
        self.cleanup_audio()
        if event.get("error"):
            self.error.emit("Groq: " + event["error"])
        elif event.get("text", "").strip():
            self.text_ready.emit(event["text"].strip())
            self.state.emit(
                "Ditado ligado (Groq) · pode continuar falando"
                if self.recording
                else f"Texto pronto (Groq) · {event.get('elapsed', 0):.1f} s"
            )
        self.pump()

    def release_capture(self):
        self.recording = False
        self.capture_timer.stop()
        self.levels.emit([0.0, 0.0, 0.0, 0.0, 0.0])
        if self.source:
            self.source.stop()
            self.source.deleteLater()
            self.source = None
        if self.buffer:
            self.buffer.close()
            self.buffer.deleteLater()
            self.buffer = None
        self.data = None
        self.recording_changed.emit(False)

    def stop_recording(self):
        if not self.recording:
            return
        self.consume_audio()
        remaining = self.segmenter.flush()
        if remaining:
            self.enqueue_pcm(remaining)
        self.release_capture()
        self.state.emit("Finalizando o ditado…" if self.transcribing or self.queue else "Ditado desligado")

    def cancel_recording(self):
        self.release_capture()
        if self.segmenter:
            self.segmenter.reset()

    def read_worker(self):
        self.output += bytes(self.worker.readAllStandardOutput())
        while b"\n" in self.output:
            line, self.output = self.output.split(b"\n", 1)
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("ready"):
                self.worker_ready = True
                self.pump()
            elif "text" in event or "error" in event:
                self.timeout.stop()
                self.transcribing = False
                self.cleanup_audio()
                if event.get("error"):
                    self.error.emit("Whisper: " + event["error"])
                elif event.get("text", "").strip():
                    self.text_ready.emit(event["text"].strip())
                    self.state.emit(
                        "Ditado ligado · pode continuar falando"
                        if self.recording
                        else f"Texto pronto · transcrição em {event['elapsed']:.1f} s"
                    )
                self.pump()

    def cleanup_audio(self, path=None):
        path = path or self.pending_path
        if path:
            if path.name.startswith("gamenext-audio-") and path.parent == Path(tempfile.gettempdir()):
                path.unlink(missing_ok=True)
            if path == self.pending_path:
                self.pending_path = None

    def worker_error(self, error):
        if not self.stopping:
            self.error.emit("Whisper interrompido: " + self.worker.errorString())
        self.transcribing = False
        self.timeout.stop()
        self.cleanup_audio()
        self.cancel_recording()
        while self.queue:
            self.cleanup_audio(self.queue.popleft())

    def worker_finished(self):
        self.worker_ready = False
        if self.transcribing and self.provider != "groq":
            self.worker_error(None)

    def transcription_timeout(self):
        self.error.emit("Transcrição excedeu o tempo limite.")
        self.cancel_transcription()

    def cancel_transcription(self):
        self.transcribing = False
        self.timeout.stop()
        if self.groq_thread and self.groq_thread.isRunning():
            self.groq_thread.quit()
            self.groq_thread.wait(800)
            self.groq_thread = None
        if self.worker.state() != QProcess.ProcessState.NotRunning:
            self.worker.kill()
        self.worker_ready = False
        self.cleanup_audio()
        while self.queue:
            self.cleanup_audio(self.queue.popleft())

    def shutdown(self):
        self.stopping = True
        self.cancel_recording()
        self.cancel_transcription()
        self.worker.waitForFinished(1500)
