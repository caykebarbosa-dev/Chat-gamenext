"""Run one actual inference using the project's existing GGUF model."""
import sys
from pathlib import Path
from PyQt6.QtCore import QCoreApplication, QTimer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gamenext.infrastructure.local_backend import LocalBackend

app = QCoreApplication([])
backend = LocalBackend(ROOT / "output")
backend.state.connect(lambda value: print(value, flush=True))
backend.resources.connect(lambda value: print(value, flush=True))
backend.chunk.connect(lambda value: print("TEXT", value, flush=True))
result = {"success": False}


def complete(status):
    result["success"] = status == "concluído" and bool(backend.text)
    print("DONE", status, flush=True)
    (ROOT / "output" / "inference-validation.txt").write_text(backend.text + "\nStatus: " + status, encoding="utf-8")
    backend.shutdown()
    app.quit()


def fail(error):
    print("ERROR", error, flush=True)
    backend.shutdown()
    app.quit()


backend.failed.connect(fail)
backend.completed.connect(complete)
backend.ready_changed.connect(lambda ready: backend.generate([
    {"role": "user", "content": "Responda em português: quanto é 2 + 2? Seja breve."}
], "Baixo") if ready else None)
backend.load({
    "executable": str(ROOT / "runtime/llama-vulkan/llama-server.exe"),
    "model": str(ROOT / "Qwen3.5-4B-Q3_K_S.gguf"),
    "ram": 0, "vram": 0, "gpu_mode": "auto",
    "device": "Vulkan", "gpu_device": "Vulkan0", "context": 8192, "threads": 4, "threads_batch": 8, "batch": 512, "ubatch": 256,
})
QTimer.singleShot(240000, lambda: fail("Timeout"))
app.exec()
sys.exit(0 if result["success"] else 1)
