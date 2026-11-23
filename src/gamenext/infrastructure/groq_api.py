"""Conexão Groq API (console.groq.com) para fala para texto ultrarrápido no chat."""
from __future__ import annotations

import os
from typing import Any
import httpx

GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
DEFAULT_GROQ_STT_MODEL = "whisper-large-v3-turbo"
GROQ_STT_MODELS: tuple[str, ...] = (
    "whisper-large-v3-turbo",
    "whisper-large-v3",
)
_KEYRING_SERVICE = "GameNext"
_KEYRING_GROQ_USER = "groq-stt-api-key"

_MIME_BY_SUFFIX: dict[str, str] = {
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".flac": "audio/flac",
    ".mpeg": "audio/mpeg",
    ".mpga": "audio/mpeg",
}


def save_groq_api_key(repository, api_key: str) -> None:
    token = str(api_key or "").strip()
    stored_in_keyring = False
    try:
        import keyring
        if token:
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_GROQ_USER, token)
            stored_in_keyring = True
        else:
            try:
                keyring.delete_password(_KEYRING_SERVICE, _KEYRING_GROQ_USER)
            except Exception:
                pass
    except Exception:
        stored_in_keyring = False
    repository.set_preference("groq_has_key", bool(token))
    repository.set_preference("groq_api_key_fallback", "" if stored_in_keyring else token)


def resolve_groq_api_key(repository=None) -> str:
    for env_name in ("GROQ_API_KEY", "GAMENEXT_GROQ_API_KEY"):
        val = str(os.environ.get(env_name) or "").strip()
        if val:
            return val
    try:
        import keyring
        token = keyring.get_password(_KEYRING_SERVICE, _KEYRING_GROQ_USER)
        if token and token.strip():
            return token.strip()
    except Exception:
        pass
    if repository is not None:
        return str(repository.preference("groq_api_key_fallback", "") or "").strip()
    return ""


def _normalize_language(language: str | None) -> str | None:
    raw = str(language or "").strip().lower()
    if not raw or raw == "auto":
        return None
    if "-" in raw:
        raw = raw.split("-", 1)[0]
    if "_" in raw:
        raw = raw.split("_", 1)[0]
    return raw[:5] if raw else None


def validate_groq_connection(
    api_key: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> list[str]:
    clean_key = str(api_key or "").strip()
    if not clean_key:
        raise ValueError("Cole sua chave da API Groq primeiro.")
    headers = {"Authorization": f"Bearer {clean_key}"}
    try:
        with httpx.Client(timeout=15.0, transport=transport) as client:
            resp = client.get(GROQ_MODELS_URL, headers=headers)
    except httpx.TimeoutException as exc:
        raise ValueError("Tempo esgotado ao conectar à Groq API.") from exc
    except httpx.RequestError as exc:
        raise ValueError(f"Falha de rede na Groq API: {exc}") from exc

    if resp.status_code in {401, 403}:
        raise ValueError("Chave da API da Groq inválida ou expirada.")
    if resp.status_code >= 400:
        raise ValueError(f"Groq API retornou HTTP {resp.status_code}.")
    try:
        payload: Any = resp.json()
    except ValueError as exc:
        raise ValueError("Resposta inválida da Groq API.") from exc

    raw_items = payload.get("data") if isinstance(payload, dict) else None
    found_ids: list[str] = []
    if isinstance(raw_items, list):
        for entry in raw_items:
            if not isinstance(entry, dict):
                continue
            mid = str(entry.get("id") or "").strip()
            if "whisper" in mid.lower() and mid not in found_ids:
                found_ids.append(mid)
    ordered = [m for m in GROQ_STT_MODELS if m in found_ids]
    for mid in found_ids:
        if mid not in ordered:
            ordered.append(mid)
    return ordered or list(GROQ_STT_MODELS)


def transcribe_audio_with_groq(
    audio_bytes: bytes,
    *,
    suffix: str = ".wav",
    api_key: str,
    model: str = DEFAULT_GROQ_STT_MODEL,
    language: str | None = "pt",
    transport: httpx.BaseTransport | None = None,
) -> str:
    if not audio_bytes:
        return ""
    clean_key = str(api_key or "").strip()
    if not clean_key:
        raise ValueError("Conecte sua chave da Groq em Configurações → API.")
    safe_suffix = suffix.lower() if suffix.lower() in _MIME_BY_SUFFIX else ".wav"
    mime = _MIME_BY_SUFFIX[safe_suffix]
    selected_model = str(model or "").strip() or DEFAULT_GROQ_STT_MODEL
    data: dict[str, str] = {"model": selected_model, "response_format": "json"}
    lang = _normalize_language(language)
    if lang:
        data["language"] = lang

    headers = {"Authorization": f"Bearer {clean_key}"}
    files = {"file": (f"mic{safe_suffix}", audio_bytes, mime)}
    try:
        with httpx.Client(timeout=25.0, transport=transport) as client:
            resp = client.post(GROQ_TRANSCRIBE_URL, headers=headers, data=data, files=files)
    except httpx.TimeoutException as exc:
        raise ValueError("Tempo esgotado na transcrição Groq.") from exc
    except httpx.RequestError as exc:
        raise ValueError(f"Falha de rede na Groq API: {exc}") from exc

    if resp.status_code in {401, 403}:
        raise ValueError("Chave da API da Groq inválida ou expirada.")
    if resp.status_code == 429:
        raise ValueError("Limite de requisições da Groq atingido. Aguarde alguns instantes.")
    if resp.status_code >= 400:
        raise ValueError(f"Falha ao transcrever áudio na Groq API (HTTP {resp.status_code}).")
    try:
        body: Any = resp.json()
    except ValueError as exc:
        raise ValueError("Resposta inválida da Groq API na transcrição.") from exc
    if not isinstance(body, dict):
        raise ValueError("Formato inesperado da Groq API.")
    return str(body.get("text") or "").strip()
