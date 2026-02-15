from pathlib import Path

from docx import Document
from pypdf import PdfReader


def extract_text(path: str) -> str:
    file_path = Path(path)
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if suffix == ".docx":
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs)

    return file_path.read_text(encoding="utf-8", errors="ignore")
