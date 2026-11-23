"""Validate calls and permissions outside the model; own the isolated tool process."""
import json
import re
import sys
import time
from pathlib import Path
from uuid import uuid4
import psutil
from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal
from jsonschema import validate
from gamenext.infrastructure.tool_specs import TOOLS


def parse_tool_arguments(raw: str) -> dict:
    """Parse tool-call JSON tolerating minor local-model formatting artifacts."""
    text = (raw or "{}").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except ValueError:
        pass
    # Trim accidental markdown fences or trailing tags like </tool_call> or '>'
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        candidate = cleaned[start:end + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except ValueError:
            pass
    raise ValueError("Argumentos JSON inválidos na chamada da ferramenta")


def sanitize_arguments(arguments: dict, spec: dict) -> dict:
    """Clean small local-model artifacts (e.g. 'open_folder>') and unknown keys."""
    props = spec["function"]["parameters"].get("properties", {})
    cleaned = {}
    for key, value in arguments.items():
        if key not in props:
            continue
        prop = props[key]
        if isinstance(value, str):
            if "enum" in prop:
                normalized = value.strip().strip("<>\"'` ")
                if normalized in prop["enum"]:
                    value = normalized
                else:
                    matched = next((item for item in prop["enum"] if item.casefold() == normalized.casefold()), None)
                    if matched is not None:
                        value = matched
            elif prop.get("type") == "string":
                if key in {"path", "cwd", "url", "server", "tool", "profile"}:
                    value = value.strip().strip("<>")
        cleaned[key] = value
    return cleaned


class ToolController(QObject):
    result = pyqtSignal(dict)
    activity = pyqtSignal(str)
    approval_requested = pyqtSignal(dict)

    def __init__(self, repository, data_dir, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.data_dir = data_dir
        self.worker = QProcess(self)
        self.worker.readyReadStandardOutput.connect(self.read_result)
        self.worker.readyReadStandardError.connect(self.read_stderr)
        self.worker.errorOccurred.connect(self.worker_error)
        self.worker.finished.connect(self.worker_finished)
        self.buffer = b""
        self.stderr_tail = ""
        self.pending = None
        self.started = 0.0
        self.approval = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.timeout)

    def available(self):
        enabled = self.repository.preference("tool_enabled", {})
        return [tool for tool in TOOLS if enabled.get(tool["function"]["name"], True)]

    def execute(self, call):
        if self.pending:
            raise RuntimeError("Uma ferramenta já está em execução")
        try:
            function = call["function"]
            spec = next((item for item in self.available() if item["function"]["name"] == function["name"]), None)
            if not spec:
                raise PermissionError("Ferramenta desativada ou desconhecida")
            arguments = sanitize_arguments(parse_tool_arguments(function.get("arguments", "{}")), spec)
            validate(arguments, spec["function"]["parameters"])
        except Exception as error:
            self.result.emit({"call": call, "ok": False, "error": str(error)[:1000]})
            return
        self.pending = {"id": str(uuid4()), "call": call, "tool": function["name"], "arguments": arguments}
        self.started = time.perf_counter()
        modifying = (
            (function["name"] == "computer" and arguments.get("action") in {"write", "mkdir", "run_command"})
            or (function["name"] == "mcp" and arguments.get("action") == "call")
            or (function["name"] == "api" and arguments.get("method", "GET") != "GET")
            or (function["name"] == "internet" and arguments.get("action") in {"click", "type"})
        )
        if modifying and self.repository.preference("tool_ask_changes", False):
            self.approval = self.pending
            self.approval_requested.emit(self.pending)
        else:
            self.dispatch()

    def approve(self, allowed):
        if not self.approval or not self.pending:
            return
        self.approval = None
        if allowed:
            self.dispatch()
        else:
            self.finish({"ok": False, "error": "Ação negada pelo proprietário. Não tentar novamente esta chamada."})

    def dispatch(self):
        if self.pending["tool"] not in {item["function"]["name"] for item in self.available()}:
            self.finish({"ok": False, "error": "Permissão revogada"})
            return
        if self.worker.state() == QProcess.ProcessState.NotRunning:
            script = Path(__file__).resolve().parents[1] / "infrastructure/tool_worker.py"
            self.buffer = b""
            self.stderr_tail = ""
            env = QProcessEnvironment.systemEnvironment()
            env.insert("PYTHONUTF8", "1")
            env.insert("PYTHONIOENCODING", "utf-8")
            self.worker.setProcessEnvironment(env)
            self.worker.start(sys.executable, ["-u", str(script), str(self.data_dir)])
        payload = {key: self.pending[key] for key in ("id", "tool", "arguments")}
        payload["config"] = {
            "mcp_servers": self.repository.preference("mcp_servers", {}),
            "api_profiles": self.repository.preference("api_profiles", {}),
        }
        self.worker.write((json.dumps(payload) + "\n").encode())
        self.timer.start(180000)
        self.activity.emit("Executando " + self.pending["tool"] + "…")

    def read_result(self):
        self.buffer += bytes(self.worker.readAllStandardOutput())
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if self.pending and event.get("id") == self.pending["id"]:
                self.finish(event)

    def finish(self, event):
        if not self.pending:
            return
        self.timer.stop()
        event["call"] = self.pending["call"]
        event["elapsed"] = time.perf_counter() - self.started
        self.repository.audit_tool(self.pending["tool"], bool(event.get("ok")), event["elapsed"])
        self.pending = None
        self.approval = None
        self.result.emit(event)

    def read_stderr(self):
        text = bytes(self.worker.readAllStandardError()).decode("utf-8", errors="replace")
        self.stderr_tail = (self.stderr_tail + text)[-1500:]

    def worker_error(self, error):
        if self.pending:
            self.finish({"ok": False, "error": "Executor interrompido: " + self.worker.errorString()})

    def worker_finished(self):
        if self.pending:
            detail = (" · " + self.stderr_tail.strip().splitlines()[-1]) if self.stderr_tail.strip() else ""
            self.finish({"ok": False, "error": "Executor encerrou antes de responder" + detail})

    def timeout(self):
        self.finish({"ok": False, "error": "Tempo de execução excedido"})
        self.kill_worker()

    def kill_worker(self):
        pid = int(self.worker.processId())
        if pid:
            try:
                for child in psutil.Process(pid).children(recursive=True):
                    try:
                        child.kill()
                    except psutil.Error:
                        pass
            except psutil.Error:
                pass
        self.worker.kill()

    def cancel(self):
        self.timer.stop()
        self.pending = None
        self.approval = None
        self.kill_worker()

    def shutdown(self):
        self.cancel()
        self.worker.waitForFinished(1500)
