from typing import Any


REQUIRED_CITATION_FIELDS = {
    "document_id",
    "document_name",
    "document_type",
    "page_number",
    "chunk_id",
}


class CitationValidationError(ValueError):
    """Une citation ne correspond pas aux preuves disponibles."""


def validate_citations(
    state: dict[str, Any],
) -> dict[str, Any]:
    """
    Vérifie que chaque citation correspond à un passage
    réellement présent dans les preuves récupérées.
    """

    pages = state.get("retrieved_pages", [])
    citations = state.get("citations", [])

    if not pages:
        raise CitationValidationError(
            "Impossible de valider les citations sans preuves."
        )

    if not citations:
        raise CitationValidationError(
            "La réponse ne contient aucune citation."
        )

    # Construction de la liste des références autorisées.
    allowed: dict[str, dict[str, Any]] = {}

    for page in pages:
        for passage in page.get("passages", []):
            chunk_id = passage.get("chunk_id")

            if not chunk_id:
                continue

            allowed[chunk_id] = {
                "document_id": page.get("document_id"),
                "document_name": page.get("document_name"),
                "document_type": page.get("document_type"),
                "page_number": page.get("page_number"),
                "chunk_id": chunk_id,
            }

    validated = []
    seen = set()

    for citation in citations:

        if not isinstance(citation, dict):
            raise CitationValidationError(
                "Une citation possède un format invalide."
            )

        missing = REQUIRED_CITATION_FIELDS - citation.keys()

        if missing:
            raise CitationValidationError(
                f"Champs manquants dans une citation : {sorted(missing)}"
            )

        chunk_id = citation["chunk_id"]

        if chunk_id not in allowed:
            raise CitationValidationError(
                f"Le passage cité n'existe pas dans les preuves : {chunk_id}"
            )

        expected = allowed[chunk_id]

        for field in REQUIRED_CITATION_FIELDS:
            if citation[field] != expected[field]:
                raise CitationValidationError(
                    f"Référence incorrecte pour {chunk_id} : {field}"
                )

        # Évite les citations identiques répétées.
        if chunk_id not in seen:
            validated.append(expected)
            seen.add(chunk_id)

    return {
        "citations": validated,
        "citations_validated": True,
    }