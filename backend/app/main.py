
import os
import uuid

from pathlib import Path
from typing import Literal

import fitz

from dotenv import load_dotenv

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    UploadFile,
    File,
)

from sqlalchemy.orm import Session

from app.database import get_db, init_db
from app.models import Conversation, Document, DocumentPage

from app.services.document_ingestion import (
    DocumentIngestionError,
    extract_document_pages,
    save_document_json,
)

load_dotenv()

STORAGE_PATH = Path(
    os.getenv("STORAGE_PATH", "./storage")
).resolve()

MAX_UPLOAD_SIZE = (
    int(os.getenv("MAX_UPLOAD_SIZE_MB", "30"))
    * 1024 * 1024
)

STORAGE_PATH.mkdir(
    parents=True,
    exist_ok=True,
)

app = FastAPI(
    title="Insurance Claims AI",
    description="Contractual document analysis API",
    version="0.1.0",
)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "insurance-claims-ai",
    }


@app.post("/conversations")
def create_conversation(
    db: Session = Depends(get_db),
):
    conversation = Conversation()

    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return {
        "conversation_id": str(conversation.id),
        "created_at": conversation.created_at,
    }



@app.post("/conversations/{conversation_id}/documents")
def upload_document(
    conversation_id: uuid.UUID,
    document_type: Literal[
        "CG",
        "CP",
        "AVENANT",
        "ANNEXE",
    ],
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    conversation = db.get(Conversation, conversation_id)

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    filename = Path(file.filename or "").name

    if not filename or not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported",
        )

    content = file.file.read(MAX_UPLOAD_SIZE + 1)

    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File too large",
        )

    # Valider le PDF avant de créer des fichiers ou des enregistrements.
    try:
        with fitz.open(stream=content, filetype="pdf") as pdf:
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

            if page_count > 500:
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

    # Tous les fichiers restent isolés dans le dossier de la conversation.
    conversation_dir = STORAGE_PATH / str(conversation_id)
    conversation_dir.mkdir(parents=True, exist_ok=True)

    file_path = conversation_dir / f"{document_id}.pdf"
    json_path = conversation_dir / f"{document_id}.json"

    try:
        # 1. Sauvegarder le PDF original.
        file_path.write_bytes(content)

        # 2. Extraire le contenu structuré page par page en Markdown.
        extracted_pages = extract_document_pages(
            file_path,
            conversation_id=conversation_id,
            document_id=document_id,
            document_name=document_type,
        )

        if len(extracted_pages) != page_count:
            raise DocumentIngestionError(
                "The extracted page count does not match the PDF"
            )

        # 3. Persister le JSON de référence du document.
        save_document_json(
            extracted_pages,
            json_path,
        )

        # 4. Créer l'enregistrement du document.
        document = Document(
            id=document_id,
            conversation_id=conversation_id,
            filename=filename,
            document_type=document_type,
            file_path=str(file_path),
            processing_status="completed",
            page_count=page_count,
        )

        db.add(document)

        # 5. Enregistrer chaque page Markdown dans PostgreSQL.
        for page_data in extracted_pages:
            db.add(
                DocumentPage(
                    conversation_id=conversation_id,
                    document_id=document_id,
                    page_number=page_data["page_number"],
                    text=page_data["page_content"],
                )
            )

        # Valider tous les enregistrements dans une transaction.
        db.commit()

    except DocumentIngestionError as exc:
        db.rollback()
        file_path.unlink(missing_ok=True)
        json_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        db.rollback()
        file_path.unlink(missing_ok=True)
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
    db: Session = Depends(get_db),
):
    conversation = db.get(
        Conversation,
        conversation_id,
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    return [
        {
            "document_id": str(document.id),
            "filename": document.filename,
            "document_type": document.document_type,
            "page_count": document.page_count,
            "processing_status": document.processing_status,
        }
        for document in conversation.documents
    ]


@app.get(
    "/conversations/{conversation_id}/documents/"
    "{document_id}/pages/{page_number}"
)
def get_document_page(
    conversation_id: uuid.UUID,
    document_id: uuid.UUID,
    page_number: int,
    db: Session = Depends(get_db),
):
    page = (
        db.query(DocumentPage)
        .filter(
            DocumentPage.conversation_id == conversation_id,
            DocumentPage.document_id == document_id,
            DocumentPage.page_number == page_number,
        )
        .first()
    )

    if page is None:
        raise HTTPException(
            status_code=404,
            detail="Page not found",
        )

    return {
        "document_id": str(document_id),
        "page_number": page.page_number,
        "text": page.text,
    }
