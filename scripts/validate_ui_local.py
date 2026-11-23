"""End-to-end UI validation against the real local model, not a fake server."""
import sys
import tempfile
from pathlib import Path
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gamenext.bootstrap import build_window
from gamenext.presentation.theme import STYLE

app = QApplication([])
app.setStyleSheet(STYLE)
window = build_window(Path(tempfile.mkdtemp(prefix="gamenext-real-test-")))
window.show()
window.resize(1440, 900)
window.navigate(2)
window.settings.tabs.setCurrentIndex(1)
result = {"sent": False, "success": False}


def ready(value):
    if value and not result["sent"]:
        result["sent"] = True
        window.navigate(0)
        window.fill_prompt("Quanto é 2 + 2? Responda só o número.")
        window.send()


def completed():
    records = window.repository.messages(window.current_id)
    answer = records[-1]
    result["success"] = answer.status == "concluído" and "4" in answer.content
    print("REAL_UI_RESULT", answer.content, answer.status, flush=True)
    QTimer.singleShot(250, capture)


def capture():
    window.grab().save(str(ROOT / "output/gamenext-real-chat.png"))
    window.navigate(2)
    window.settings.tabs.setCurrentIndex(1)
    QTimer.singleShot(150, finish)


def finish():
    window.grab().save(str(ROOT / "output/gamenext-real-backend.png"))
    window.close()
    app.quit()


window.backend.state.connect(lambda text: print(text, flush=True))
window.backend.failed.connect(lambda error: print("ERROR", error, flush=True))
window.backend.ready_changed.connect(ready)
window.controller.finished.connect(completed)
QTimer.singleShot(2000, window.settings.model_panel.load)
QTimer.singleShot(240000, finish)
app.exec()
sys.exit(0 if result["success"] else 1)
