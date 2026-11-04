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

FORMAT DE SORTIE :
- Rédige answer en Markdown GitHub (GFM) valide : titres, listes,
  tableaux ou emphase uniquement quand cela améliore la lisibilité.
- N'inclus aucun HTML et n'entoure pas la réponse d'un bloc de code.
- Préserve les marqueurs de citation [[cite:<chunk_id>]] en fin de phrase.

CITATIONS :

- Utilise exclusivement les références présentes dans les preuves.
- Retourne les références dans le champ citations et ajoute à la fin
    de chaque phrase factuelle un marqueur [[cite:<chunk_id>]], en utilisant
    le chunk_id exact de la preuve qui soutient cette phrase.
- N'affiche jamais document_id, document_name, page_number ou chunk_id
    autrement que dans ces marqueurs techniques.
- N'invente jamais de numéro de page ou de document.
- Les citations doivent soutenir directement les affirmations.
- Les marqueurs seront remplacés par des boutons de source dans l'interface.

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

    retrieved_pages = state.get("retrieved_pages", [])
    supporting_page_keys = {
        (str(page.get("document_id")), page.get("page_number"))
        for page in state.get("supporting_pages", [])
    }
    pages = [
        page for page in retrieved_pages
        if not supporting_page_keys
        or (str(page.get("document_id")), page.get("page_number")) in supporting_page_keys
    ]

    if not pages:
        raise ValueError("Aucune preuve documentaire disponible.")

    messages = [
        {
            "role": "user",
            "content": (
                f"Question de l'utilisateur :\n{question}\n\n"
                f"Évaluation par axe :\n{state.get('axis_assessments', [])}\n\n"
                f"Limites identifiées :\n{state.get('limitations', [])}\n\n"
                f"Contradictions détectées :\n{state.get('contradictions', [])}\n\n"
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

    answer = result.answer

    if not answer.strip():
        raise ValueError("Le LLM a retourné une réponse vide.")

    return {
        "answer": answer,
        "citations": [citation.model_dump() for citation in result.citations],
        "limitations": list(dict.fromkeys([
            *result.limitations,
            *state.get("limitations", []),
            *[
                f"Contradiction documentaire : {item}"
                for item in state.get("contradictions", [])
            ],
        ])),
    }