from typing import Literal

from pydantic import BaseModel

from .state import AgentState
from .llm import LLM


DocumentType = Literal["CG", "CP", "AVENANT", "ANNEXE"]


class SearchAxis(BaseModel):
    document_type: DocumentType
    query: str
    reason: str


class RetrievalPlan(BaseModel):
    axes: list[SearchAxis]
    reason: str


def normalize_search_axes(
    axes: list[SearchAxis],
    allowed_doc_types: list[str],
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for axis in axes:
        document_type = axis.document_type
        query = " ".join(axis.query.lower().split())
        if document_type not in allowed_doc_types or not query:
            continue

        key = (document_type, query)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({
            "axis_id": f"axis-{len(normalized) + 1}",
            "document_type": document_type,
            "query": axis.query.strip(),
            "reason": axis.reason.strip(),
        })

    return normalized


RETRIEVAL_PLANNER_SYSTEM = """
Tu es un planificateur de recherche documentaire spécialisé
dans les contrats d'assurance habitation.

Tu décomposes la question en axes de recherche indépendants.
Chaque axe concerne un seul type de document et contient une requête
autonome, précise et adaptée à ce type.

Catégories disponibles :
- CG : conditions générales du contrat
- CP : conditions particulières du contrat
- AVENANT : modifications ou compléments du contrat
- ANNEXE : documents annexes au contrat

IMPORTANT :
Les identifiants des catégories doivent toujours être retournés
en majuscules : CG, CP, AVENANT ou ANNEXE.


Règles :

1. Les conditions générales décrivent les garanties, exclusions,
   franchises, plafonds et conditions générales d'application.

2. Les conditions particulières contiennent les informations
   propres au contrat de l'assuré : formule souscrite, options,
   montants, franchises spécifiques, biens et personnes assurés.

3. Les avenants peuvent modifier les garanties ou les conditions
   du contrat initial.

4. Les annexes peuvent contenir des informations complémentaires
   nécessaires à l'interprétation du contrat.

5. Crée un axe distinct pour chaque information à rechercher dans
    chaque type de document pertinent. Plusieurs axes peuvent viser
    le même type si les informations recherchées sont différentes.

6. Chaque axe doit cibler un seul type de document disponible.

7. Pour une question sur une garantie, sépare si nécessaire les
    dispositions générales (CG) des garanties, options, montants ou
    franchises propres au contrat (CP).

8. Les requêtes des axes doivent être autonomes et précises, sans
    ajouter de faits non établis.

9. Ne réponds pas à la question d'assurance.
"""


def plan_retrieval(
    state: AgentState,
    llm: LLM,
    available_doc_types: list[str],
) -> dict:
    question = state.get("resolved_question", "").strip()

    if not question:
        question = state.get("original_question", "").strip()

    if not question:
        raise ValueError("Aucune question disponible pour la recherche.")

    allowed_doc_types = [
        document_type
        for document_type in ("CG", "CP", "AVENANT", "ANNEXE")
        if document_type in available_doc_types
    ]

    if not allowed_doc_types:
        return {
            "available_doc_types": [],
            "search_axes": [],
            "retrieval_plan_reason": (
                "Aucun type de document n'est indexé dans la base "
                "de cette conversation."
            ),
            "missing_information": [
                "Aucun document indexé n'est disponible pour cette conversation."
            ],
        }

    messages = [
        {
            "role": "user",
            "content": (
                f"Types de documents indexés et disponibles : "
                f"{allowed_doc_types}\n\n"
                f"Question à décomposer en axes de recherche :\n{question}"
            ),
        }
    ]

    result = llm.structured(
        schema=RetrievalPlan,
        system=RETRIEVAL_PLANNER_SYSTEM,
        messages=messages,
        retries=1,
    )

    if not isinstance(result, RetrievalPlan):
        raise TypeError("Le LLM doit retourner un RetrievalPlan.")

    search_axes = normalize_search_axes(result.axes, allowed_doc_types)
    plan_reason = result.reason.strip()
    if not search_axes:
        search_axes = [
            {
                "axis_id": f"axis-{index}",
                "document_type": document_type,
                "query": question,
                "reason": "Recherche de secours dans le type disponible.",
            }
            for index, document_type in enumerate(allowed_doc_types, start=1)
        ]
        plan_reason += (
            " Aucun axe valide n'a été proposé ; une recherche de secours "
            "est lancée dans chaque type disponible."
        )

    return {
        "available_doc_types": allowed_doc_types,
        "search_axes": search_axes,
        "retrieval_plan_reason": plan_reason,
    }