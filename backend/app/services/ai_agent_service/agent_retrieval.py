from typing import Any

from .state import AgentState
from .retrieval_algorithm import HybridRetriever


def retrieve_documents(
    state: AgentState,
    retriever: HybridRetriever,
    tracer: Any = None,
) -> dict[str, Any]:
    """
    Recherche les passages pertinents dans les documents
    associés à une conversation.
    """

    conversation_id = state.get("conversation_id")
    query = state.get("search_query", "").strip()
    doc_types = state.get("doc_types", [])

    if not conversation_id:
        raise ValueError("conversation_id est obligatoire.")

    if not query:
        raise ValueError("search_query est obligatoire.")

    if not doc_types:
        raise ValueError("Aucun type de document sélectionné.")

    results = retriever.search(
        conversation_id=conversation_id,
        query=query,
        doc_types=doc_types,
        top_k=10,
        tracer=tracer,
    )

    return {
        "retrieval_results": results,
        "retrieval_attempts": state.get("retrieval_attempts", 0) + 1,
    }