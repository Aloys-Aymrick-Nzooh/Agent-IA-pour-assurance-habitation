import unittest

from app.services.ai_agent_service.query_refiner import refine_retrieval


class FakeLLM:
    def __init__(self, additional_axes):
        self.additional_axes = additional_axes
        self.user_message = ""

    def structured(self, schema, system, messages, retries):
        self.user_message = messages[0]["content"]
        return schema(
            additional_axes=self.additional_axes,
            reason="Recherche dans les CP pour vérifier la souscription.",
        )


class QueryRefinerTest(unittest.TestCase):
    def test_adds_new_axis_and_preserves_previous_axes(self):
        llm = FakeLLM([{
            "document_type": "CP",
            "query": "option dégâts des eaux souscrite",
            "reason": "Vérifier l'option au contrat.",
        }])
        previous_axis = {
            "axis_id": "axis-1",
            "document_type": "CG",
            "query": "conditions de la garantie",
            "reason": "Trouver les règles générales.",
        }
        result = refine_retrieval(
            {
                "original_question": "Mon dégât est-il couvert ?",
                "available_doc_types": ["CG", "CP"],
                "search_axes": [previous_axis],
                "missing_information": ["Option souscrite dans les CP."],
                "follow_up_queries": ["option dégâts des eaux souscrite"],
            },
            llm,
        )

        self.assertEqual(
            [(axis["document_type"], axis["query"]) for axis in result["search_axes"]],
            [
                ("CG", "conditions de la garantie"),
                ("CP", "option dégâts des eaux souscrite"),
            ],
        )
        self.assertIn("option dégâts des eaux souscrite", llm.user_message)


if __name__ == "__main__":
    unittest.main()