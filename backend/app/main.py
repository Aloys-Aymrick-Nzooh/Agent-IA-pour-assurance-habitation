
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
    # 1. Vérifier que la conversation existe

    conversation = db.get(
        Conversation,
        conversation_id,
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    # 2. Vérifier le nom et le format du fichier

    filename = Path(
        file.filename or ""
    ).name

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported",
        )

    # 3. Lire le fichier avec une limite de taille

    content = file.file.read(
        MAX_UPLOAD_SIZE + 1
    )

    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File too large",
        )

    # 4. Générer un identifiant de document

    document_id = uuid.uuid4()

    # 5. Stocker le fichier dans le dossier
    # correspondant à la conversation

    conversation_dir = (
        STORAGE_PATH / str(conversation_id)
    )

    conversation_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_path = (
        conversation_dir
        / f"{document_id}.pdf"
    )

    # 6. Extraire le texte des pages du PDF

    try:
        pdf = fitz.open(
            stream=content,
            filetype="pdf",
        )

        if pdf.is_encrypted:
            raise HTTPException(
                status_code=400,
                detail="Encrypted PDFs are not supported",
            )

        if len(pdf) == 0:
            raise HTTPException(
                status_code=400,
                detail="Empty PDF",
            )

        if len(pdf) > 500:
            raise HTTPException(
                status_code=400,
                detail="PDF exceeds the page limit",
            )

        extracted_pages = []

        for page_index, page in enumerate(pdf):
            page_text = page.get_text("text").strip()

            extracted_pages.append({
                "page_number": page_index + 1,
                "text": page_text,
            })

        pdf.close()

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Unable to read the PDF",
        )

    # 7. Enregistrer le fichier original

    file_path.write_bytes(content)

    # 8. Créer le document dans la base

    document = Document(
        id=document_id,
        conversation_id=conversation_id,
        filename=filename,
        document_type=document_type,
        file_path=str(file_path),
        processing_status="completed",
        page_count=len(extracted_pages),
    )

    db.add(document)

    # 9. Enregistrer le texte extrait page par page

    for page_data in extracted_pages:
        page = DocumentPage(
            conversation_id=conversation_id,
            document_id=document_id,
            page_number=page_data["page_number"],
            text=page_data["text"],
        )

        db.add(page)

    db.commit()

    return {
        "conversation_id": str(conversation_id),
        "document_id": str(document_id),
        "filename": filename,
        "document_type": document_type,
        "page_count": len(extracted_pages),
        "processing_status": "completed",
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
