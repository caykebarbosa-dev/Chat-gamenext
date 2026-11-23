"""Async SSE streaming backend for Kilo Code Gateway (OpenAI-compatible + tools + reasoning)."""
from __future__ import annotations

import json
from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from gamenext.infrastructure.kilo_api import (
    DEFAULT_USD_TO_BRL,
    KILO_CHAT_URL,
    KiloModelInfo,
    calculate_request_cost_usd,
    load_kilo_models,
    resolve_kilo_api_key,
)

EFFORT_MAP = {
    "Desligado": "off",
    "Curto": "low",
    "Baixo": "low",
    "Médio": "medium",
    "Alto": "high",
    "Livre": "medium",
}


def _extract_error(raw: bytes, status_code: int) -> str:
    text = raw.decode("utf-8", errors="replace").strip()
    try:
        parsed = json.loads(text)
        err = parsed.get("error") if isinstance(parsed, dict) else None
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])[:280]
        if isinstance(err, str) and err:
            return err[:280]
    except ValueError:
        pass
    if status_code in {401, 403}:
        return "Chave da API do Kilo recusada ou expirada. Verifique em Configurações → API."
    if status_code == 402:
        return "Saldo insuficiente no Kilo Gateway. Selecione um modelo gratuito ou adicione créditos."
    if status_code == 429:
        return "Limite de requisições do Kilo Gateway atingido. Aguarde alguns segundos."
    return f"Kilo Gateway retornou erro HTTP {status_code}."


