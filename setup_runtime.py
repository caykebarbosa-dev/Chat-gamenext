"""Download the default llama.cpp runtime and starter GGUF model on Windows."""
from __future__ import annotations

import json
import os
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "runtime" / "llama-vulkan"
MODEL = ROOT / "Qwen3.5-4B-Q3_K_S.gguf"
MODEL_URL = (
    "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/"
    "Qwen3.5-4B-Q3_K_S.gguf"
)
WHISPER_DIR = ROOT / "runtime" / "whisper-tiny"
WHISPER_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
WHISPER_BASE_URL = "https://huggingface.co/Systran/faster-whisper-tiny/resolve/main/"
RELEASES_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "GameNext-setup"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as out:
            total = int(response.headers.get("Content-Length", "0"))
            received = 0
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
                received += len(chunk)
                if total:
                    print(f"\r  {received / total:.0%} ({received / 1e9:.2f}/{total / 1e9:.2f} GB)", end="", flush=True)
        temporary.replace(destination)
        print()
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def install_runtime() -> None:
    server = RUNTIME_DIR / "llama-server.exe"
    if server.is_file():
        print("Runtime llama.cpp já existe.")
        return
    request = urllib.request.Request(RELEASES_API, headers={"User-Agent": "GameNext-setup"})
    with urllib.request.urlopen(request, timeout=30) as response:
        release = json.load(response)
    asset = next(
        (a for a in release.get("assets", []) if "win-vulkan-x64.zip" in a["name"].lower()),
        None,
    )
    if not asset:
        raise RuntimeError("Não encontrei o pacote Windows x64 Vulkan no release do llama.cpp.")
    archive = ROOT / "runtime" / asset["name"]
    print(f"Baixando runtime llama.cpp {release.get('tag_name', '')}...")
    download(asset["browser_download_url"], archive)
    temp_dir = ROOT / "runtime" / "_llama_extract"
    shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True)
    try:
        with zipfile.ZipFile(archive) as bundle:
            base = temp_dir.resolve()
            for member in bundle.infolist():
                target = (temp_dir / member.filename).resolve()
                if target != base and base not in target.parents:
                    raise RuntimeError("O pacote contém um caminho de arquivo inválido.")
            bundle.extractall(temp_dir)
        found = next(temp_dir.rglob("llama-server.exe"), None)
        if not found:
            raise RuntimeError("O pacote baixado não contém llama-server.exe.")
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        for item in found.parent.iterdir():
            destination = RUNTIME_DIR / item.name
            if item.is_dir():
                shutil.copytree(item, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(item, destination)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        archive.unlink(missing_ok=True)


def install_model() -> None:
    if MODEL.is_file() and MODEL.stat().st_size > 1_000_000_000:
        print("Modelo Qwen3.5-4B já existe.")
        return
    print("Baixando modelo Qwen3.5-4B Q3_K_S (~2,1 GB)...")
    download(MODEL_URL, MODEL)


def install_whisper() -> None:
    if all((WHISPER_DIR / name).is_file() for name in WHISPER_FILES):
        print("Modelo de voz Whisper Tiny já existe.")
        return
    print("Baixando modelo de voz Whisper Tiny (~75 MB)...")
    for name in WHISPER_FILES:
        target = WHISPER_DIR / name
        if not target.is_file():
            download(WHISPER_BASE_URL + name, target)


def main() -> int:
    if os.name != "nt":
        print("Este instalador automático foi preparado para Windows.", file=sys.stderr)
        return 1
    try:
        install_runtime()
        install_model()
        install_whisper()
    except Exception as error:
        print(f"\nFalha na preparação: {error}", file=sys.stderr)
        print("Confira a conexão e o espaço livre e execute o BAT novamente.", file=sys.stderr)
        return 1
    print("Runtime e modelo prontos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
