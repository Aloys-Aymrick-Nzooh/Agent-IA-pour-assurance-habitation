
from typing import Any

from langgraph.graph import END, START, StateGraph

from .state import AgentState
from .router import route_intent
from .context_resolver import resolve_context
from .retrieval_planner import plan_retrieval
from .query_refiner import refine_retrieval
from .agent_retrieval import retrieve_documents
from .evidence_builder import build_evidence
from .evidence_evaluator import evaluate_evidence
from .answer_generator import generate_answer
from .general_answer import generate_general_answer
from .citation_validator import validate_citations
from .finalizer import (
    finalize_clarification,
    finalize_abstention,
    finalize_out_of_scope,
)


MAX_RETRIEVAL_ATTEMPTS = 3


def route_after_intent(state: AgentState) -> str:
    if state.get("needs_clarification"):
        return "clarify"

    intent = state.get("intent")

    if intent == "GENERAL":
        return "general_answer"

    if intent == "OUT_OF_SCOPE":
        return "out_of_scope"

    if intent == "CLARIFICATION":
        return "clarify"

    if intent == "CONTRACT_QUESTION":
        return "plan_retrieval"

    return "resolve_context"


def route_after_context(state: AgentState) -> str:
    if state.get("needs_clarification"):
        return "clarify"

    return "plan_retrieval"


def route_after_planning(state: AgentState) -> str:
    if state.get("search_axes"):
        return "retrieve"

    return "abstain"


def route_after_evaluation(state: AgentState) -> str:
    decision = state.get("evidence_decision")

    if decision == "ANSWER" and state.get("evidence_sufficient"):
        return "answer"

    if decision == "CLARIFY":
        return "clarify"

    if decision == "RETRIEVE_MORE":
        attempts = state.get("retrieval_attempts", 0)

        if attempts < MAX_RETRIEVAL_ATTEMPTS:
            return "refine_retrieval"

        return "abstain"

    return "abstain"


def route_after_refinement(state: AgentState) -> str:
    if state.get("retrieval_refinement_error"):
        return "abstain"

    return "retrieve"


def build_agent_graph(
    retriever: Any,
    llm: Any,
    tracer: Any = None,
    progress_callback: Any = None,
):
    graph = StateGraph(AgentState)

    def router_node(state: AgentState):
        return route_intent(state, llm)

    def general_answer_node(state: AgentState):
        return generate_general_answer(state, llm)

    def context_node(state: AgentState):
        return resolve_context(state, llm)

    def planner_node(state: AgentState):
        conversation_id = state.get("conversation_id")
        if not conversation_id:
            raise ValueError("conversation_id est obligatoire.")

        available_doc_types = retriever.vs.available_document_types(
            conversation_id
        )
        return plan_retrieval(state, llm, available_doc_types)

    def retrieval_node(state: AgentState):
        return retrieve_documents(state, retriever, tracer)

    def evidence_node(state: AgentState):
        return build_evidence(state, retriever)

    def evaluator_node(state: AgentState):
        return evaluate_evidence(state, llm)

    def refinement_node(state: AgentState):
        try:
            return refine_retrieval(state, llm)
        except ValueError as exc:
            return {
                "retrieval_refinement_error": str(exc),
            }

    def answer_node(state: AgentState):
        return generate_answer(state, llm)

    def citation_node(state: AgentState):
        return validate_citations(state)

    def clarification_node(state: AgentState):
        return finalize_clarification(state)

    def abstention_node(state: AgentState):
        return finalize_abstention(state)

    def out_of_scope_node(state: AgentState):
        return finalize_out_of_scope(state)

    labels = {
        "router": "Comprendre la demande",
        "general_answer": "Préparer une réponse générale",
        "resolve_context": "Résoudre le contexte de la conversation",
        "plan_retrieval": "Planifier la recherche documentaire",
        "retrieve": "Rechercher dans les documents indexés",
        "build_evidence": "Assembler les passages utiles",
        "evaluate": "Évaluer les preuves disponibles",
        "refine_retrieval": "Préciser la recherche",
        "answer": "Rédiger la réponse avec les sources",
        "validate_citations": "Vérifier les références documentaires",
        "clarify": "Préparer une demande de précision",
        "abstain": "Préparer une réponse prudente",
        "out_of_scope": "Répondre sur le périmètre de l'assistant",
    }

    def add_tracked_node(name: str, node: Any) -> None:
        def emit(status: str, **extra) -> None:
            if progress_callback is not None:
                progress_callback({
                    "type": "step",
                    "id": name,
                    "label": labels[name],
                    "status": status,
                    **extra,
                })

        def tracked(state: AgentState):
            emit("running")
            try:
                result = node(state)
            except Exception:
                emit("error", detail="Cette étape n'a pas pu aboutir.")
                raise
            emit("done")
            return result

        graph.add_node(name, tracked)

    add_tracked_node("router", router_node)
    add_tracked_node("general_answer", general_answer_node)
    add_tracked_node("resolve_context", context_node)
    add_tracked_node("plan_retrieval", planner_node)
    add_tracked_node("retrieve", retrieval_node)
    add_tracked_node("build_evidence", evidence_node)
    add_tracked_node("evaluate", evaluator_node)
    add_tracked_node("refine_retrieval", refinement_node)
    add_tracked_node("answer", answer_node)
    add_tracked_node("validate_citations", citation_node)
    add_tracked_node("clarify", clarification_node)
    add_tracked_node("abstain", abstention_node)
    add_tracked_node("out_of_scope", out_of_scope_node)

    graph.add_edge(START, "router")

    graph.add_conditional_edges(
        "router",
        route_after_intent,
        {
            "general_answer": "general_answer",
            "plan_retrieval": "plan_retrieval",
            "resolve_context": "resolve_context",
            "clarify": "clarify",
            "abstain": "abstain",
            "out_of_scope": "out_of_scope",
        },
    )

    graph.add_edge("general_answer", END)

    graph.add_conditional_edges(
        "resolve_context",
        route_after_context,
        {
            "plan_retrieval": "plan_retrieval",
            "clarify": "clarify",
        },
    )

    graph.add_conditional_edges(
        "plan_retrieval",
        route_after_planning,
        {
            "retrieve": "retrieve",
            "abstain": "abstain",
        },
    )
    graph.add_edge("retrieve", "build_evidence")
    graph.add_edge("build_evidence", "evaluate")

    graph.add_conditional_edges(
        "evaluate",
        route_after_evaluation,
        {
            "answer": "answer",
            "clarify": "clarify",
            "refine_retrieval": "refine_retrieval",
            "abstain": "abstain",
        },
    )

    graph.add_conditional_edges(
        "refine_retrieval",
        route_after_refinement,
        {
            "retrieve": "retrieve",
            "abstain": "abstain",
        },
    )

    graph.add_edge("answer", "validate_citations")
    graph.add_edge("validate_citations", END)

    graph.add_edge("clarify", END)
    graph.add_edge("abstain", END)

    return graph.compile()