class KiloBackend(QObject):
    chunk = pyqtSignal(str)
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)
    usage = pyqtSignal(dict)

    def __init__(self, repository, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.network = QNetworkAccessManager(self)
        self.reply = None
        self.buffer = b""
        self.text = ""
        self.cancelled = False
        self.tool_calls = []
        self.call_parts = {}
        self.finish_reason = None
        self._last_request = None
        self._model_info: KiloModelInfo | None = None

    def model_info(self, model_id: str) -> KiloModelInfo | None:
        return next((m for m in load_kilo_models(self.repository) if m.id == model_id), None)

    def generate(
        self,
        messages: list[dict],
        reasoning: str,
        tools: list | None = None,
        *,
        model_id: str = "",
        _opts: dict | None = None,
    ):
        if self.reply:
            raise ValueError("Já existe uma geração em andamento na Kilo Gateway.")
        api_key = resolve_kilo_api_key(self.repository)
        if not api_key:
            raise ValueError("Conecte sua chave da Kilo Gateway API em Configurações → API.")
        if not model_id:
            raise ValueError("Selecione um modelo Kilo Gateway antes de enviar.")

        info = self.model_info(model_id)
        self._model_info = info
        opts = dict(_opts) if _opts is not None else {
            "use_reasoning": bool(info.supports_reasoning if info else False) and EFFORT_MAP.get(reasoning, "medium") != "off",
            "include_stream_options": True,
            "use_tools": bool(tools) and (info.supports_tools if info else True),
        }
        self._last_request = {
            "messages": messages,
            "reasoning": reasoning,
            "tools": tools,
            "model_id": model_id,
            "opts": opts,
        }

        self.text, self.buffer, self.cancelled = "", b"", False
        self.tool_calls, self.call_parts = [], {}
        self.finish_reason = None

        payload: dict = {
            "model": model_id,
            "messages": messages,
            "stream": True,
        }
        if opts["include_stream_options"]:
            payload["stream_options"] = {"include_usage": True}
        if opts["use_tools"] and tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if opts["use_reasoning"]:
            effort = EFFORT_MAP.get(reasoning, "medium")
            if effort != "off":
                payload["reasoning"] = {"effort": effort}

        request = QNetworkRequest(QUrl(KILO_CHAT_URL))
        request.setRawHeader(b"Authorization", ("Bearer " + api_key).encode("utf-8"))
        request.setRawHeader(b"Accept", b"text/event-stream")
        request.setRawHeader(b"HTTP-Referer", b"https://gamenext.local")
        request.setRawHeader(b"X-Title", b"GameNext")
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        request.setTransferTimeout(180000)

        self.reply = self.network.post(request, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
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
            except ValueError:
                continue
            if isinstance(event.get("error"), dict):
                self.failed.emit(str(event["error"].get("message") or "Erro no stream da Kilo Gateway."))
                self.cancel()
                return
            if isinstance(event.get("usage"), dict):
                usage = dict(event["usage"])
                cost_usd = calculate_request_cost_usd(self._model_info, usage)
                rate = float(self.repository.preference("kilo_usd_to_brl", DEFAULT_USD_TO_BRL) or DEFAULT_USD_TO_BRL)
                if cost_usd is not None:
                    usage["cost_usd"] = cost_usd
                    usage["cost_brl"] = cost_usd * rate
                self.usage.emit(usage)
            choices = event.get("choices") or []
            if not choices:
                continue
            self.finish_reason = choices[0].get("finish_reason") or self.finish_reason
            delta = choices[0].get("delta") or {}
            for fragment in delta.get("tool_calls") or []:
                index = int(fragment.get("index", 0))
                part = self.call_parts.setdefault(
                    index,
                    {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                )
                if fragment.get("id"):
                    part["id"] = fragment["id"]
                function = fragment.get("function") or {}
                if function.get("name"):
                    part["function"]["name"] += function["name"]
                if function.get("arguments"):
                    part["function"]["arguments"] += function["arguments"]
            content = delta.get("content")
            if isinstance(content, str) and content:
                self.text += content
                self.chunk.emit(self.text)

    def finish_stream(self):
        reply = self.reply
        if not reply:
            return
        status_code = int(reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0)
        self.read_stream()
        self.tool_calls = [self.call_parts[index] for index in sorted(self.call_parts)]
        self.reply = None

        if self.cancelled:
            reply.deleteLater()
            self.completed.emit("cancelado")
            return

        if reply.error() != QNetworkReply.NetworkError.NoError or status_code >= 400:
            raw_body = self.buffer
            reply.deleteLater()
            # Graceful fallback for models rejecting reasoning/stream_options/tools on HTTP 400/404/422.
            if status_code in {400, 404, 422} and self._last_request:
                body_lower = raw_body.decode("utf-8", errors="replace").lower()
                opts = dict(self._last_request["opts"])
                retried = False
                if opts.get("use_reasoning") and "reasoning" in body_lower:
                    opts["use_reasoning"] = False
                    retried = True
                elif opts.get("include_stream_options") and "stream_options" in body_lower:
                    opts["include_stream_options"] = False
                    retried = True
                elif opts.get("use_tools") and ("tool" in body_lower or "function" in body_lower):
                    opts["use_tools"] = False
                    retried = True
                if retried:
                    req = self._last_request
                    self.generate(
                        req["messages"],
                        req["reasoning"],
                        req["tools"],
                        model_id=req["model_id"],
                        _opts=opts,
                    )
                    return
            self.failed.emit(_extract_error(raw_body, status_code))
            self.completed.emit("erro")
            return

        # Handle non-stream JSON response if gateway returned a single JSON object.
        if not self.text and not self.tool_calls and self.buffer.strip().startswith(b"{"):
            try:
                body = json.loads(self.buffer)
                msg = (body.get("choices") or [{}])[0].get("message") or {}
                if isinstance(msg.get("content"), str) and msg["content"]:
                    self.text = msg["content"]
                    self.chunk.emit(self.text)
                if isinstance(msg.get("tool_calls"), list):
                    self.tool_calls = msg["tool_calls"]
                if isinstance(body.get("usage"), dict):
                    usage = dict(body["usage"])
                    cost_usd = calculate_request_cost_usd(self._model_info, usage)
                    rate = float(self.repository.preference("kilo_usd_to_brl", DEFAULT_USD_TO_BRL) or DEFAULT_USD_TO_BRL)
                    if cost_usd is not None:
                        usage["cost_usd"] = cost_usd
                        usage["cost_brl"] = cost_usd * rate
                    self.usage.emit(usage)
            except ValueError:
                pass

        reply.deleteLater()
        self.completed.emit("concluído")

    def cancel(self):
        if self.reply:
            self.cancelled = True
            self.reply.abort()
