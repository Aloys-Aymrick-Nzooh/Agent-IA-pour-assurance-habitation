
import json
import re

from pathlib import Path
from typing import Any


DEFAULT_MAX_CHARS = 1800
DEFAULT_OVERLAP_CHARS = 200


def load_document_pages(json_path: str | Path) -> list[dict[str, Any]]:
    """Load and validate page records from an ingestion JSON file."""
    path = Path(json_path)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Unable to read the document JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("Invalid document JSON structure")

    pages = payload.get("pages")

    if not isinstance(pages, list):
        raise ValueError("Document JSON must contain a pages list")

    required_fields = {
        "conversation_id",
        "document_id",
        "document_name",
        "chapter",
        "page_number",
        "titles",
        "page_content",
    }

    for page in pages:
        if not isinstance(page, dict):
            raise ValueError("Each page must be a JSON object")

        if not required_fields.issubset(page):
            raise ValueError("A page is missing required metadata")

        if not isinstance(page["page_content"], str):
            raise ValueError("Page content must be a string")

        if not isinstance(page["titles"], list):
            raise ValueError("Page titles must be a list")

        if not isinstance(page["page_number"], int) or page["page_number"] < 1:
            raise ValueError("Page number must be a positive integer")

    return pages


def _split_long_text(text: str, max_chars: int) -> list[str]:
    """Split oversized text by sentences, then by character windows."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())

    parts: list[str] = []
    current = ""

    for sentence in sentences:
        if len(sentence) <= max_chars:
            candidate = f"{current} {sentence}".strip()

            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    parts.append(current)

                current = sentence

            continue

        if current:
            parts.append(current)
            current = ""

        # Last resort for a sentence longer than the chunk limit.
        start = 0

        while start < len(sentence):
            parts.append(sentence[start : start + max_chars])
            start += max_chars

    if current:
        parts.append(current)

    return parts


def _split_page_content(
    page_content: str,
    max_chars: int,
    overlap_chars: int,
) -> list[str]:
    """Split Markdown while preferring paragraph and sentence boundaries."""
    content = page_content.strip()

    if not content:
        return []

    # Markdown paragraphs are generally separated by one or more blank lines.
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", content)
        if paragraph.strip()
    ]

    units: list[str] = []

    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            units.append(paragraph)
        else:
            units.extend(_split_long_text(paragraph, max_chars))

    chunks: list[str] = []
    current = ""

    for unit in units:
        candidate = f"{current}\n\n{unit}".strip()

        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)

        # Preserve a small amount of context across chunk boundaries.
        overlap = ""

        if chunks and overlap_chars:
            overlap = chunks[-1][-overlap_chars:].strip()

        if overlap:
            candidate = f"{overlap}\n\n{unit}".strip()
        else:
            candidate = unit

        if len(candidate) <= max_chars:
            current = candidate
        else:
            # The unit itself is already within max_chars.
            # Drop the overlap rather than exceed the chunk limit.
            current = unit

    if current:
        chunks.append(current)

    return chunks


def chunk_document_pages(
    pages: list[dict[str, Any]],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[dict[str, Any]]:
    """
    Split page-level Markdown into searchable chunks.

    Each chunk retains the source page and conversation metadata.
    Chunk indexes restart at zero for each page.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be positive")

    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError(
            "overlap_chars must be non-negative and smaller than max_chars"
        )

    chunks: list[dict[str, Any]] = []

    for page in pages:
        page_content = page.get("page_content")

        if not isinstance(page_content, str):
            raise ValueError("Page content must be a string")

        page_chunks = _split_page_content(
            page_content,
            max_chars,
            overlap_chars,
        )

        # Keep compatibility with older JSON files that do not have
        # document_type. New ingestion records provide this field.
        document_type = page.get(
            "document_type",
            page["document_name"],
        )

        for chunk_index, chunk_text in enumerate(page_chunks):
            chunks.append({
                "conversation_id": page["conversation_id"],
                "document_id": page["document_id"],
                "document_name": page["document_name"],
                "document_type": document_type,
                "chapter": page["chapter"],
                "page_number": page["page_number"],
                "titles": list(page["titles"]),
                "chunk_index": chunk_index,
                "chunk_text": chunk_text,
            })

    return chunks
