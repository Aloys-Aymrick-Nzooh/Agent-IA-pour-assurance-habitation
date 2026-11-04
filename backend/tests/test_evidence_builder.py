import unittest

from app.services.ai_agent_service.evidence_builder import build_evidence
from app.services.ai_agent_service.evidence_evaluator import evaluate_evidence


class FakeVectorStore:
    def __init__(self, pages):
        self.pages = pages
        self.requested_refs = []

    def get_pages(self, conversation_id, refs):
        self.requested_refs = refs
        requested = {
            (ref["document_id"], ref["document_type"], ref["page_number"])
            for ref in refs
        }
        return [
            page for page in self.pages
            if (page["document_id"], page["document_type"], page["page_number"])
            in requested
        ]


class FakeRetriever:
    def __init__(self, vector_store):
        self.vs = vector_store


class FakeLLM:
    def __init__(self, response=None):
        self.response = response or {}

    def structured(self, schema, system, messages, retries):
        self.content = messages[0]["content"]
        values = {
            "decision": "ANSWER",
            "supporting_pages": [{"document_id": "doc-1", "page_number": 5}],
            "evidence_sufficient": True,
            "reason": "Les pages contiennent les informations nécessaires.",
        }
        values.update(self.response)
        return schema(**values)


class EvidenceBuilderTest(unittest.TestCase):
    def test_deduplicates_page_refs_and_loads_full_page_content(self):
        vector_store = FakeVectorStore([
            {
                "document_id": "doc-1",
                "document_name": "CP.pdf",
                "document_type": "CP",
                "chapter": "Garanties",
                "page_number": 5,
                "titles": ["Plafonds"],
                "page_content": "Chunk retenu. Contexte complet de la page.",
            },
        ])
        state = {
            "conversation_id": "conversation-1",
            "retrieval_results": [
                {
                    "chunk_id": "doc-1:5:0",
                    "document_id": "doc-1",
                    "document_name": "CP.pdf",
                    "document_type": "CP",
                    "page_number": 5,
                    "text": "Chunk retenu.",
                    "score": 0.9,
                },
                {
                    "chunk_id": "doc-1:5:1",
                    "document_id": "doc-1",
                    "document_name": "CP.pdf",
                    "document_type": "CP",
                    "page_number": 5,
                    "text": "Autre chunk retenu.",
                    "score": 0.8,
                },
            ],
        }

        result = build_evidence(state, FakeRetriever(vector_store))

        self.assertEqual(len(vector_store.requested_refs), 1)
        self.assertEqual(len(result["retrieved_pages"]), 1)
        page = result["retrieved_pages"][0]
        self.assertEqual(page["page_content"], "Chunk retenu. Contexte complet de la page.")
        self.assertEqual(len(page["passages"]), 2)

    def test_evaluator_receives_full_page_without_chunk_payload(self):
        page_content = "Clause sélectionnée. Contexte adjacent utile à l'interprétation."
        state = {
            "original_question": "Et mon plafond ?",
            "resolved_question": "Quel est le plafond ?",
            "search_axes": [{
                "axis_id": "axis-1",
                "document_type": "CP",
                "query": "plafond mobilier",
                "reason": "Chercher le montant propre au contrat.",
            }],
            "retrieved_pages": [{
                "document_id": "doc-1",
                "document_name": "CP.pdf",
                "document_type": "CP",
                "chapter": "Garanties",
                "page_number": 5,
                "titles": ["Plafonds"],
                "page_content": page_content,
                "passages": [{"chunk_id": "doc-1:5:0", "text": "Clause sélectionnée."}],
            }],
        }
        llm = FakeLLM()

        evaluate_evidence(state, llm)

        self.assertIn(page_content, llm.content)
        self.assertIn("Et mon plafond ?", llm.content)
        self.assertIn("Quel est le plafond ?", llm.content)
        self.assertIn("plafond mobilier", llm.content)
        self.assertNotIn("chunk_id", llm.content)
        self.assertNotIn("passages", llm.content)

    def test_answer_with_unknown_supporting_page_is_downgraded(self):
        llm = FakeLLM({
            "supporting_pages": [{"document_id": "not-retrieved", "page_number": 99}],
        })
        state = {
            "original_question": "Quel est le plafond ?",
            "retrieved_pages": [{"document_id": "doc-1", "page_number": 5}],
        }

        result = evaluate_evidence(state, llm)

        self.assertEqual(result["evidence_decision"], "ABSTAIN")
        self.assertFalse(result["evidence_sufficient"])
        self.assertEqual(result["supporting_pages"], [])

    def test_retrieve_more_stops_at_iteration_limit(self):
        llm = FakeLLM({
            "decision": "RETRIEVE_MORE",
            "evidence_sufficient": False,
            "supporting_pages": [],
            "follow_up_queries": ["franchise applicable au sinistre"],
        })
        state = {
            "original_question": "Quelle franchise s'applique ?",
            "retrieval_iteration": 2,
            "retrieved_pages": [{"document_id": "doc-1", "page_number": 5}],
        }

        result = evaluate_evidence(state, llm)

        self.assertEqual(result["evidence_decision"], "ABSTAIN")
        self.assertEqual(result["follow_up_queries"], [])


if __name__ == "__main__":
    unittest.main()