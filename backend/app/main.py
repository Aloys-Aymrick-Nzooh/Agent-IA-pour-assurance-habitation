
import json
import os
import uuid

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import fitz

from dotenv import load_dotenv

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
)

from app.services.document_ingestion import (
    DocumentIngestionError,
    extract_document_pages,
    save_document_json,
)

from app.services.chunking import chunk_document_pages, load_document_pages
from app.services.embeddings import EmbeddingService
from app.services.vector_store import VectorStore, VectorStoreError

load_dotenv()

STORAGE_PATH = Path(
    os.getenv("STORAGE_PATH", "./storage")
).resolve()

embedding_service = EmbeddingService()
vector_store = VectorStore(STORAGE_PATH)

CONVERSATIONS_PATH = STORAGE_PATH / "conversations"

MAX_UPLOAD_SIZE = (
    int(os.getenv("MAX_UPLOAD_SIZE_MB", "30"))
    * 1024
    * 1024
)

MAX_PDF_PAGES = 500

DOCUMENT_TYPE_DIRS = {
    "CG": "cg",
    "CP": "cp",
    "AVENANT": "avenant",
    "ANNEXE": "annexe",
}

CONVERSATIONS_PATH.mkdir(
    parents=True,
    exist_ok=True,
)

app = FastAPI(
    title="Insurance Claims AI",
    description="Contractual document analysis API",
    version="0.1.0",
)


def _get_conversation_dir(
    conversation_id: uuid.UUID,
) -> Path:
    """Return the directory of an existing conversation."""

    conversation_dir = (
        CONVERSATIONS_PATH / str(conversation_id)
    )

    metadata_path = conversation_dir / "conversation.json"

    if not metadata_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    try:
        metadata = json.loads(
            metadata_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to read conversation metadata",
        ) from exc

    if (
        not isinstance(metadata, dict)
        or metadata.get("conversation_id") != str(conversation_id)
    ):
        raise HTTPException(
            status_code=500,
            detail="Invalid conversation metadata",
        )

    return conversation_dir


def _load_document_json(
    json_path: Path,
) -> dict:
    """Read and validate a document JSON file."""

    try:
        payload = json.loads(
            json_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to read document data",
        ) from exc

    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("pages"), list)
    ):
        raise HTTPException(
            status_code=500,
            detail="Invalid document JSON structure",
        )

    return payload


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "insurance-claims-ai",
    }


@app.post("/conversations")
def create_conversation():
    """Create a conversation isolated on the filesystem."""

    conversation_id = uuid.uuid4()
    created_at = datetime.now(timezone.utc)

    conversation_dir = (
        CONVERSATIONS_PATH / str(conversation_id)
    )

    conversation_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    metadata = {
        "conversation_id": str(conversation_id),
        "created_at": created_at.isoformat(),
    }

    metadata_path = conversation_dir / "conversation.json"

    try:
        metadata_path.write_text(
            json.dumps(
                metadata,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        # Avoid leaving behind an incomplete conversation.
        try:
            metadata_path.unlink(missing_ok=True)
            conversation_dir.rmdir()
        except OSError:
            pass

        raise HTTPException(
            status_code=500,
            detail="Unable to create conversation",
        ) from exc

    return metadata


@app.post("/conversations/{conversation_id}/documents")
def upload_document(
    conversation_id: uuid.UUID,
    document_type: Literal[
        "CG",
        "CP",
        "AVENANT",
        "ANNEXE",
    ] = Form(...),
    file: UploadFile = File(...),
):
    """Store the original PDF and its extracted Markdown pages."""

    conversation_dir = _get_conversation_dir(
        conversation_id
    )

    filename = Path(file.filename or "").name

    if not filename or not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported",
        )

    try:
        content = file.file.read(MAX_UPLOAD_SIZE + 1)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Unable to read uploaded file",
        ) from exc

    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File too large",
        )

    # Validate the PDF before creating any document files.
    try:
        with fitz.open(
            stream=content,
            filetype="pdf",
        ) as pdf:
            if pdf.is_encrypted:
                raise HTTPException(
                    status_code=400,
                    detail="Encrypted PDFs are not supported",
                )

            page_count = len(pdf)

            if page_count == 0:
                raise HTTPException(
                    status_code=400,
                    detail="Empty PDF",
                )

            if page_count > MAX_PDF_PAGES:
                raise HTTPException(
                    status_code=400,
                    detail="PDF exceeds the page limit",
                )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Unable to read the PDF",
        ) from exc

    document_id = uuid.uuid4()

    type_dir = DOCUMENT_TYPE_DIRS[document_type]

    document_dir = (
        conversation_dir / "documents" / type_dir
    )

    document_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    pdf_path = document_dir / f"{document_id}.pdf"
    json_path = document_dir / f"{document_id}.json"

    try:
        # 1. Preserve the original PDF.
        pdf_path.write_bytes(content)

        # 2. Extract structured Markdown page by page.
        extracted_pages = extract_document_pages(
            pdf_path,
            conversation_id=conversation_id,
            document_id=document_id,
            document_name=filename,
            document_type=document_type,
        )

        if len(extracted_pages) != page_count:
            raise DocumentIngestionError(
                "The extracted page count does not match the PDF"
            )

        # 3. Save the authoritative page-level JSON.
        save_document_json(
            extracted_pages,
            json_path,
        )

        # 1. Recharger les pages depuis le JSON enregistré.
        pages = load_document_pages(json_path)

        # 2. Découper les pages en chunks.
        chunks = chunk_document_pages(pages)

        # 3. Calculer les embeddings des chunks.
        embedded_chunks = embedding_service.embed_chunks(chunks)

        # 4. Enregistrer les chunks et leurs vecteurs dans LanceDB.
        stored_count = vector_store.upsert_chunks(embedded_chunks)

        # 5. Vérifier que tous les chunks ont été indexés.
        if stored_count != len(embedded_chunks):
            raise VectorStoreError(
                f"Indexation incomplète : {stored_count}/{len(embedded_chunks)} chunks enregistrés."
            )

    except DocumentIngestionError as exc:
        pdf_path.unlink(missing_ok=True)
        json_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        pdf_path.unlink(missing_ok=True)
        json_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=500,
            detail="Unable to process and store the document",
        ) from exc

    return {
        "conversation_id": str(conversation_id),
        "document_id": str(document_id),
        "filename": filename,
        "document_type": document_type,
        "page_count": page_count,
        "processing_status": "completed",
        "json_path": str(json_path),
    }


