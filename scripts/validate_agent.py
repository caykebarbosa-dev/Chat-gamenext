"""Real model -> function call -> filesystem -> model response, isolated history."""
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
app.setQuitOnLastWindowClosed(False)
app.setStyleSheet(STYLE)
directory = Path(tempfile.mkdtemp(prefix="gamenext-agent-check-"))
fixture = directory / "validation.txt"
fixture.write_text("Código de validação: GN-4827", encoding="utf-8")
window = build_window(directory)
window.resize(1440, 900)
window.settings.controls["context"].setValue(4096)
sent = False
passed = False


def ready(value):
    global sent
    if value and not sent:
        sent = True
        window.navigate(0)
        window.fill_prompt(f'Use a ferramenta computer action=read para ler o arquivo "{fixture}" e me diga o código de validação encontrado. Não adivinhe.')
        window.send()


def finish():
    global passed
    message = window.repository.messages(window.current_id)[-1]
    passed = bool(message.tool_runs) and any(run["ok"] for run in message.tool_runs) and "GN-4827" in message.content
    print("AGENT_RESULT", passed, message.content, "TOOLS", message.tool_runs, "TOKENS", message.prompt_tokens, message.completion_tokens, flush=True)
    (ROOT / "output/agent-validation.txt").write_text(str(message.serialize()), encoding="utf-8")
    QTimer.singleShot(200, capture)


def capture():
    window.grab().save(str(ROOT / "output/gamenext-agent.png"))
    window.close()
    app.quit()


window.backend.state.connect(lambda text: print(text, flush=True))
window.backend.failed.connect(lambda text: print("ERROR", text, flush=True))
window.controller.activity.connect(lambda text: print(text, flush=True))
window.backend.ready_changed.connect(ready)
window.controller.finished.connect(finish)
QTimer.singleShot(2500, window.settings.model_panel.load)
QTimer.singleShot(240000, capture)
app.exec()
sys.exit(0 if passed else 1)
