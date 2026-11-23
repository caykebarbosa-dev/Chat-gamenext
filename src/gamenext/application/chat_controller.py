"""Unified conversation orchestration for both Local GGUF and Kilo Gateway models + autonomous tools."""
from __future__ import annotations

import base64
import json
import mimetypes
import time
from pathlib import Path
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from gamenext.application.tool_controller import parse_tool_arguments
from gamenext.domain.models import Message
from gamenext.infrastructure.demo import response
from gamenext.infrastructure.document_reader import read_document
from gamenext.infrastructure.storage import Repository

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

SYSTEM_PROMPT = (
    "Você é GameNext, um assistente em português rodando no Windows do usuário. "
    "Você tem liberdade para usar as ferramentas disponíveis (computer, internet, screenshot, mcp, api) "
    "sempre que o pedido envolver ações no computador, arquivos, pastas, comandos, pesquisa/navegação web, "
    "captura de tela, Blender/Godot ou APIs. "
    "Quando o usuário pedir para criar código, jogos, páginas HTML/CSS/JS, textos ou explicações sem pedir "
    "para salvar em disco, entregue o conteúdo completo diretamente no chat em blocos Markdown com a linguagem. "
    "Se o usuário pedir para salvar, editar, abrir arquivo/pasta ou executar algo no computador, use a ferramenta computer diretamente. "
    "Só afirme ações confirmadas pelos resultados das ferramentas. "
    "Se uma chamada de ferramenta retornar erro, corrija os argumentos ou explique o problema com clareza."
)


