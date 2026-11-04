import unittest

from app.services.ai_agent_service.citation_validator import validate_citations


class CitationValidatorTest(unittest.TestCase):
    def test_deduplicates_same_page(self):
        state = {
            "retrieved_pages": [{
                "document_id": "d1",
                "document_name": "CG",
                "document_type": "CG",
                "page_number": 12,
                "passages": [
                    {"chunk_id": "c1", "text": "x"},
                    {"chunk_id": "c2", "text": "y"},
                ],
            }],
            "citations": [
                {
                    "document_id": "d1",
                    "document_name": "CG",
                    "document_type": "CG",
                    "page_number": 12,
                    "chunk_id": "c1",
                },
                {
                    "document_id": "d1",
                    "document_name": "CG",
                    "document_type": "CG",
                    "page_number": 12,
                    "chunk_id": "c2",
                },
            ],
        }

        result = validate_citations(state)

        self.assertEqual(len(result["citations"]), 1)
        self.assertEqual(result["citations"][0]["page_number"], 12)
        self.assertEqual(result["citations"][0]["excerpt"], "x")
        self.assertTrue(result["citations_validated"])

    def test_keeps_different_pages(self):
        state = {
            "retrieved_pages": [
                {
                    "document_id": "d1",
                    "document_name": "CG",
                    "document_type": "CG",
                    "page_number": 12,
                    "passages": [{"chunk_id": "c1", "text": "x"}],
                },
                {
                    "document_id": "d1",
                    "document_name": "CG",
                    "document_type": "CG",
                    "page_number": 15,
                    "passages": [{"chunk_id": "c2", "text": "y"}],
                },
            ],
            "citations": [
                {
                    "document_id": "d1",
                    "document_name": "CG",
                    "document_type": "CG",
                    "page_number": 12,
                    "chunk_id": "c1",
                },
                {
                    "document_id": "d1",
                    "document_name": "CG",
                    "document_type": "CG",
                    "page_number": 15,
                    "chunk_id": "c2",
                },
            ],
        }

        result = validate_citations(state)

        self.assertEqual(len(result["citations"]), 2)


if __name__ == "__main__":
    unittest.main()
