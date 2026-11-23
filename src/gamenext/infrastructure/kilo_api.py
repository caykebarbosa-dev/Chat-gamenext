"""Conexão oficial com a API do Kilo Code Gateway (kilo.ai) e catálogo de modelos."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field, asdict
from threading import RLock
from typing import Any
import httpx

KILO_GATEWAY_URL = "https://ai-gateway.kilo.ai/api/v1"
KILO_MODELS_URL = f"{KILO_GATEWAY_URL}/models"
KILO_CHAT_URL = f"{KILO_GATEWAY_URL}/chat/completions"
KILO_PROFILE_URL = "https://api.kilo.ai/api/profile"
DEFAULT_USD_TO_BRL = 5.78
_KEYRING_SERVICE = "GameNext"
_KEYRING_KILO_USER = "kilo-gateway-api-key"
_FX_LOCK = RLock()
_FX_CACHE: tuple[float, float] | None = None


@dataclass
class KiloCapability:
    key: str
    icon: str
    label: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KiloCapability":
        return cls(
            key=str(data.get("key") or "text"),
            icon=str(data.get("icon") or "text"),
            label=str(data.get("label") or "Texto"),
        )


@dataclass
class KiloModelInfo:
    id: str
    name: str = ""
    description: str = ""
    is_free: bool = False
    power_tier: str = "Médio"
    input_usd_per_m: float | None = 0.0
    output_usd_per_m: float | None = 0.0
    cache_read_usd_per_m: float | None = None
    cache_write_usd_per_m: float | None = None
    request_usd: float = 0.0
    context_length: int = 128_000
    input_modalities: list[str] = field(default_factory=lambda: ["text"])
    output_modalities: list[str] = field(default_factory=lambda: ["text"])
    supported_parameters: list[str] = field(default_factory=list)
    capabilities: list[KiloCapability] = field(default_factory=list)

    @property
    def supports_reasoning(self) -> bool:
        return any(cap.key == "reasoning" for cap in self.capabilities)

    @property
    def supports_image_input(self) -> bool:
        return "image" in self.input_modalities or any(cap.key == "image" for cap in self.capabilities)

    @property
    def supports_audio_input(self) -> bool:
        return "audio" in self.input_modalities

    @property
    def supports_pdf_input(self) -> bool:
        return "pdf" in self.input_modalities or "file" in self.input_modalities

    @property
    def supports_tools(self) -> bool:
        return (
            not self.supported_parameters
            or "tools" in self.supported_parameters
            or any(cap.key == "code" for cap in self.capabilities)
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["capabilities"] = [cap.to_dict() for cap in self.capabilities]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KiloModelInfo":
        caps = [
            KiloCapability.from_dict(c) if isinstance(c, dict) else c
            for c in (data.get("capabilities") or [])
        ]
        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or data.get("id") or ""),
            description=str(data.get("description") or ""),
            is_free=bool(data.get("is_free", False)),
            power_tier=str(data.get("power_tier") or "Médio"),
            input_usd_per_m=data.get("input_usd_per_m"),
            output_usd_per_m=data.get("output_usd_per_m"),
            cache_read_usd_per_m=data.get("cache_read_usd_per_m"),
            cache_write_usd_per_m=data.get("cache_write_usd_per_m"),
            request_usd=float(data.get("request_usd") or 0.0),
            context_length=int(data.get("context_length") or 128_000),
            input_modalities=list(data.get("input_modalities") or ["text"]),
            output_modalities=list(data.get("output_modalities") or ["text"]),
            supported_parameters=list(data.get("supported_parameters") or []),
            capabilities=caps or [KiloCapability("text", "text", "Texto e conversa")],
        )


def _parse_usd_per_million(raw: Any) -> float | None:
    if raw is None:
        return 0.0
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if value < 0:
        return None
    return value * 1_000_000.0


def classify_power_tier(
    model_id: str,
    name: str,
    input_usd_per_m: float | None,
    output_usd_per_m: float | None,
    is_free: bool,
) -> str:
    text = f"{model_id} {name}".lower()
    peak = max(input_usd_per_m or 0.0, output_usd_per_m or 0.0)
    ultra_tokens = ("ultra", "opus", "fable", "frontier", "o1-", "/o1", "o3-pro", "550b", "405b")
    max_tokens = ("-max", ":max", " max", "sonnet", "hydrogen", "/o3", "/o4", "super", "large")
    if any(k in text for k in ultra_tokens) or "gpt-6" in text or "carbon" in text or peak >= 8.0:
        return "Ultra"
    if (any(k in text for k in max_tokens) and not any(k in text for k in ("mini", "nano"))) or peak >= 1.5:
        return "Max"
    free_basic = is_free and not any(k in text for k in ("30b", "70b", "flash", "beam"))
    basic_tokens = ("nano", "micro", "mini", "lite", "efficient", "1b", "1.7b", "2b", "3b", "4b", "7b", "8b", "9b")
    if any(k in text for k in basic_tokens) or free_basic or (output_usd_per_m is not None and 0.0 <= peak <= 0.25 and "flash" not in text):
        return "Básico"
    return "Médio"


def extract_capabilities(item: dict[str, Any]) -> list[KiloCapability]:
    arch = item.get("architecture") or {}
    in_mods = {str(x).lower() for x in (arch.get("input_modalities") or [])}
    out_mods = {str(x).lower() for x in (arch.get("output_modalities") or [])}
    params = {str(x).lower() for x in (item.get("supported_parameters") or [])}
    text = f"{item.get('id', '')} {item.get('name', '')}".lower()

    caps: list[KiloCapability] = []
    supports_code = (
        bool(item.get("opencode"))
        or any(k in text for k in ("code", "coder", "codex", "devstral", "codestral", "swe"))
        or ("tools" in params and "text" in (out_mods or {"text"}))
    )
    if supports_code:
        caps.append(KiloCapability("code", "code", "Programação e código"))
    if "video" in in_mods or "video" in out_mods:
        vlabel = "Vê e gera vídeo" if ("video" in in_mods and "video" in out_mods) else ("Gera vídeo" if "video" in out_mods else "Vê e analisa vídeo")
        caps.append(KiloCapability("video", "video", vlabel))
    if "image" in in_mods or "image" in out_mods:
        ilabel = "Vê e gera imagem" if ("image" in in_mods and "image" in out_mods) else ("Gera imagem" if "image" in out_mods else "Vê e analisa imagem")
        caps.append(KiloCapability("image", "image", ilabel))
    if "audio" in in_mods or "audio" in out_mods:
        alabel = "Ouve e gera áudio" if ("audio" in in_mods and "audio" in out_mods) else ("Gera áudio" if "audio" in out_mods else "Ouve e analisa áudio")
        caps.append(KiloCapability("audio", "audio", alabel))
    if "pdf" in in_mods or "file" in in_mods:
        caps.append(KiloCapability("file", "file", "Lê arquivos e PDFs"))
    if "reasoning" in params or any(k in text for k in ("reasoning", "thinking", "-r1")):
        caps.append(KiloCapability("reasoning", "brain", "Raciocínio avançado"))
    if not caps:
        caps.append(KiloCapability("text", "text", "Texto e conversa"))
    return caps


def format_brl_per_million(usd_per_m: float | None, usd_to_brl: float) -> str:
    if usd_per_m is None:
        return "Dinâmico"
    brl = max(0.0, usd_per_m * usd_to_brl)
    if brl == 0.0:
        return "R$ 0,00"
    if brl < 0.01:
        return f"R$ {brl:.3f}".replace(".", ",")
    return f"R$ {brl:.2f}".replace(".", ",")


def format_usd_per_million(usd_per_m: float | None) -> str:
    if usd_per_m is None:
        return "Dinâmico"
    val = max(0.0, float(usd_per_m))
    if val == 0.0:
        return "US$ 0,00"
    if val < 0.01:
        return f"US$ {val:.4f}".replace(".", ",")
    return f"US$ {val:.2f}".replace(".", ",")


def format_request_cost_brl(cost_usd: float | None, usd_to_brl: float) -> str:
    if cost_usd is None:
        return ""
    brl = max(0.0, float(cost_usd) * float(usd_to_brl or DEFAULT_USD_TO_BRL))
    if brl == 0.0:
        return "R$ 0,00"
    if brl < 0.01:
        return f"R$ {brl:.4f}".replace(".", ",")
    return f"R$ {brl:.2f}".replace(".", ",")


def calculate_request_cost_usd(model: KiloModelInfo | None, usage: dict[str, Any]) -> float | None:
    direct_cost = usage.get("cost")
    if isinstance(direct_cost, (int, float)) and not isinstance(direct_cost, bool):
        return max(0.0, float(direct_cost))
    if model is None:
        return None
    if model.is_free:
        return 0.0
    if model.input_usd_per_m is None or model.output_usd_per_m is None:
        return None

    prompt_tokens = max(0, int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0))
    completion_tokens = max(0, int(usage.get("completion_tokens") or usage.get("output_tokens") or 0))
    details = usage.get("prompt_tokens_details") or {}
    cached_tokens = min(
        prompt_tokens,
        max(0, int(details.get("cached_tokens") or usage.get("cache_read_input_tokens") or 0)),
    )
    uncached_prompt = max(0, prompt_tokens - cached_tokens)
    cache_write_tokens = max(0, int(usage.get("cache_creation_input_tokens") or 0))

    cache_read_rate = model.cache_read_usd_per_m if model.cache_read_usd_per_m is not None else model.input_usd_per_m
    cache_write_rate = model.cache_write_usd_per_m if model.cache_write_usd_per_m is not None else model.input_usd_per_m
    total = (
        (uncached_prompt * model.input_usd_per_m)
        + (cached_tokens * cache_read_rate)
        + (cache_write_tokens * cache_write_rate)
        + (completion_tokens * model.output_usd_per_m)
    ) / 1_000_000.0 + max(0.0, float(model.request_usd or 0.0))
    return round(total, 8)


def fetch_usd_to_brl(*, transport: httpx.BaseTransport | None = None) -> float:
    global _FX_CACHE
    now = time.monotonic()
    with _FX_LOCK:
        if transport is None and _FX_CACHE is not None and now - _FX_CACHE[1] < 1800:
            return _FX_CACHE[0]

    endpoints = (
        ("https://economia.awesomeapi.com.br/json/last/USD-BRL", lambda d: d["USDBRL"]["bid"]),
        ("https://open.er-api.com/v6/latest/USD", lambda d: d["rates"]["BRL"]),
    )
    with httpx.Client(timeout=4.0, transport=transport, follow_redirects=True) as client:
        for url, extractor in endpoints:
            try:
                resp = client.get(url)
                if resp.status_code != 200:
                    continue
                rate = float(extractor(resp.json()))
                if 1.0 <= rate <= 30.0:
                    if transport is None:
                        with _FX_LOCK:
                            _FX_CACHE = (rate, now)
                    return rate
            except Exception:
                continue
    return DEFAULT_USD_TO_BRL


def extract_models(payload: Any) -> list[KiloModelInfo]:
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError("Resposta da API do Kilo não contém a lista de modelos.")
    seen: dict[str, KiloModelInfo] = {}
    for item in items:
        if isinstance(item, str):
            model_id = item.strip()
            if not model_id or model_id in seen:
                continue
            is_free = model_id.endswith(":free")
            seen[model_id] = KiloModelInfo(
                id=model_id,
                name=model_id,
                is_free=is_free,
                power_tier=classify_power_tier(model_id, model_id, 0.0, 0.0, is_free),
                capabilities=[KiloCapability("text", "text", "Texto e conversa")],
            )
        elif isinstance(item, dict):
            model_id = str(item.get("id") or item.get("model") or "").strip()
            if not model_id or model_id in seen:
                continue
            name = str(item.get("name") or model_id).strip()
            description = str(item.get("description") or "").strip()
            pricing = item.get("pricing") or {}
            in_usd = _parse_usd_per_million(pricing.get("prompt"))
            out_usd = _parse_usd_per_million(pricing.get("completion"))
            cache_read_usd = (
                _parse_usd_per_million(pricing.get("input_cache_read"))
                if pricing.get("input_cache_read") is not None
                else None
            )
            cache_write_usd = (
                _parse_usd_per_million(pricing.get("input_cache_write"))
                if pricing.get("input_cache_write") is not None
                else None
            )
            try:
                req_usd = max(0.0, float(pricing.get("request") or 0.0))
            except (TypeError, ValueError):
                req_usd = 0.0
            top_provider = item.get("top_provider") or {}
            raw_ctx = item.get("context_length") or top_provider.get("context_length") or 128_000
            try:
                ctx_len = max(2048, int(raw_ctx))
            except (TypeError, ValueError):
                ctx_len = 128_000
            arch = item.get("architecture") or {}
            in_mods = [str(x).lower() for x in (arch.get("input_modalities") or ["text"])]
            out_mods = [str(x).lower() for x in (arch.get("output_modalities") or ["text"])]
            sup_params = [str(x).lower() for x in (item.get("supported_parameters") or [])]
            is_free = (
                bool(item.get("isFree"))
                or model_id.endswith(":free")
                or (in_usd == 0.0 and out_usd == 0.0 and bool(pricing))
            )
            seen[model_id] = KiloModelInfo(
                id=model_id,
                name=name,
                description=description,
                is_free=is_free,
                power_tier=classify_power_tier(model_id, name, in_usd, out_usd, is_free),
                input_usd_per_m=0.0 if is_free else in_usd,
                output_usd_per_m=0.0 if is_free else out_usd,
                cache_read_usd_per_m=0.0 if is_free else cache_read_usd,
                cache_write_usd_per_m=0.0 if is_free else cache_write_usd,
                request_usd=0.0 if is_free else req_usd,
                context_length=ctx_len,
                input_modalities=in_mods or ["text"],
                output_modalities=out_mods or ["text"],
                supported_parameters=sup_params,
                capabilities=extract_capabilities(item),
            )
    return list(seen.values())


def fetch_kilo_catalog(
    api_key: str,
    *,
    transport: httpx.BaseTransport | None = None,
    fx_transport: httpx.BaseTransport | None = None,
) -> tuple[list[KiloModelInfo], float]:
    token = str(api_key or "").strip()
    if not token:
        raise ValueError("Informe a chave da API obtida em kilo.ai.")

    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=15.0, transport=transport, follow_redirects=True) as client:
        try:
            profile_resp = client.get(KILO_PROFILE_URL, headers=headers)
        except httpx.RequestError as exc:
            raise ValueError("Não foi possível conectar ao servidor oficial do Kilo (kilo.ai).") from exc

        if profile_resp.status_code in {401, 403}:
            raise ValueError("Chave da API do Kilo inválida ou expirada.")

        try:
            models_resp = client.get(KILO_MODELS_URL, headers=headers)
        except httpx.RequestError as exc:
            raise ValueError("Não foi possível conectar à API do Kilo Code Gateway.") from exc

        if models_resp.status_code in {401, 403}:
            raise ValueError("Chave da API do Kilo recusada pelo gateway.")
        if models_resp.status_code >= 400:
            raise ValueError(f"Kilo Code Gateway retornou erro HTTP {models_resp.status_code}.")
        try:
            payload = models_resp.json()
        except ValueError as exc:
            raise ValueError("Resposta inválida do Kilo Code Gateway.") from exc

    models = extract_models(payload)
    if not models:
        raise ValueError("Nenhum modelo de IA disponível retornado pelo Kilo Code.")
    usd_to_brl = fetch_usd_to_brl(transport=fx_transport)
    return models, usd_to_brl


def save_kilo_api_key(repository, api_key: str) -> None:
    token = str(api_key or "").strip()
    stored_in_keyring = False
    try:
        import keyring
        if token:
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_KILO_USER, token)
            stored_in_keyring = True
        else:
            try:
                keyring.delete_password(_KEYRING_SERVICE, _KEYRING_KILO_USER)
            except Exception:
                pass
    except Exception:
        stored_in_keyring = False
    repository.set_preference("kilo_has_key", bool(token))
    repository.set_preference("kilo_api_key_fallback", "" if stored_in_keyring else token)


def resolve_kilo_api_key(repository=None) -> str:
    for env_name in ("KILO_API_KEY", "KILO_GATEWAY_API_KEY", "GAMENEXT_KILO_API_KEY"):
        val = str(os.environ.get(env_name) or "").strip()
        if val:
            return val
    try:
        import keyring
        token = keyring.get_password(_KEYRING_SERVICE, _KEYRING_KILO_USER)
        if token and token.strip():
            return token.strip()
    except Exception:
        pass
    if repository is not None:
        return str(repository.preference("kilo_api_key_fallback", "") or "").strip()
    return ""


def load_kilo_models(repository) -> list[KiloModelInfo]:
    raw = repository.preference("kilo_models", [])
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if isinstance(item, dict) and item.get("id"):
            result.append(KiloModelInfo.from_dict(item))
    return result


def load_enabled_kilo_ids(repository) -> list[str]:
    raw = repository.preference("kilo_chat_models", [])
    if not isinstance(raw, list):
        return []
    return [str(mid).strip() for mid in raw if str(mid).strip()]


def save_kilo_catalog(
    repository,
    models: list[KiloModelInfo],
    usd_to_brl: float,
    enabled_ids: list[str] | None = None,
) -> list[str]:
    repository.set_preference("kilo_models", [m.to_dict() for m in models])
    rate = float(usd_to_brl) if 1.0 <= float(usd_to_brl or 0) <= 30.0 else DEFAULT_USD_TO_BRL
    repository.set_preference("kilo_usd_to_brl", rate)
    valid_ids = {m.id for m in models}
    if enabled_ids is None:
        current = [mid for mid in load_enabled_kilo_ids(repository) if mid in valid_ids]
        if not current and models:
            # Automatically include up to 3 free models (or the first model) so chat is ready immediately.
            free_defaults = [m.id for m in models if m.is_free][:3]
            current = free_defaults or [models[0].id]
    else:
        current = list(dict.fromkeys(mid for mid in enabled_ids if mid in valid_ids))
    repository.set_preference("kilo_chat_models", current)
    return current
