from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from .state import AgentState
from .llm import LLM


class GeneratedCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    document_name: str
    document_type: Literal["CG", "CP", "AVENANT", "ANNEXE"]
    page_number: int
    chunk_id: str


class GeneratedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    citations: list[GeneratedCitation]
    limitations: list[str]


ANSWER_GENERATOR_SYSTEM = """
Tu es un assistant spécialisé dans l'analyse des contrats
d'assurance habitation.

Ta mission est de répondre à la question de l'utilisateur
en utilisant exclusivement les preuves documentaires fournies.

RÈGLES OBLIGATOIRES :

1. N'invente aucune garantie, exclusion, franchise, limite
   d'indemnisation ou condition contractuelle.

2. Chaque affirmation relative au contrat doit être soutenue
   par une preuve documentaire.

3. Distingue clairement :
   - les garanties prévues ;
   - les conditions d'application ;
   - les exclusions ;
   - les franchises ;
   - les plafonds ;
   - les informations non retrouvées.

4. Ne considère jamais qu'une garantie est exclue simplement
   parce que les passages fournis n'en parlent pas.

5. Si les conditions dépendent des circonstances du sinistre,
   explique lesquelles doivent être vérifiées.

6. Si les documents ne permettent pas de conclure, dis-le
   explicitement.

7. Ne donne pas de conseil juridique définitif.

8. Utilise un langage simple, précis et pédagogique.

CITATIONS :

- Utilise exclusivement les références présentes dans les preuves.
- Pour chaque citation, conserve document_id, document_name,
  document_type, page_number et chunk_id.
- N'invente jamais de numéro de page ou de document.
- Les citations doivent soutenir directement les affirmations.

Ne réponds pas au-delà de ce que les preuves permettent d'établir.
"""


def generate_answer(
    state: AgentState,
    llm: LLM,
) -> dict[str, Any]:

    question = (
        state.get("resolved_question")
        or state.get("original_question")
        or ""
    ).strip()

    if not question:
        raise ValueError("Aucune question disponible.")

    if state.get("evidence_decision") != "ANSWER":
        raise ValueError(
            "La génération est autorisée uniquement si "
            "evidence_decision vaut ANSWER."
        )

    if not state.get("evidence_sufficient", False):
        raise ValueError("Les preuves ne sont pas suffisantes.")

    pages = state.get("retrieved_pages", [])

    if not pages:
        raise ValueError("Aucune preuve documentaire disponible.")

    messages = [
        {
            "role": "user",
            "content": (
                f"Question de l'utilisateur :\n{question}\n\n"
                f"Preuves documentaires :\n{pages}\n\n"
                "Rédige une réponse en respectant strictement "
                "les règles du système."
            ),
        }
    ]

    result = llm.structured(
        schema=GeneratedAnswer,
        system=ANSWER_GENERATOR_SYSTEM,
        messages=messages,
        retries=1,
    )

    if not isinstance(result, GeneratedAnswer):
        raise TypeError(
            "Le LLM doit retourner un objet GeneratedAnswer."
        )

    answer = result.answer.strip()

    if not answer:
        raise ValueError("Le LLM a retourné une réponse vide.")

    return {
        "answer": answer,
        "citations": [citation.model_dump() for citation in result.citations],
        "limitations": result.limitations,
    }