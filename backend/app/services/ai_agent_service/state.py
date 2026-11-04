
from typing import Any, Literal, TypedDict


# Intentions que le routeur pourra identifier.
AgentIntent = Literal[
    "GENERAL",
    "CONTRACT_QUESTION",
    "FOLLOW_UP",
    "COMPARE",
    "CLARIFICATION",
    "OUT_OF_SCOPE",
]

# Décisions possibles après l'évaluation des preuves.
EvidenceDecision = Literal[
    "ANSWER",
    "RETRIEVE_MORE",
    "CLARIFY",
    "ABSTAIN",
]


class AgentState(TypedDict, total=False):
    """
    État partagé entre les nœuds de l'agent IA.

    Les champs sont optionnels pour permettre à chaque nœud
    de ne renseigner que les informations qu'il produit.
    """

    # Identifiants
    conversation_id: str

    # Question de l'utilisateur
    original_question: str
    resolved_question: str

    # Historique conversationnel
    conversation_history: list[dict[str, Any]]
    available_documents: list[dict[str, Any]]
    is_follow_up: bool

    # Classification et routage
    intent: AgentIntent
    search_axes: list[dict[str, Any]]
    route_reason: str

    # Clarification
    needs_clarification: bool
    clarification_question: str

    # Réponse générale
    general_answer_reason: str


    # Recherche documentaire
    retrieval_attempts: int
    retrieval_iteration: int
    executed_queries: list[dict[str, str]]
    retrieval_results: list[dict[str, Any]]
    retrieved_pages: list[dict[str, Any]]
    missing_information: list[str]
    follow_up_queries: list[str]
    supporting_pages: list[dict[str, Any]]
    axis_assessments: list[dict[str, Any]]
    contradictions: list[str]
    available_doc_types: list[str]
    search_trace: list[dict[str, Any]]
    
    retrieval_plan_reason: str
    context_resolution_reason: str

    retrieval_refinement_reason: str
    retrieval_refinement_error: str



    # Évaluation des preuves
    evidence_decision: EvidenceDecision
    evidence_evaluation_reason: str
    evidence_sufficient: bool
    missing_information: list[str]

    # Réponse finale
    answer: str
    citations: list[dict[str, Any]]
    citations_validated: bool
    limitations: list[str]