@app.get("/conversations/{conversation_id}/documents")
def get_documents(
    conversation_id: uuid.UUID,
):
    """List all documents stored in a conversation."""

    conversation_dir = _get_conversation_dir(
        conversation_id
    )

    documents_dir = conversation_dir / "documents"
    documents = []

    for document_type, type_dir in DOCUMENT_TYPE_DIRS.items():
        type_path = documents_dir / type_dir

        if not type_path.is_dir():
            continue

        for json_path in sorted(type_path.glob("*.json")):
            payload = _load_document_json(json_path)
            pages = payload["pages"]

            if not pages:
                raise HTTPException(
                    status_code=500,
                    detail="Document JSON contains no pages",
                )

            first_page = pages[0]

            if not isinstance(first_page, dict):
                raise HTTPException(
                    status_code=500,
                    detail="Invalid document page metadata",
                )

            try:
                document_id = uuid.UUID(
                    str(first_page["document_id"])
                )
            except (KeyError, ValueError, TypeError) as exc:
                raise HTTPException(
                    status_code=500,
                    detail="Invalid document identifier",
                ) from exc

            if (
                first_page.get("conversation_id")
                != str(conversation_id)
                or first_page.get("document_type")
                != document_type
            ):
                raise HTTPException(
                    status_code=500,
                    detail="Document metadata does not match its location",
                )

            documents.append({
                "document_id": str(document_id),
                "filename": first_page.get("document_name"),
                "document_type": document_type,
                "page_count": len(pages),
                "processing_status": "completed",
            })

    return documents


@app.get(
    "/conversations/{conversation_id}/documents/"
    "{document_id}/pages/{page_number}"
)
def get_document_page(
    conversation_id: uuid.UUID,
    document_id: uuid.UUID,
    page_number: int,
):
    """Retrieve the original Markdown content of one page."""

    conversation_dir = _get_conversation_dir(
        conversation_id
    )

    if page_number < 1:
        raise HTTPException(
            status_code=404,
            detail="Page not found",
        )

    documents_dir = conversation_dir / "documents"

    # Search all supported document types. This avoids requiring
    # the caller to know the document's type.
    for type_dir in DOCUMENT_TYPE_DIRS.values():
        json_path = (
            documents_dir
            / type_dir
            / f"{document_id}.json"
        )

        if not json_path.is_file():
            continue

        payload = _load_document_json(json_path)

        for page in payload["pages"]:
            if not isinstance(page, dict):
                raise HTTPException(
                    status_code=500,
                    detail="Invalid document page structure",
                )

            if (
                page.get("conversation_id")
                != str(conversation_id)
                or page.get("document_id")
                != str(document_id)
            ):
                raise HTTPException(
                    status_code=500,
                    detail="Document page metadata does not match its source",
                )

            if page.get("page_number") == page_number:
                return {
                    "document_id": str(document_id),
                    "page_number": page_number,
                    "text": page.get("page_content", ""),
                }

        raise HTTPException(
            status_code=404,
            detail="Page not found",
        )

    raise HTTPException(
        status_code=404,
        detail="Document not found",
    )
