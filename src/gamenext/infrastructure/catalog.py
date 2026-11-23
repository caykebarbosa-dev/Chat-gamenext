"""GGUF discovery and bounded metadata parsing, without loading model weights."""
import os
import struct
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal


def read_metadata(path: Path) -> dict:
    with path.open("rb") as stream:
        def unpack(fmt):
            size = struct.calcsize(fmt)
            data = stream.read(size)
            if len(data) != size:
                raise ValueError("GGUF incompleto")
            return struct.unpack(fmt, data)[0]

        def string(keep=True):
            size = unpack("<Q")
            if size > 32_000_000:
                raise ValueError("Metadado GGUF excessivo")
            if keep:
                return stream.read(size).decode("utf-8", errors="replace")
            stream.seek(size, 1)

        sizes = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}

        def value(kind, keep=True, depth=0):
            if depth > 4:
                raise ValueError("Metadado GGUF aninhado excessivo")
            if kind == 8:
                return string(keep)
            if kind == 9:
                item_type, count = unpack("<I"), unpack("<Q")
                if count > 2_000_000:
                    raise ValueError("Array GGUF excessivo")
                if item_type in sizes:
                    stream.seek(struct.calcsize(sizes[item_type]) * count, 1)
                else:
                    for _ in range(count):
                        value(item_type, False, depth + 1)
                return None
            if kind not in sizes:
                raise ValueError("Tipo GGUF desconhecido")
            return unpack(sizes[kind])

        if stream.read(4) != b"GGUF" or unpack("<I") not in (2, 3):
            raise ValueError("Arquivo GGUF inválido ou versão não suportada")
        tensors, count = unpack("<Q"), unpack("<Q")
        if count > 100_000 or tensors > 1_000_000:
            raise ValueError("Cabeçalho GGUF excessivo")
        metadata = {}
        for _ in range(count):
            key = string()
            keep = key.startswith("general.") or key.endswith((".block_count", ".context_length"))
            result = value(unpack("<I"), keep)
            if keep and result is not None:
                metadata[key] = result
        return metadata


class CatalogScanner(QThread):
    found = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, folder: str, parent=None):
        super().__init__(parent)
        self.folder = folder

    def run(self):
        try:
            root = Path(self.folder)
            if not root.is_dir():
                raise ValueError("Escolha uma pasta existente")
            models = []
            scanned = 0
            for current, dirs, files in os.walk(root, followlinks=False):
                dirs[:] = [d for d in dirs if d not in {".git", ".venv", "node_modules", "runtime"} and not (Path(current) / d).is_symlink()]
                for filename in files:
                    scanned += 1
                    if scanned > 100_000 or self.isInterruptionRequested():
                        break
                    path = Path(current) / filename
                    if path.suffix.lower() != ".gguf" or "mmproj" in filename.lower():
                        continue
                    try:
                        meta = read_metadata(path)
                        models.append({"path": str(path.resolve()), "name": filename, "bytes": path.stat().st_size, "metadata": meta})
                    except (OSError, ValueError, struct.error) as error:
                        models.append({"path": str(path), "name": filename, "error": str(error)})
                if scanned > 100_000 or self.isInterruptionRequested():
                    break
            self.found.emit(models)
        except (OSError, ValueError) as error:
            self.failed.emit(str(error))
