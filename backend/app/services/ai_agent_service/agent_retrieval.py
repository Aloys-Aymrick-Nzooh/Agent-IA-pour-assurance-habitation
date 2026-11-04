from typing import Any

from . import config
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
    search_axes = state.get("search_axes", [])

    if not conversation_id:
        raise ValueError("conversation_id est obligatoire.")

    if not search_axes:
        raise ValueError("Aucun axe de recherche n'a été planifié.")

    results_by_chunk = {
        passage["chunk_id"]: passage
        for passage in state.get("retrieval_results", [])
    }
    for passage in results_by_chunk.values():
        passage.setdefault("matched_axes", [])

    executed_queries = list(state.get("executed_queries", []))
    executed_keys = {
        (item.get("document_type"), " ".join(item.get("query", "").casefold().split()))
        for item in executed_queries
        if isinstance(item, dict)
    }

    for index, axis in enumerate(search_axes, start=1):
        axis_id = axis.get("axis_id", f"axis-{index}")
        document_type = axis["document_type"]
        query = axis["query"].strip()
        if not query:
            continue

        query_key = (document_type, " ".join(query.casefold().split()))
        if query_key in executed_keys:
            continue

        results = retriever.search(
            conversation_id=conversation_id,
            query=query,
            doc_types=[document_type],
            top_k=config.TOP_K,
            tracer=tracer,
        )

        axis_ref = {
            "axis_id": axis_id,
            "document_type": document_type,
            "query": query,
            "reason": axis.get("reason", ""),
        }
        executed_queries.append({"document_type": document_type, "query": query})
        executed_keys.add(query_key)
        for passage in results:
            chunk_id = passage["chunk_id"]
            existing = results_by_chunk.get(chunk_id)
            if existing is None:
                results_by_chunk[chunk_id] = {
                    **passage,
                    "matched_axes": [axis_ref],
                }
                continue

            if not any(item["axis_id"] == axis_id for item in existing["matched_axes"]):
                existing["matched_axes"].append(axis_ref)
            existing["score"] = max(
                existing.get("score") or 0.0,
                passage.get("score") or 0.0,
            )

    return {
        "retrieval_results": list(results_by_chunk.values()),
        "retrieval_attempts": state.get("retrieval_attempts", 0) + 1,
        "retrieval_iteration": state.get("retrieval_attempts", 0),
        "executed_queries": executed_queries,
    }