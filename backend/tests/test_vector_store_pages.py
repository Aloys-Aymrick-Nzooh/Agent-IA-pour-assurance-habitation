import json
import tempfile
import unittest
import uuid
from pathlib import Path

from app.services.data_base_service.vector_store import VectorStore


class VectorStorePagesTest(unittest.TestCase):
    def test_loads_deduplicated_full_pages_from_document_json(self):
        conversation_id = str(uuid.uuid4())
        document_id = str(uuid.uuid4())
        pages = [
            {
                "conversation_id": conversation_id,
                "document_id": document_id,
                "document_name": "CP.pdf",
                "document_type": "CP",
                "chapter": "Garanties",
                "page_number": 4,
                "titles": ["Plafonds"],
                "page_content": "Chunk pertinent. Contexte complet de la page 4.",
            },
            {
                "conversation_id": conversation_id,
                "document_id": document_id,
                "document_name": "CP.pdf",
                "document_type": "CP",
                "chapter": "Garanties",
                "page_number": 5,
                "titles": ["Franchises"],
                "page_content": "Contenu intégral de la page 5.",
            },
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            json_path = (
                Path(temporary_directory)
                / "conversations"
                / conversation_id
                / "documents"
                / "cp"
                / f"{document_id}.json"
            )
            json_path.parent.mkdir(parents=True)
            json_path.write_text(
                json.dumps({"pages": pages}, ensure_ascii=False),
                encoding="utf-8",
            )

            retrieved = VectorStore(temporary_directory).get_pages(
                conversation_id,
                [
                    {"document_id": document_id, "document_type": "CP", "page_number": 4},
                    {"document_id": document_id, "document_type": "CP", "page_number": 4},
                    {"document_id": document_id, "document_type": "CP", "page_number": 5},
                ],
            )

        self.assertEqual([page["page_number"] for page in retrieved], [4, 5])
        self.assertEqual(
            retrieved[0]["page_content"],
            "Chunk pertinent. Contexte complet de la page 4.",
        )
        self.assertEqual(retrieved[1]["page_content"], "Contenu intégral de la page 5.")


if __name__ == "__main__":
    unittest.main()