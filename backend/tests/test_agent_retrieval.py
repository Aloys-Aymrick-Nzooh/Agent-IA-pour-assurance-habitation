import unittest

from app.services.ai_agent_service import config
from app.services.ai_agent_service.agent_retrieval import retrieve_documents


class FakeRetriever:
    def __init__(self):
        self.calls = []
        self.results = {
            "conditions garantie": [
                {"chunk_id": "cg:1:0", "document_id": "cg", "document_type": "CG", "page_number": 1, "text": "Clause CG", "score": 0.9},
                {"chunk_id": "cg:1:1", "document_id": "cg", "document_type": "CG", "page_number": 1, "text": "Suite CG", "score": 0.8},
            ],
            "exclusion garantie": [
                {"chunk_id": "cg:1:0", "document_id": "cg", "document_type": "CG", "page_number": 1, "text": "Clause CG", "score": 0.95},
            ],
            "option contrat": [
                {"chunk_id": "cp:2:0", "document_id": "cp", "document_type": "CP", "page_number": 2, "text": "Option CP", "score": 0.85},
            ],
        }

    def search(self, conversation_id, query, doc_types, top_k, tracer):
        self.calls.append((query, doc_types, top_k))
        return self.results[query]


class AgentRetrievalTest(unittest.TestCase):
    def test_searches_each_axis_with_top_k_and_merges_duplicate_chunks(self):
        retriever = FakeRetriever()
        state = {
            "conversation_id": "conversation-1",
            "search_axes": [
                {"axis_id": "axis-1", "document_type": "CG", "query": "conditions garantie", "reason": "Règles."},
                {"axis_id": "axis-2", "document_type": "CG", "query": "exclusion garantie", "reason": "Exclusions."},
                {"axis_id": "axis-3", "document_type": "CP", "query": "option contrat", "reason": "Souscription."},
            ],
        }

        result = retrieve_documents(state, retriever)

        self.assertEqual(len(retriever.calls), 3)
        self.assertEqual(
            retriever.calls,
            [
                ("conditions garantie", ["CG"], config.TOP_K),
                ("exclusion garantie", ["CG"], config.TOP_K),
                ("option contrat", ["CP"], config.TOP_K),
            ],
        )
        chunks = {passage["chunk_id"]: passage for passage in result["retrieval_results"]}
        self.assertEqual(set(chunks), {"cg:1:0", "cg:1:1", "cp:2:0"})
        self.assertEqual(
            [axis["axis_id"] for axis in chunks["cg:1:0"]["matched_axes"]],
            ["axis-1", "axis-2"],
        )


if __name__ == "__main__":
    unittest.main()