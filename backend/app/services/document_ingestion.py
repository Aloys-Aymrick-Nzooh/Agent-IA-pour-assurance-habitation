
import re
import uuid

from pathlib import Path
from typing import Any

import pymupdf4llm


class DocumentIngestionError(Exception):
    """Raised when a PDF cannot be converted into structured pages."""


def _extract_titles(page_content: str) -> list[str]:
    """Extract Markdown headings in their original order."""
    titles = []

    for line in page_content.splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)

        if match:
            title = match.group(1).strip()

            if title:
                titles.append(title)

    return titles


def _extract_chapter(titles: list[str]) -> str | None:
    """Return the most relevant chapter heading available on the page."""
    for title in titles:
        if re.match(
            r"^(chapitre|chapter|partie|titre|section)\b",
            title,
            flags=re.IGNORECASE,
        ):
            return title

    return None


def _clean_page_content(page_content: str) -> str:
    """
    Apply conservative Markdown cleanup.

    Contractual content is preserved by default. Table-of-contents
    removal must be handled explicitly after validating the PDF format.
    """
    content = page_content.replace("\x00", "")
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    # Remove excessive blank lines without changing Markdown structure.
    content = re.sub(r"\n{3,}", "\n\n", content)

    return content.strip()


def extract_document_pages(
    pdf_path: str | Path,
    *,
    conversation_id: uuid.UUID | str,
    document_id: uuid.UUID | str,
    document_name: str,
    document_type: str,
) -> list[dict[str, Any]]:
    """
    Extract a PDF into page-level Markdown records.

    Each record preserves the original page content and its metadata,
    including the document type and conversation/document identifiers.
    """
    if not isinstance(document_type, str) or not document_type.strip():
        raise DocumentIngestionError("Document type must not be empty")

    path = Path(pdf_path)

    if not path.is_file():
        raise DocumentIngestionError("PDF file not found")

    try:
        pages = pymupdf4llm.to_markdown(
            str(path),
            page_chunks=True,
        )
    except Exception as exc:
        raise DocumentIngestionError(
            "Unable to extract Markdown from PDF"
        ) from exc

    if not pages:
        raise DocumentIngestionError("PDF contains no extractable pages")

    structured_pages = []

    for index, page_data in enumerate(pages, start=1):
        if not isinstance(page_data, dict):
            raise DocumentIngestionError(
                "Unexpected page structure returned by pymupdf4llm"
            )

        raw_content = page_data.get("text", "")

        if not isinstance(raw_content, str):
            raise DocumentIngestionError(
                "Unexpected page content returned by pymupdf4llm"
            )

        content = _clean_page_content(raw_content)
        titles = _extract_titles(content)

        structured_pages.append({
            "conversation_id": str(conversation_id),
            "document_id": str(document_id),
            "document_name": document_name,
            "document_type": document_type.strip(),
            "chapter": _extract_chapter(titles),
            "page_number": index,
            "titles": titles,
            "page_content": content,
        })

    return structured_pages


def save_document_json(
    pages: list[dict[str, Any]],
    json_path: str | Path,
) -> Path:
    """Persist the structured page records as a UTF-8 JSON file."""
    import json

    destination = Path(json_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = destination.with_suffix(
        destination.suffix + ".tmp"
    )

    try:
        temporary_path.write_text(
            json.dumps(
                {"pages": pages},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary_path.replace(destination)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    return destination
