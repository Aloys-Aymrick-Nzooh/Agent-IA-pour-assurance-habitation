import math
import re
import uuid
from pathlib import Path
from typing import Any

import lancedb

from app.services.data_base_service.embeddings import EMBEDDING_DIMENSION


DOCUMENT_TYPE_DIRS = {
    "CG": "cg",
    "CP": "cp",
    "AVENANT": "avenant",
    "ANNEXE": "annexe",
}

TABLE_NAME = "chunks"


class VectorStoreError(Exception):
    """Raised when vector data cannot be stored."""


class VectorStore:
    def __init__(self, storage_path: str | Path) -> None:
        self.storage_path = Path(storage_path).resolve()

    def _get_database_path(
        self,
        conversation_id: str,
        document_type: str,
    ) -> Path:
        try:
            conversation_id = str(uuid.UUID(str(conversation_id)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Invalid conversation ID") from exc

        if document_type not in DOCUMENT_TYPE_DIRS:
            raise ValueError("Unsupported document type")

        type_dir = DOCUMENT_TYPE_DIRS[document_type]

        return (
            self.storage_path
            / "conversations"
            / conversation_id
            / "lancedb"
            / type_dir
        )

    def open_table(self, conversation_id: str, document_type: str):
        """Retourne la table LanceDB du couple (conversation, type), ou None."""
        path = self._get_database_path(conversation_id, document_type)

        # lancedb.connect() crée le dossier s'il n'existe pas : on teste avant.
        if not path.is_dir():
            return None

        try:
            return lancedb.connect(str(path)).open_table(TABLE_NAME)
        except Exception:
            return None

    def delete_document(
        self,
        conversation_id: str,
        document_type: str,
        document_id: str,
    ) -> None:
        """Supprime les vecteurs d'un document (nettoyage après un échec)."""
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", str(document_id)):
            raise ValueError("Invalid document ID")

        table = self.open_table(conversation_id, document_type)
        if table is not None:
            table.delete(f"document_id = '{document_id}'")

    def upsert_chunks(
        self,
        chunks: list[dict[str, Any]],
    ) -> int:
        """
        Store chunks in the LanceDB database for their conversation
        and document type.

        Each chunk must contain a document ID, page number, chunk
        index, text, and embedding.
        """
        if not chunks:
            return 0

        first = chunks[0]

        conversation_id = first.get("conversation_id")
        document_type = first.get("document_type")

        if not isinstance(conversation_id, str):
            raise ValueError("Invalid conversation ID")

        if document_type not in DOCUMENT_TYPE_DIRS:
            raise ValueError("Unsupported document type")

        rows = []

        for chunk in chunks:
            if (
                chunk.get("conversation_id") != conversation_id
                or chunk.get("document_type") != document_type
            ):
                raise ValueError(
                    "A batch must contain one conversation and document type"
                )

            document_id = chunk.get("document_id")
            page_number = chunk.get("page_number")
            chunk_index = chunk.get("chunk_index")
            chunk_text = chunk.get("chunk_text")
            embedding = chunk.get("embedding")

            if not isinstance(document_id, str) or not document_id:
                raise ValueError("Invalid document ID")

            if not isinstance(page_number, int) or page_number < 1:
                raise ValueError("Invalid page number")

            if not isinstance(chunk_index, int) or chunk_index < 0:
                raise ValueError("Invalid chunk index")

            if not isinstance(chunk_text, str) or not chunk_text.strip():
                raise ValueError("Chunk text must not be empty")

            if (
                not isinstance(embedding, list)
                or len(embedding) != EMBEDDING_DIMENSION
                or any(
                    not isinstance(value, (int, float)) or not math.isfinite(value)
                    for value in embedding
                )
            ):
                raise ValueError("Invalid embedding vector")

            chunk_id = f"{document_id}:{page_number}:{chunk_index}"

            rows.append({
                "chunk_id": chunk_id,
                "conversation_id": conversation_id,
                "document_id": document_id,
                "document_name": chunk["document_name"],
                "document_type": document_type,
                "chapter": chunk.get("chapter") or "",
                "page_number": page_number,
                # Chaîne et non liste : une liste vide partout fait inférer
                # list<null> à PyArrow et casse l'écriture LanceDB.
                "titles": " > ".join(chunk.get("titles") or []),
                "chunk_index": chunk_index,
                "chunk_text": chunk_text,
                "embedding_text": chunk.get("embedding_text", chunk_text),
                "vector": embedding,
            })

        database_path = self._get_database_path(
            conversation_id,
            document_type,
        )

        database_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            database = lancedb.connect(str(database_path))

            if TABLE_NAME in database.table_names():
                table = database.open_table(TABLE_NAME)

                # Remove previous vectors for these documents so
                # re-ingestion does not leave obsolete chunks behind.
                document_ids = sorted({row["document_id"] for row in rows})

                for document_id in document_ids:
                    if not re.fullmatch(r"[0-9a-fA-F-]{36}", document_id):
                        raise ValueError("Invalid document ID")

                    table.delete(f"document_id = '{document_id}'")

                table.add(rows)
            else:
                database.create_table(
                    TABLE_NAME,
                    data=rows,
                )

        except ValueError:
            raise
        except Exception as exc:
            raise VectorStoreError(
                "Unable to write chunks to LanceDB"
            ) from exc

        return len(rows)