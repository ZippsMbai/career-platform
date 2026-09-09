import io

from fastapi import HTTPException
from pypdf import PdfReader
from docx import Document


def extract_text_from_upload(filename: str, content: bytes) -> str:
    """Pull plain text out of an uploaded resume file. Supports PDF, DOCX, and
    plain text — anything else is rejected with a clear error rather than
    silently producing garbage text that would poison downstream analysis."""
    name_lower = filename.lower()

    if name_lower.endswith(".pdf"):
        try:
            reader = PdfReader(io.BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not read PDF: {e}")

    elif name_lower.endswith(".docx"):
        try:
            doc = Document(io.BytesIO(content))
            text = "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not read DOCX: {e}")

    elif name_lower.endswith(".txt"):
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Could not decode .txt file as UTF-8.")

    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type — please upload a .pdf, .docx, or .txt file.",
        )

    text = text.strip()
    if not text:
        raise HTTPException(
            status_code=400,
            detail="No extractable text found in this file — it may be a scanned image without a text layer.",
        )
    return text