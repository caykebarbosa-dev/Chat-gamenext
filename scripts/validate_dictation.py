"""Two real local Whisper requests, using a prerecorded fixture rather than a live mic."""
import sys
import tempfile
from pathlib import Path
from PyQt6.QtCore import QCoreApplication, QTimer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gamenext.application.audio_controller import AudioController
from gamenext.infrastructure.storage import Repository

app = QCoreApplication([])
repo = Repository(Path(tempfile.mkdtemp()) / "audio.sqlite3")
audio = AudioController(repo)
texts = []


def ready(text):
    texts.append(text)
    print("DICTATION", len(texts), text, flush=True)
    if len(texts) == 2:
        QTimer.singleShot(10, app.quit)


audio.text_ready.connect(ready)
audio.error.connect(lambda error: (print("ERROR", error, flush=True), app.quit()))
audio.transcribe_file(ROOT / "output/whisper-test.wav")
audio.transcribe_file(ROOT / "output/whisper-test.wav")
QTimer.singleShot(30000, app.quit)
app.exec()
audio.shutdown()
repo.close()
assert len(texts) == 2 and all("microfone" in text.lower() for text in texts)
print("CONTINUOUS QUEUE OK", flush=True)
