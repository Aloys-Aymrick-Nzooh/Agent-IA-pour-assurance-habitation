from typing import Any

from .state import AgentState
from .retrieval_algorithm import HybridRetriever


def build_evidence(
    state: AgentState,
    retriever: HybridRetriever,
) -> dict[str, Any]:
    conversation_id = state.get("conversation_id")
    results = state.get("retrieval_results", [])

    if not conversation_id:
        raise ValueError("conversation_id est obligatoire.")

    if not results:
        return {
            "retrieved_pages": [],
            "missing_information": ["Aucun passage pertinent retrouvé."],
        }

    pages_by_key: dict[tuple[str, str, int], dict[str, Any]] = {}
    passages_by_page: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    axes_by_page: dict[tuple[str, str, int], list[dict[str, Any]]] = {}

    for passage in results:
        key = (
            passage["document_id"],
            passage["document_type"],
            passage["page_number"],
        )
        pages_by_key.setdefault(key, {
            "document_id": passage["document_id"],
            "document_type": passage["document_type"],
            "page_number": passage["page_number"],
        })
        page_passages = passages_by_page.setdefault(key, [])
        if not any(item["chunk_id"] == passage["chunk_id"] for item in page_passages):
            page_passages.append({
                "chunk_id": passage["chunk_id"],
                "text": passage["text"],
                "score": passage.get("score"),
            })
        page_axes = axes_by_page.setdefault(key, [])
        for axis in passage.get("matched_axes", []):
            if not any(item.get("axis_id") == axis.get("axis_id") for item in page_axes):
                page_axes.append(axis)

    source_pages = retriever.vs.get_pages(
        conversation_id=conversation_id,
        refs=list(pages_by_key.values()),
    )
    source_pages_by_key = {
        (
            page["document_id"],
            page["document_type"],
            page["page_number"],
        ): page
        for page in source_pages
    }

    if not source_pages_by_key or len(source_pages_by_key) != len(pages_by_key):
        return {
            "retrieved_pages": [],
            "missing_information": [
                "Le contenu complet d'une ou plusieurs pages retrouvées est indisponible."
            ],
        }

    retrieved_pages = []
    for key in pages_by_key:
        page = source_pages_by_key[key]
        retrieved_pages.append({
            "document_id": page["document_id"],
            "document_name": page["document_name"],
            "document_type": page["document_type"],
            "chapter": page.get("chapter", ""),
            "page_number": page["page_number"],
            "titles": page.get("titles", []),
            "page_content": page["page_content"],
            "matched_axes": axes_by_page[key],
            "passages": passages_by_page[key],
        })

    return {
        "retrieved_pages": retrieved_pages,
        "missing_information": [],
    }