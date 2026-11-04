from typing import Any

from .state import AgentState


def finalize_clarification(state: AgentState) -> dict[str, Any]:
    question = state.get("clarification_question", "").strip()

    if not question:
        raise ValueError(
            "Une question de clarification est nécessaire."
        )

    return {
        "answer": question,
        "citations": [],
        "limitations": [
            "Une précision est nécessaire avant de poursuivre l'analyse."
        ],
    }


def finalize_abstention(state: AgentState) -> dict[str, Any]:
    missing = state.get("missing_information", [])
    reason = state.get("evidence_evaluation_reason", "").strip()

    limitations = list(missing)
    limitations.extend(state.get("limitations", []))
    limitations.extend(
        f"Contradiction documentaire : {item}"
        for item in state.get("contradictions", [])
    )

    if reason:
        limitations.append(reason)

    if not limitations:
        limitations.append(
            "Les documents disponibles ne permettent pas "
            "de conclure de manière suffisamment fiable."
        )

    answer = (
        "Je ne peux pas confirmer la réponse à partir des "
        "documents disponibles. "
        "Les éléments retrouvés ne permettent pas d'établir "
        "une conclusion suffisamment fiable."
    )

    return {
        "answer": answer,
        "citations": [],
        "limitations": limitations,
    }


def finalize_out_of_scope(state: AgentState) -> dict[str, Any]:
    return {
        "answer": (
            "Je suis spécialisé dans l'assurance habitation et l'analyse "
            "des documents associés. Je peux vous aider avec une question "
            "sur ce sujet."
        ),
        "citations": [],
        "limitations": [
            "La demande ne concerne pas l'assurance habitation ni l'analyse de documents contractuels."
        ],
    }