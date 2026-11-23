"""Document extraction, never executing embedded document content."""
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


TEXT_EXTENSIONS = {
    ".txt", ".md", ".json", ".csv", ".tsv", ".py", ".gd", ".godot", ".tscn", ".tres",
    ".ini", ".toml", ".yaml", ".yml", ".log", ".html", ".htm", ".xml", ".svg", ".rst",
    ".cfg", ".cs", ".js", ".jsx", ".ts", ".tsx", ".css", ".scss", ".sql", ".sh",
    ".bat", ".ps1", ".c", ".cpp", ".h", ".hpp", ".java", ".rs", ".go", ".php", ".rb", ".lua",
}


def read_document(path: Path, limit=24000) -> str:
    if not path.is_file():
        raise ValueError("Arquivo não encontrado")
    if path.stat().st_size > 250 * 1024 * 1024:
        raise ValueError("Documento excede 250 MB")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        chunks = []
        for index, page in enumerate(reader.pages):
            chunks.append(f"Página {index + 1}:\n" + (page.extract_text() or "[sem texto extraível; pode exigir OCR]"))
            if sum(map(len, chunks)) >= limit:
                break
        text = "\n".join(chunks)
    elif suffix == ".docx":
        from docx import Document
        document = Document(path)
        text = "\n".join(
            [p.text for p in document.paragraphs]
            + [" | ".join(cell.text for cell in row.cells) for table in document.tables for row in table.rows]
        )
    elif suffix in {".pptx", ".xlsx", ".odt", ".ods"}:
        with zipfile.ZipFile(path) as archive:
            chunks = []
            for item in archive.infolist():
                if item.file_size > 16_000_000:
                    continue
                relevant = (
                    item.filename.startswith("ppt/slides/slide")
                    or item.filename == "xl/sharedStrings.xml"
                    or item.filename.startswith("xl/worksheets/sheet")
                    or item.filename == "content.xml"
                ) and item.filename.endswith(".xml")
                if relevant:
                    root = ET.fromstring(archive.read(item))
                    chunks.append(" ".join(node.text for node in root.iter() if node.text and node.text.strip()))
                    if sum(map(len, chunks)) >= limit:
                        break
            text = "\n".join(chunks)
    elif suffix in TEXT_EXTENSIONS:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            text = stream.read(limit + 1)
    else:
        raise ValueError("Formato não suportado para leitura direta de texto.")
    return text[:limit] + ("\n[conteúdo truncado pelo limite de leitura]" if len(text) > limit else "")
