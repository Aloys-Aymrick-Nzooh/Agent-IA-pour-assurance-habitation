from typing import Literal

from pydantic import BaseModel, Field

from .state import AgentState
from .llm import LLM
from .retrieval_planner import SearchAxis, normalize_search_axes


DocumentType = Literal["CG", "CP", "AVENANT", "ANNEXE"]


class RetrievalRefinement(BaseModel):
    additional_axes: list[SearchAxis] = Field(
        description="Axes supplémentaires ciblant les informations manquantes."
    )
    reason: str = Field(
        description="Explication de la stratégie de recherche améliorée."
    )


def _normalize_query(query: str) -> str:
    return " ".join(query.lower().split())


def refine_retrieval(state: AgentState, llm: LLM) -> dict:
    """
    Prépare une nouvelle stratégie de recherche lorsque les preuves
    récupérées sont insuffisantes.
    """
    previous_axes = [
        SearchAxis.model_validate(axis)
        for axis in state.get("search_axes", [])
    ]
    available_doc_types = state.get(
        "available_doc_types",
        [axis.document_type for axis in previous_axes],
    )
    missing_information = state.get("missing_information", [])
    question = (
        state.get("resolved_question")
        or state.get("original_question")
        or ""
    ).strip()

    if not question:
        raise ValueError("Impossible de reformuler une recherche sans question.")

    if not previous_axes:
        raise ValueError("Les axes de recherche précédents sont absents.")

    allowed_doc_types = [
        document_type
        for document_type in ("CG", "CP", "AVENANT", "ANNEXE")
        if document_type in available_doc_types
    ]

    if not allowed_doc_types:
        raise ValueError("Aucun type de document indexé n'est disponible.")

    system = """
Tu es un spécialiste de la recherche documentaire dans des contrats
d'assurance habitation.

Une première recherche a été effectuée, mais les preuves récupérées
ne permettent pas encore de répondre de manière fiable.

Ta mission :
- analyser les informations manquantes ;
- proposer uniquement des axes de recherche supplémentaires ;
- associer chaque axe à un seul type de document ;
- élargir ou préciser les recherches sans inventer de clauses.

Types autorisés :
- CG : conditions générales ;
- CP : conditions particulières ;
- AVENANT : avenants au contrat ;
- ANNEXE : annexes contractuelles.

Ne sélectionne que les types effectivement disponibles dans la conversation.

Règles :
- Ne répète pas les axes déjà exécutés.
- Cible explicitement les notions ou informations encore manquantes.
- Si nécessaire, élargis les types de documents consultés.
- Ne sélectionne que les types réellement utiles.
- N'ajoute aucun axe qui ne cible une information manquante.
- N'invente jamais le contenu du contrat.
"""

    user = f"""
Question de l'utilisateur :
{question}

Axes déjà exécutés :
{[axis.model_dump() for axis in previous_axes]}

Types de documents actuellement indexés et disponibles :
{allowed_doc_types}

Informations manquantes identifiées :
{missing_information}

Requêtes de suivi proposées par l'évaluateur :
{state.get("follow_up_queries", [])}

Propose des axes supplémentaires pour compléter la stratégie existante.
"""

    refinement = llm.structured(
        schema=RetrievalRefinement,
        system=system,
        messages=[{"role": "user", "content": user}],
        retries=1,
    )

    previous_normalized = normalize_search_axes(previous_axes, allowed_doc_types)
    expanded_axes = normalize_search_axes(
        [*previous_axes, *refinement.additional_axes],
        allowed_doc_types,
    )
    previous_keys = {
        (axis["document_type"], _normalize_query(axis["query"]))
        for axis in previous_normalized
    }
    added_axes = [
        axis for axis in expanded_axes
        if (axis["document_type"], _normalize_query(axis["query"])) not in previous_keys
    ]

    if not added_axes:
        raise ValueError(
            "Aucun axe supplémentaire ne complète la recherche précédente."
        )

    return {
        "search_axes": expanded_axes,
        "retrieval_refinement_reason": refinement.reason,
    }