class ChatController(QObject):
    chunk = pyqtSignal(str)
    finished = pyqtSignal()
    failed = pyqtSignal(str)
    activity = pyqtSignal(str)

    def __init__(self, repository: Repository, backend=None, tool_controller=None, kilo_backend=None):
        super().__init__()
        self.repository = repository
        self.backend = backend
        self.kilo_backend = kilo_backend
        self.tools = tool_controller
        if tool_controller:
            tool_controller.result.connect(self.tool_result)
            tool_controller.activity.connect(self.activity)
        self.agent_messages = []
        self.pending_calls = []
        self.round_count = 0
        self.round_prefix = ""
        self.last_round_text = ""
        self.last_error = ""
        self.generating = False
        self.active_provider = "local"
        self.active_model_id = ""

        if backend:
            backend.chunk.connect(self._on_local_chunk)
            backend.completed.connect(self._on_local_completed)
            backend.failed.connect(self._on_local_failed)
            backend.usage.connect(self._on_local_usage)
        if kilo_backend:
            kilo_backend.chunk.connect(self._on_kilo_chunk)
            kilo_backend.completed.connect(self._on_kilo_completed)
            kilo_backend.failed.connect(self._on_kilo_failed)
            kilo_backend.usage.connect(self._on_kilo_usage)

        self.timer = QTimer(self)
        self.timer.setInterval(22)
        self.timer.timeout.connect(self.tick)
        self.message = None
        self.cid = None
        self.full_text = ""
        self.position = 0
        self.started_at = 0.0
        self.recovering_tool_call = False
        self.use_tools = False

    def _current_backend(self):
        return self.kilo_backend if self.active_provider == "kilo" else self.backend

    def _on_local_chunk(self, text: str):
        if self.active_provider == "local":
            self.receive(text)

    def _on_local_completed(self, status: str):
        if self.active_provider == "local":
            self.complete(status)

    def _on_local_failed(self, error: str):
        if self.active_provider == "local":
            self._on_backend_failed(error)

    def _on_local_usage(self, usage: dict):
        if self.active_provider == "local":
            self.receive_usage(usage)

    def _on_kilo_chunk(self, text: str):
        if self.active_provider == "kilo":
            self.receive(text)

    def _on_kilo_completed(self, status: str):
        if self.active_provider == "kilo":
            self.complete(status)

    def _on_kilo_failed(self, error: str):
        if self.active_provider == "kilo":
            self._on_backend_failed(error)

    def _on_kilo_usage(self, usage: dict):
        if self.active_provider == "kilo":
            self.receive_usage(usage)

    def _on_backend_failed(self, error: str):
        self.last_error = error
        self.failed.emit(error)

    @property
    def active(self) -> bool:
        if self.backend or self.kilo_backend:
            return self.generating
        return self.timer.isActive()

    @staticmethod
    def _build_user_content(text: str, attachments: list[str], supports_images: bool):
        if not attachments:
            return text
        text_blocks = [text] if text else []
        image_parts = []
        for item in attachments:
            path = Path(item)
            suffix = path.suffix.lower()
            if supports_images and suffix in IMAGE_EXTENSIONS and path.is_file() and path.stat().st_size <= 8 * 1024 * 1024:
                mime = mimetypes.guess_type(str(path))[0] or "image/png"
                b64 = base64.b64encode(path.read_bytes()).decode("ascii")
                image_parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
                text_blocks.append(f"[Imagem anexada: {path.name}]")
                continue
            try:
                content = read_document(path, limit=12000)
                text_blocks.append(f"[Arquivo anexado: {path}]\n{content}")
            except Exception:
                text_blocks.append(f"[Arquivo anexado (caminho local): {path}]")
        combined_text = "\n\n".join(text_blocks)
        if image_parts:
            return [{"type": "text", "text": combined_text}, *image_parts]
        return combined_text

    def start(
        self,
        cid: str,
        prompt: str,
        attachments: list[str],
        task_mode: bool,
        *,
        provider: str = "local",
        model_id: str = "",
        model_label: str = "",
    ):
        self.started_at = time.perf_counter()
        self.round_count = 0
        self.round_prefix = ""
        self.last_round_text = ""
        self.last_error = ""
        self.recovering_tool_call = False
        self.active_provider = "kilo" if (provider == "kilo" and self.kilo_backend is not None) else "local"
        self.active_model_id = model_id
        self.use_tools = bool(self.tools and self.tools.available())
        self.cid = cid
        self.repository.save_message(cid, Message("user", prompt, attachments))
        self.message = Message(
            "assistant",
            "",
            status="processando",
            provider=self.active_provider,
            model_name=model_label or model_id or None,
        )
        self.repository.save_message(cid, self.message)
        self.full_text = response(prompt, task_mode, attachments)
        self.position = 0

        active_backend = self._current_backend()
        if active_backend:
            self.generating = True
            history = self.repository.messages(cid)
            supports_images = False
            if self.active_provider == "kilo" and self.kilo_backend is not None:
                info = self.kilo_backend.model_info(model_id)
                supports_images = bool(info and info.supports_image_input)

            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            past = [m for m in history[:-1] if m.content][-12:]
            for idx, m in enumerate(past):
                content = m.content[-6000:]
                if idx == len(past) - 1 and m.role == "user" and attachments:
                    content = self._build_user_content(content, attachments, supports_images)
                messages.append({"role": m.role, "content": content})
            self.agent_messages = messages
            try:
                self.generate_round()
            except ValueError as error:
                self._on_backend_failed(str(error))
                self.complete("erro")
        else:
            self.timer.start()

    def receive(self, text: str):
        self.last_round_text = text
        self.message.content = self.round_prefix + text
        self.chunk.emit(self.message.content)
        self.repository.save_message(self.cid, self.message)

    def receive_usage(self, usage: dict):
        if self.message and self.generating:
            self.message.prompt_tokens = (self.message.prompt_tokens or 0) + int(usage.get("prompt_tokens", 0) or 0)
            self.message.completion_tokens = (self.message.completion_tokens or 0) + int(usage.get("completion_tokens", 0) or 0)
            if usage.get("cost_usd") is not None:
                self.message.cost_usd = (self.message.cost_usd or 0.0) + float(usage["cost_usd"])
            if usage.get("cost_brl") is not None:
                self.message.cost_brl = (self.message.cost_brl or 0.0) + float(usage["cost_brl"])

    def generate_round(self):
        self.round_count += 1
        self.last_round_text = ""
        tools = self.tools.available() if self.use_tools and not self.recovering_tool_call else None
        reasoning = self.repository.preference("reasoning", "Livre")
        if self.active_provider == "kilo":
            self.kilo_backend.generate(self.agent_messages, reasoning, tools, model_id=self.active_model_id)
        else:
            self.backend.generate(self.agent_messages, reasoning, tools)

    @staticmethod
    def complete_tool_call(call):
        try:
            function = call["function"]
            if not (call.get("id") and function.get("name")):
                return False
            parsed = parse_tool_arguments(function.get("arguments", "{}"))
            return isinstance(parsed, dict)
        except (KeyError, TypeError, ValueError):
            return False

    def recover_tool_call(self):
        self.recovering_tool_call = True
        self.agent_messages[0]["content"] += (
            " A chamada de ferramenta anterior veio malformada e não pôde ser executada."
            " Responda diretamente ao usuário de forma completa no chat."
        )
        self.activity.emit("Chamada incompleta detectada. Respondendo diretamente no chat…")
        self.execute_next()

    def execute_next(self):
        if not self.generating:
            return
        if self.pending_calls:
            self.tools.execute(self.pending_calls.pop(0))
        else:
            self.round_prefix = self.message.content + ("\n\n" if self.message.content else "")
            try:
                self.generate_round()
            except ValueError as error:
                self._on_backend_failed(str(error))
                self.complete("erro")

    def tool_result(self, event):
        if not self.generating:
            return
        call = event["call"]
        if call.get("id", "").startswith("connection_test_"):
            return
        result = event.get("result") if event.get("ok") else {"error": event.get("error", "Falha")}
        text = json.dumps(result, ensure_ascii=False)
        self.agent_messages.append({"role": "tool", "tool_call_id": call["id"], "content": text[:8000]})
        self.message.tool_runs.append({
            "tool": call["function"]["name"],
            "ok": bool(event.get("ok")),
            "summary": text[:8000],
            "elapsed": event.get("elapsed", 0),
        })
        self.repository.save_message(self.cid, self.message)
        self.activity.emit(call["function"]["name"] + (" concluído" if event.get("ok") else " retornou erro"))
        QTimer.singleShot(0, self.execute_next)

    def complete(self, status: str):
        if not self.generating:
            return
        active_backend = self._current_backend()
        if status == "concluído" and active_backend and active_backend.tool_calls and self.tools and not self.recovering_tool_call:
            if any(not self.complete_tool_call(call) for call in active_backend.tool_calls):
                self.recover_tool_call()
                return
            if self.round_count >= 20:
                self.message.content += "\n\nLimite de 20 etapas consecutivas de ferramentas atingido. Envie uma continuação se desejar prosseguir."
            else:
                calls = active_backend.tool_calls
                self.agent_messages.append({"role": "assistant", "content": self.last_round_text or None, "tool_calls": calls})
                self.pending_calls = calls.copy()
                self.execute_next()
                return
        if status == "erro" and not self.message.content.strip() and self.last_error:
            self.message.content = self.last_error
        if status == "concluído" and active_backend and active_backend.finish_reason == "length":
            status = "limite de resposta atingido"
        self.generating = False
        self.message.status = status
        self.message.elapsed_seconds = time.perf_counter() - self.started_at
        self.repository.save_message(self.cid, self.message)
        self.finished.emit()

    def tick(self):
        self.position = min(self.position + 7, len(self.full_text))
        self.message.content = self.full_text[:self.position]
        self.chunk.emit(self.message.content)
        if self.position % 35 == 0:
            self.repository.save_message(self.cid, self.message)
        if self.position == len(self.full_text):
            self.stop("concluído")

    def stop(self, status: str = "cancelado"):
        if not self.active:
            return
        active_backend = self._current_backend()
        if active_backend:
            if self.tools:
                self.tools.cancel()
            self.pending_calls = []
            active_backend.cancel()
            if self.generating:
                self.complete(status)
            return
        self.timer.stop()
        self.message.status = status
        self.message.elapsed_seconds = time.perf_counter() - self.started_at
        self.repository.save_message(self.cid, self.message)
        self.finished.emit()
