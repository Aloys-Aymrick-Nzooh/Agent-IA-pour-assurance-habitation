import unittest

from app.services.ai_agent_service.retrieval_planner import plan_retrieval


class FakeLLM:
    def __init__(self, axes, reason="Axes distincts pour les documents."):
        self.axes = axes
        self.reason = reason

    def structured(self, schema, system, messages, retries):
        return schema(axes=self.axes, reason=self.reason)


class RetrievalPlannerTest(unittest.TestCase):
    def test_creates_separate_axes_for_available_document_types(self):
        llm = FakeLLM([
            {
                "document_type": "CG",
                "query": "conditions et exclusions de la garantie dégâts des eaux",
                "reason": "Trouver les règles générales de la garantie.",
            },
            {
                "document_type": "CP",
                "query": "option dégâts des eaux souscrite et plafonds applicables",
                "reason": "Vérifier la couverture propre au contrat.",
            },
            {
                "document_type": "ANNEXE",
                "query": "annexe dégâts des eaux",
                "reason": "Ce type n'est pas disponible.",
            },
        ])

        result = plan_retrieval(
            {"original_question": "Suis-je couvert ?"},
            llm,
            ["CG", "CP"],
        )

        self.assertEqual(
            [(axis["document_type"], axis["query"]) for axis in result["search_axes"]],
            [
                ("CG", "conditions et exclusions de la garantie dégâts des eaux"),
                ("CP", "option dégâts des eaux souscrite et plafonds applicables"),
            ],
        )

    def test_falls_back_to_one_question_axis_per_available_type(self):
        result = plan_retrieval(
            {"original_question": "Quel est le plafond ?"},
            FakeLLM([]),
            ["CG", "CP"],
        )

        self.assertEqual(
            [axis["document_type"] for axis in result["search_axes"]],
            ["CG", "CP"],
        )
        self.assertTrue(all(axis["query"] == "Quel est le plafond ?" for axis in result["search_axes"]))


if __name__ == "__main__":
    unittest.main()