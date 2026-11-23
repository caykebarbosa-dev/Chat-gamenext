"""Owned llama.cpp process, loopback-only HTTP and cancellable SSE streaming."""
import json
import socket
import time
import secrets
import re
from pathlib import Path
import psutil
from PyQt6.QtCore import QObject, QProcess, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from gamenext.infrastructure.windows_job import MemoryJob


RESPONSE_PRESETS = {
    "Baixo": 1024,
    "Curto": 1024,
    "Médio": 2048,
    "Alto": 4096,
    "Livre": 0,
}


class LocalBackend(QObject):
    state = pyqtSignal(str)
    ready_changed = pyqtSignal(bool)
    chunk = pyqtSignal(str)
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)
    resources = pyqtSignal(str)
    usage = pyqtSignal(dict)

    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self.data_dir = data_dir
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_logs)
        self.process.started.connect(self.attach_limits)
        self.process.finished.connect(self.process_finished)
        self.process.errorOccurred.connect(self.process_error)
        self.network = QNetworkAccessManager(self)
        self.poll = QTimer(self)
        self.poll.setInterval(750)
        self.poll.timeout.connect(self.health)
        self.monitor = QTimer(self)
        self.monitor.setInterval(1000)
        self.monitor.timeout.connect(self.sample_resources)
        self.ready = False
        self.reply = None
        self.health_reply = None
        self.job = None
        self.port = 0
        self.buffer = b""
        self.text = ""
        self.logs = ""
        self.model_path = ""
        self.config = {}
        self.started_at = 0.0
        self.cancelled = False
        self.shutting_down = False
        self.api_key = ""
        self.tool_calls = []
        self.call_parts = {}
        self.gpu_summary = ""
        self.finish_reason = None
        self.oom_attempt = 0

    def process_error(self, error):
        if not self.shutting_down:
            self.state.emit("Backend: " + self.process.errorString())
            if error == QProcess.ProcessError.FailedToStart:
                self.ready_changed.emit(False)
                self.failed.emit("Não foi possível iniciar o modelo: " + self.process.errorString())

    def load(self, config: dict, _oom_attempt: int = 0):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            raise ValueError("Descarregue o modelo atual antes de carregar outro")
        executable, model = Path(config["executable"]), Path(config["model"])
        if not executable.is_file() or not model.is_file():
            raise ValueError("Selecione llama-server.exe e um modelo GGUF existente")
        with model.open("rb") as stream:
            if stream.read(4) != b"GGUF":
                raise ValueError("O arquivo não é um GGUF válido")

        self.oom_attempt = _oom_attempt
        gpu_mode = config.get("gpu_mode", "auto")
        gpu_device = config.get("gpu_device") or ""
        has_gpu = bool(re.fullmatch(r"(?:Vulkan|CUDA|ROCm|SYCL)\d+", gpu_device))
        if gpu_mode == "cpu" or not has_gpu or _oom_attempt >= 3:
            gpu_mode = "cpu"

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]

        self.config = config.copy()
        self.config["effective_gpu_mode"] = gpu_mode
        self.api_key = secrets.token_urlsafe(32)
        self.model_path = str(model)
        self.logs = ""
        self.gpu_summary = ""
        self.shutting_down = False

        args = [
            "--model", str(model),
            "--host", "127.0.0.1",
            "--port", str(self.port),
            "--log-verbosity", "4",
            "--parallel", "1",
            "--jinja",
            "--no-webui",
            "--no-warmup",
            "--load-mode", "auto",
            "--api-key", self.api_key,
        ]

        if gpu_mode == "cpu":
            args.extend(["--device", "none", "--n-gpu-layers", "0", "--fit", "off"])
        elif gpu_mode == "gpu_all" and _oom_attempt == 0:
            args.extend(["--device", gpu_device, "--n-gpu-layers", "all", "--fit", "off"])
        elif gpu_mode == "custom" and _oom_attempt == 0:
            layers = max(0, int(config.get("gpu_layers", 0)))
            args.extend(["--device", gpu_device, "--n-gpu-layers", str(layers), "--fit", "off"])
        else:
            # Auto hybrid mode: leaves comfortable Vulkan headroom and retries with larger margin on OOM.
            args.extend(["--device", gpu_device, "--n-gpu-layers", "auto", "--fit", "on"])
            vram_budget = int(config.get("vram", 0) or 0)
            gpu_total = int(config.get("gpu_total", 0) or 0)
            base_margin = max(1024, gpu_total - vram_budget) if (vram_budget > 0 and gpu_total > vram_budget) else 1024
            retry_margins = (base_margin, max(base_margin, 2048), max(base_margin, 3200))
            margin = retry_margins[min(_oom_attempt, len(retry_margins) - 1)]
            args.extend(["--fit-target", str(margin)])

        flash_attn = config.get("flash_attn", "auto")
        if flash_attn in {"auto", "on", "off"}:
            args.extend(["--flash-attn", flash_attn])

        kv_cache = config.get("kv_cache", "f16")
        if _oom_attempt >= 1 and kv_cache == "f16":
            kv_cache = "q8_0"
        if kv_cache in {"q8_0", "q4_0"}:
            args.extend(["--cache-type-k", kv_cache, "--cache-type-v", kv_cache])

        if not config.get("thinking", False):
            args.extend(["--reasoning", "off"])

        threads = int(config.get("threads", 0) or 0)
        threads_batch = int(config.get("threads_batch", 0) or 0) or threads
        for flag, value in (
            ("--ctx-size", int(config.get("context", 0) or 0)),
            ("--threads", threads),
            ("--threads-batch", threads_batch),
            ("--batch-size", int(config.get("batch", 0) or 0)),
            ("--ubatch-size", int(config.get("ubatch", 0) or 0)),
        ):
            if value > 0:
                args.extend([flag, str(value)])

        self.started_at = time.monotonic()
        self.state.emit("Carregando modelo local…")
        self.process.setWorkingDirectory(str(executable.parent))
        self.process.start(str(executable), args)

    def attach_limits(self):
        try:
            ram_cap = int(self.config.get("ram", 0) or 0)
            self.job = MemoryJob(int(self.process.processId()), ram_cap)
            self.poll.start()
            self.monitor.start()
            mode = self.config.get("effective_gpu_mode", "auto")
            if mode == "cpu":
                self.state.emit("Carregando modelo na CPU…")
            elif mode == "gpu_all":
                self.state.emit("Carregando todas as camadas na GPU…")
            else:
                self.state.emit("Carregando na GPU (ajuste automático GPU + RAM)…")
        except OSError as error:
            self.state.emit("Não foi possível vincular o processo local: " + str(error))
            self.process.kill()

    def read_logs(self):
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.logs = (self.logs + data)[-60_000:]
        if not self.ready:
            with (self.data_dir / "backend.log").open("a", encoding="utf-8") as stream:
                stream.write(data)

    def summarize_load(self):
        gpu_device = self.config.get("gpu_device") or ""
        mode = self.config.get("effective_gpu_mode", "auto")
        if mode == "cpu" or not gpu_device:
            self.gpu_summary = "CPU · execução local sem limite artificial"
            return
        device = re.escape(gpu_device)
        adapter = re.search(rf"using device {device} \(([^)]+)\)", self.logs, re.I)
        layers = re.search(r"offloaded (\d+)/(\d+) layers to GPU", self.logs)
        buffers = re.findall(rf"\b{device}\s+\w+ buffer size\s*=\s*([\d.]+) MiB", self.logs)
        adapter_name = adapter[1] if adapter else gpu_device
        parts = [adapter_name]
        if layers:
            loaded, total = int(layers[1]), int(layers[2])
            if loaded >= total and total > 0:
                parts.append(f"{loaded}/{total} camadas na GPU (100%)")
            elif loaded > 0:
                parts.append(f"{loaded}/{total} camadas na GPU (híbrido GPU + RAM)")
            else:
                parts.append("0 camadas na GPU (CPU)")
        if buffers:
            allocated = sum(map(float, buffers))
            parts.append(f"{allocated:.0f} MiB VRAM")
        self.gpu_summary = " · ".join(parts)

    def health(self):
        if self.health_reply:
            return
        if time.monotonic() - self.started_at > 600:
            self.state.emit("Tempo de carregamento excedido; consulte os detalhes do backend")
            self.unload()
            return
        request = QNetworkRequest(QUrl(f"http://127.0.0.1:{self.port}/health"))
        request.setRawHeader(b"Authorization", ("Bearer " + self.api_key).encode())
        request.setTransferTimeout(2000)
        self.health_reply = self.network.get(request)

        def done():
            reply = self.health_reply
            self.health_reply = None
            if reply and not self.shutting_down and reply.error() == QNetworkReply.NetworkError.NoError:
                self.summarize_load()
                self.ready = True
                self.poll.stop()
                self.state.emit("Modelo local pronto · " + Path(self.model_path).name + " · " + self.gpu_summary)
                self.ready_changed.emit(True)
            if reply:
                reply.deleteLater()

        self.health_reply.finished.connect(done)

    def generate(self, messages: list[dict], reasoning: str, tools: list | None = None):
        if not self.ready or self.reply:
            raise ValueError("Carregue um modelo em Configurações → Modelos antes de enviar")
        self.text, self.buffer, self.cancelled = "", b"", False
        self.tool_calls, self.call_parts = [], {}
        self.finish_reason = None

        token_budget = int(self.config.get("response_tokens", -1))
        if token_budget == -1:
            token_budget = RESPONSE_PRESETS.get(reasoning, 0)

        temperature = float(self.config.get("temperature", 0.6))
        thinking = bool(self.config.get("thinking", False))
        payload = {
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": temperature,
            "chat_template_kwargs": {"enable_thinking": thinking},
        }
        if token_budget > 0:
            payload["max_tokens"] = token_budget
        if tools:
            payload.update(tools=tools, tool_choice="auto", parallel_tool_calls=False)

        request = QNetworkRequest(QUrl(f"http://127.0.0.1:{self.port}/v1/chat/completions"))
        request.setRawHeader(b"Authorization", ("Bearer " + self.api_key).encode())
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        request.setTransferTimeout(600000)
        self.reply = self.network.post(request, json.dumps(payload).encode())
        self.reply.readyRead.connect(self.read_stream)
        self.reply.finished.connect(self.finish_stream)

    def read_stream(self):
        if not self.reply:
            return
        self.buffer += bytes(self.reply.readAll())
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            line = line.strip()
            if not line.startswith(b"data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == b"[DONE]":
                continue
            try:
                event = json.loads(payload)
                if isinstance(event.get("usage"), dict):
                    self.usage.emit(event["usage"])
                choices = event.get("choices") or []
                if not choices:
                    continue
                self.finish_reason = choices[0].get("finish_reason") or self.finish_reason
                delta = choices[0].get("delta", {})
                for fragment in delta.get("tool_calls", []):
                    index = fragment.get("index", 0)
                    part = self.call_parts.setdefault(
                        index,
                        {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                    )
                    if fragment.get("id"):
                        part["id"] = fragment["id"]
                    function = fragment.get("function", {})
                    if function.get("name"):
                        part["function"]["name"] += function["name"]
                    if function.get("arguments"):
                        part["function"]["arguments"] += function["arguments"]
                content = delta.get("content", "")
                if isinstance(content, str) and content:
                    self.text += content
                    self.chunk.emit(self.text)
            except (ValueError, IndexError, AttributeError):
                self.failed.emit("Resposta de streaming inválida do backend")
                self.cancel()

    def finish_stream(self):
        reply = self.reply
        if not reply:
            return
        self.read_stream()
        self.tool_calls = [self.call_parts[index] for index in sorted(self.call_parts)]
        self.reply = None
        if self.cancelled:
            self.completed.emit("cancelado")
        elif reply.error() != QNetworkReply.NetworkError.NoError:
            try:
                detail = json.loads(self.buffer).get("error", {})
                diagnostic = detail.get("message", "") if isinstance(detail, dict) else str(detail)
            except (ValueError, AttributeError):
                diagnostic = ""
            self.failed.emit("Inferência falhou: " + (diagnostic[:320] or reply.errorString()))
            self.completed.emit("erro")
        else:
            self.completed.emit("concluído")
        reply.deleteLater()

    def cancel(self):
        if self.reply:
            self.cancelled = True
            self.reply.abort()

    def sample_resources(self):
        try:
            process = psutil.Process(int(self.process.processId()))
            info = process.memory_info()
            committed = getattr(info, "private", info.rss) / 1048576
            ram_cap = int(self.config.get("ram", 0) or 0)
            cap = f" / {ram_cap} MiB" if ram_cap else " (sem teto)"
            self.resources.emit(
                f"RAM residente {info.rss / 1048576:.0f} MiB · privada {committed:.0f} MiB{cap} · "
                f"RAM livre {psutil.virtual_memory().available / 1073741824:.1f} GiB"
            )
        except (psutil.Error, ValueError):
            pass

    def process_finished(self, code, status):
        was_ready = self.ready
        self.ready = False
        self.poll.stop()
        self.monitor.stop()
        self.cancel()
        if self.job:
            self.job.close()
            self.job = None
        oom_error = bool(re.search(r"ErrorOutOfDeviceMemory|unable to allocate|failed to allocate", self.logs, re.I))
        if (
            not self.shutting_down
            and not was_ready
            and oom_error
            and self.config.get("gpu_mode", "auto") != "cpu"
            and self.oom_attempt < 3
        ):
            next_attempt = self.oom_attempt + 1
            mode_note = "em modo CPU" if next_attempt >= 3 else f"com mais margem de VRAM (tentativa {next_attempt + 1}/4)"
            self.state.emit(f"VRAM ocupada por outros apps · reajustando carga {mode_note}…")
            QTimer.singleShot(250, lambda cfg=self.config.copy(), att=next_attempt: self.load(cfg, _oom_attempt=att))
            return
        self.ready_changed.emit(False)
        if not self.shutting_down:
            self.state.emit(f"Backend encerrado ({code}). Abra os detalhes para ver o motivo.")
            self.failed.emit("O backend foi encerrado. " + self.logs[-1200:])

    def unload(self):
        self.shutting_down = True
        self.ready = False
        self.ready_changed.emit(False)
        self.poll.stop()
        self.monitor.stop()
        self.cancel()
        if self.health_reply:
            self.health_reply.abort()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
        if self.job:
            self.job.close()
            self.job = None

    def shutdown(self):
        self.unload()
        self.process.waitForFinished(1500)
