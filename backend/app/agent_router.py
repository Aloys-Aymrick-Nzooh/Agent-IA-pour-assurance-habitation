
import json
import logging
import os
import time
import uuid

from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Any, Callable

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.ai_agent_service.graph import build_agent_graph
from app.services.ai_agent_service.retrieval_algorithm import (
    HybridRetriever,
    Reranker,
)
from app.services.ai_agent_service.llm import LLM, LLMConfig
from app.services.ai_agent_service.config import (
    CONVERSATIONS_PATH,
    DOCUMENT_TYPE_DIRS,
)
from app.services.data_base_service.vector_store import VectorStore


logger = logging.getLogger("uvicorn.error")

router = APIRouter(
    prefix="/conversations",
    tags=["agent"],
)

# Le reranker est partagé entre les requêtes.
reranker = Reranker()

# Verrous locaux par conversation.
_conversation_locks: dict[str, Lock] = {}
_progress_callback: ContextVar[Callable[[dict[str, Any]], None] | None] = ContextVar(
    "agent_progress_callback",
    default=None,
)


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_conversation_lock(conversation_id: str) -> Lock:
    """Return a process-local lock for one conversation."""

    lock = _conversation_locks.get(conversation_id)

    if lock is None:
        lock = Lock()
        _conversation_locks[conversation_id] = lock

    return lock


def _get_conversation_dir(conversation_id: uuid.UUID) -> Path:
    """Return the directory of an existing conversation."""

    conversation_dir = CONVERSATIONS_PATH / str(conversation_id)
    metadata_path = conversation_dir / "conversation.json"

    if not metadata_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    try:
        metadata = json.loads(
            metadata_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to read conversation metadata",
        ) from exc

    if (
        not isinstance(metadata, dict)
        or metadata.get("conversation_id") != str(conversation_id)
    ):
        raise HTTPException(
            status_code=500,
            detail="Invalid conversation metadata",
        )

    return conversation_dir


def _list_indexed_documents(
    conversation_dir: Path,
    conversation_id: str,
    vector_store: VectorStore,
) -> list[dict[str, Any]]:
    indexed_types = set(
        vector_store.available_document_types(conversation_id)
    )
    documents = []
    documents_dir = conversation_dir / "documents"

    for document_type, type_dir in DOCUMENT_TYPE_DIRS.items():
        if document_type not in indexed_types:
            continue

        type_path = documents_dir / type_dir
        if not type_path.is_dir():
            continue

        for json_path in sorted(type_path.glob("*.json")):
            try:
                payload = json.loads(json_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                logger.warning("Skipping unreadable document metadata %s", json_path)
                continue

            pages = payload.get("pages", []) if isinstance(payload, dict) else []
            first_page = pages[0] if pages else None
            if not isinstance(first_page, dict):
                continue
            if (
                first_page.get("conversation_id") != conversation_id
                or first_page.get("document_type") != document_type
            ):
                continue

            documents.append({
                "document_id": first_page.get("document_id", json_path.stem),
                "filename": first_page.get("document_name", json_path.name),
                "document_type": document_type,
                "page_count": len(pages),
            })

    return documents


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file, returning an empty list if it does not exist."""

    if not path.exists():
        return []

    messages: list[dict[str, Any]] = []

    try:
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue

                item = json.loads(line)

                if isinstance(item, dict):
                    messages.append(item)

    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to read conversation history",
        ) from exc

    return messages


def _append_jsonl(
    path: Path,
    messages: list[dict[str, Any]],
) -> None:
    """Append messages to a JSONL file."""

    try:
        with path.open("a", encoding="utf-8") as file:
            for message in messages:
                file.write(
                    json.dumps(message, ensure_ascii=False) + "\n"
                )

    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to save conversation history",
        ) from exc


def _safe_trace_value(
    value: Any,
    depth: int = 0,
) -> Any:
    """
    Prepare values for trace storage.

    Secrets are excluded, long strings are truncated and collections
    are limited to avoid oversized trace files.
    """

    if depth > 6:
        return "[profondeur maximale atteinte]"

    if isinstance(value, dict):
        safe_dict = {}

        for key, item in value.items():
            key_string = str(key)
            normalized_key = key_string.lower()

            if any(
                secret in normalized_key
                for secret in (
                    "api_key",
                    "apikey",
                    "password",
                    "secret",
                    "token",
                    "authorization",
                )
            ):
                safe_dict[key_string] = "[masqué]"
                continue

            safe_dict[key_string] = _safe_trace_value(
                item,
                depth + 1,
            )

        return safe_dict

    if isinstance(value, (list, tuple)):
        items = [
            _safe_trace_value(item, depth + 1)
            for item in value[:20]
        ]

        if len(value) > 20:
            items.append(
                f"[{len(value) - 20} éléments supplémentaires]"
            )

        return items

    if isinstance(value, str):
        max_length = 2000

        if len(value) > max_length:
            return (
                value[:max_length]
                + f"... [texte tronqué, {len(value)} caractères]"
            )

        return value

    if value is None or isinstance(value, (bool, int, float)):
        return value

    return str(value)


def _append_trace_event(
    trace_path: Path,
    event: dict[str, Any],
) -> None:
    """
    Append one event to the conversation trace.

    A trace failure must not prevent the agent from answering.
    """

    try:
        with trace_path.open("a", encoding="utf-8") as file:
            file.write(
                json.dumps(
                    _safe_trace_value(event),
                    ensure_ascii=False,
                )
                + "\n"
            )

    except OSError:
        logger.exception(
            "Unable to write agent trace: %s",
            trace_path,
        )


def _trace_state_snapshot(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Return the useful state fields for debugging."""

    fields = (
        "original_question",
        "resolved_question",
        "available_documents",
        "intent",
        "route_reason",
        "needs_clarification",
        "clarification_question",
        "general_answer_reason",
        "doc_types",
        "search_query",
        "context_resolution_reason",
        "retrieval_plan_reason",
        "retrieval_attempts",
        "retrieval_results",
        "retrieved_pages",
        "search_trace",
        "missing_information",
        "retrieval_refinement_reason",
        "retrieval_refinement_error",
        "evidence_decision",
        "evidence_evaluation_reason",
        "evidence_sufficient",
        "answer",
        "citations",
        "citations_validated",
        "limitations",
    )

    return {
        field: state[field]
        for field in fields
        if field in state
    }


def _get_routing_decision(
    node_name: str,
    state: dict[str, Any],
) -> str | None:
    """Describe the conditional routing decision after a node."""

    if node_name == "router":
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

    if node_name == "plan_retrieval":
        return "retrieve" if state.get("doc_types") else "abstain"

    if node_name == "resolve_context":
        if state.get("needs_clarification"):
            return "clarify"

        return "plan_retrieval"

    if node_name == "evaluate":
        decision = state.get("evidence_decision")

        if (
            decision == "ANSWER"
            and state.get("evidence_sufficient")
        ):
            return "answer"

        if decision == "CLARIFY":
            return "clarify"

        if decision == "RETRIEVE_MORE":
            if state.get("retrieval_attempts", 0) < 3:
                return "refine_retrieval"

            return "abstain"

        return "abstain"

    if node_name == "refine_retrieval":
        if state.get("retrieval_refinement_error"):
            return "abstain"

        return "retrieve"

    return None


def _progress_detail(
    node_name: str,
    node_output: Any,
    state: dict[str, Any],
) -> str:
    output = node_output if isinstance(node_output, dict) else {}

    if node_name == "router":
        return f"Intention : {state.get('intent', 'non déterminée')}."

    if node_name == "resolve_context":
        return "Question contextualisée pour la recherche."

    if node_name == "plan_retrieval":
        types = ", ".join(state.get("doc_types", [])) or "aucun type"
        return f"Documents ciblés : {types}. {_short_progress_text(output.get('retrieval_plan_reason', ''))}"

    if node_name == "retrieve":
        count = len(output.get("retrieval_results", []))
        return f"{count} passage(s) retrouvé(s) dans les documents indexés."

    if node_name == "build_evidence":
        pages = output.get("retrieved_pages", [])
        passage_count = sum(len(page.get("passages", [])) for page in pages)
        return f"Preuves assemblées : {passage_count} passage(s) sur {len(pages)} page(s)."

    if node_name == "evaluate":
        decisions = {
            "ANSWER": "Les preuves sont jugées suffisantes.",
            "RETRIEVE_MORE": "Les preuves sont incomplètes; une recherche complémentaire est lancée.",
            "CLARIFY": "Une précision est nécessaire.",
            "ABSTAIN": "Les documents ne permettent pas de conclure.",
        }
        decision = state.get("evidence_decision")
        summary = decisions.get(decision, "Les preuves ont été évaluées.")
        reason = state.get("evidence_evaluation_reason", "")
        return f"{summary} {_short_progress_text(reason)}".strip()

    if node_name == "refine_retrieval":
        return _short_progress_text(output.get("retrieval_refinement_reason", "Recherche affinée."))

    if node_name == "answer":
        return f"Réponse préparée avec {len(state.get('citations', []))} citation(s)."

    if node_name == "validate_citations":
        return f"{len(output.get('citations', []))} référence(s) vérifiée(s)."

    if node_name == "general_answer":
        return "Réponse générale préparée sans recherche dans le contrat."

    return "Étape terminée."


def _short_progress_text(value: Any, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        return text[:limit].rstrip() + "…"
    return text


def _execute_graph_with_trace(
    graph: Any,
    initial_state: dict[str, Any],
    trace_path: Path,
    conversation_id: str,
) -> dict[str, Any]:
    """
    Execute the graph using streaming updates and persist each node output.
    """

    current_state = dict(initial_state)
    previous_event_time = time.perf_counter()

    _append_trace_event(
        trace_path,
        {
            "event": "execution_started",
            "timestamp": _timestamp(),
            "conversation_id": conversation_id,
            "question": initial_state.get("original_question"),
        },
    )
    logger.info(
        "Agent execution started for conversation %s",
        conversation_id,
    )

    try:
        for update in graph.stream(
            initial_state,
            stream_mode="updates",
        ):
            for node_name, node_output in update.items():
                node_started = time.perf_counter()

                if isinstance(node_output, dict):
                    current_state.update(node_output)

                routing_decision = _get_routing_decision(
                    node_name,
                    current_state,
                )

                event = {
                    "event": "node_completed",
                    "timestamp": _timestamp(),
                    "conversation_id": conversation_id,
                    "node": node_name,
                    "duration_since_previous_event_ms": round(
                        (node_started - previous_event_time) * 1000,
                        2,
                    ),
                    "output": node_output,
                    "routing_decision": routing_decision,
                    "state_snapshot": _trace_state_snapshot(
                        current_state
                    ),
                }

                _append_trace_event(trace_path, event)
                logger.info(
                    "Agent step completed: %s (conversation %s; next=%s; output=%s)",
                    node_name,
                    conversation_id,
                    routing_decision or "end",
                    json.dumps(
                        _safe_trace_value(node_output),
                        ensure_ascii=False,
                    ),
                )
                progress_callback = _progress_callback.get()
                if progress_callback is not None:
                    progress_callback({
                        "type": "step",
                        "id": node_name,
                        "status": "done",
                        "detail": _progress_detail(
                            node_name,
                            node_output,
                            current_state,
                        ),
                    })

                previous_event_time = time.perf_counter()

        _append_trace_event(
            trace_path,
            {
                "event": "execution_completed",
                "timestamp": _timestamp(),
                "conversation_id": conversation_id,
                "final_intent": current_state.get("intent"),
                "final_answer": current_state.get("answer"),
                "citations": current_state.get("citations", []),
                "limitations": current_state.get("limitations", []),
            },
        )
        logger.info(
            "Agent execution completed for conversation %s",
            conversation_id,
        )

        return current_state

    except Exception as exc:
        _append_trace_event(
            trace_path,
            {
                "event": "execution_failed",
                "timestamp": _timestamp(),
                "conversation_id": conversation_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "state_snapshot": _trace_state_snapshot(
                    current_state
                ),
            },
        )

        raise


def _read_pending_clarification(
    conversation_dir: Path,
) -> dict[str, Any] | None:
    """Read the clarification currently waiting for a user response."""

    path = conversation_dir / "pending_clarification.json"

    if not path.is_file():
        return None

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to read pending clarification",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=500,
            detail="Invalid pending clarification",
        )

    return payload


def _write_pending_clarification(
    conversation_dir: Path,
    original_question: str,
    clarification_question: str,
    source: str | None = None,
) -> None:
    """Persist the clarification needed to continue the conversation."""

    path = conversation_dir / "pending_clarification.json"
    temporary_path = conversation_dir / "pending_clarification.tmp"

    payload = {
        "status": "waiting_for_clarification",
        "original_question": original_question,
        "clarification_question": clarification_question,
        "source": source,
        "updated_at": _timestamp(),
    }

    try:
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        os.replace(temporary_path, path)

    except OSError as exc:
        temporary_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=500,
            detail="Unable to save pending clarification",
        ) from exc


def _delete_pending_clarification(
    conversation_dir: Path,
) -> None:
    """Remove the clarification after a completed turn."""

    path = conversation_dir / "pending_clarification.json"

    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to clear pending clarification",
        ) from exc


def _build_llm(
    provider: str,
    model: str,
    api_key: str,
) -> LLM:
    """Build a request-scoped LLM client."""

    try:
        config = LLMConfig(
            provider=provider,
            model=model,
            api_key=api_key,
        )

        return LLM(config)

    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid LLM configuration",
        ) from exc


def _build_retriever(request: Request) -> HybridRetriever:
    """Build the hybrid retriever using shared application services."""

    vector_store: VectorStore = request.app.state.vector_store
    embedding_service = request.app.state.embedding_service

    return HybridRetriever(
        vector_store=vector_store,
        embedder=embedding_service,
        reranker=reranker,
    )


def _initial_state(
    conversation_id: str,
    question: str,
    conversation_history: list[dict[str, Any]],
    available_documents: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a fresh LangGraph state for the current user turn."""

    return {
        "conversation_id": conversation_id,
        "original_question": question,
        "conversation_history": conversation_history,
        "available_documents": available_documents,
        "retrieval_attempts": 0,
        "retrieval_results": [],
        "retrieved_pages": [],
        "search_trace": [],
        "missing_information": [],
        "citations": [],
        "limitations": [],
        "answer": "",
        "needs_clarification": False,
        "evidence_sufficient": False,
        "citations_validated": False,
    }


def _is_clarification_required(
    state: dict[str, Any],
) -> bool:
    """Determine whether the graph is asking the user for clarification."""

    if state.get("needs_clarification"):
        return True

    if state.get("evidence_decision") == "CLARIFY":
        return True

    return state.get("intent") == "CLARIFICATION"


def _get_clarification_question(
    state: dict[str, Any],
) -> str:
    """Extract the clarification prompt produced by the graph."""

    question = (
        state.get("clarification_question")
        or state.get("answer")
        or ""
    )

    return str(question).strip()


@router.post("/{conversation_id}/messages")
def post_message(
    conversation_id: uuid.UUID,
    body: MessageIn,
    request: Request,
    x_llm_provider: str = Header(...),
    x_llm_model: str = Header(...),
    x_llm_api_key: str = Header(...),
):
    """Send a message and execute the insurance analysis agent."""

    conversation_id_str = str(conversation_id)
    conversation_dir = _get_conversation_dir(conversation_id)

    with _get_conversation_lock(conversation_id_str):
        history_path = conversation_dir / "history.jsonl"
        trace_path = conversation_dir / "agent_trace.jsonl"

        history = _read_jsonl(history_path)
        pending = _read_pending_clarification(conversation_dir)

        user_content = body.content.strip()

        if not user_content:
            raise HTTPException(
                status_code=422,
                detail="Message content cannot be empty",
            )

        user_message = {
            "role": "user",
            "content": user_content,
            "created_at": _timestamp(),
        }
        pending_original_question = user_content

        if pending is not None:
            original_question = str(
                pending.get("original_question", "")
            ).strip()

            if not original_question:
                raise HTTPException(
                    status_code=500,
                    detail="Pending clarification has no original question",
                )

            pending_original_question = original_question
            question = (
                f"Question initiale : {original_question}\n\n"
                f"Précision de l'utilisateur : {user_content}"
            )

        else:
            question = user_content

        history_for_graph = history + [user_message]

        llm = _build_llm(
            provider=x_llm_provider,
            model=x_llm_model,
            api_key=x_llm_api_key,
        )

        retriever = _build_retriever(request)
        available_documents = _list_indexed_documents(
            conversation_dir,
            conversation_id_str,
            retriever.vs,
        )

        graph = build_agent_graph(
            retriever=retriever,
            llm=llm,
            progress_callback=_progress_callback.get(),
        )

        state = _initial_state(
            conversation_id=conversation_id_str,
            question=question,
            conversation_history=history_for_graph,
            available_documents=available_documents,
        )

        try:
            result = _execute_graph_with_trace(
                graph=graph,
                initial_state=state,
                trace_path=trace_path,
                conversation_id=conversation_id_str,
            )

        except Exception as exc:
            logger.exception(
                "Agent execution failed for conversation %s",
                conversation_id_str,
            )

            # On conserve la clarification en attente si le graphe échoue.
            raise HTTPException(
                status_code=500,
                detail="Unable to process the message",
            ) from exc

        answer = str(result.get("answer", "")).strip()

        if not answer:
            raise HTTPException(
                status_code=500,
                detail="The agent returned an empty answer",
            )

        assistant_message = {
            "role": "assistant",
            "content": answer,
            "created_at": _timestamp(),
            "citations": result.get("citations", []),
            "limitations": result.get("limitations", []),
        }

        _append_jsonl(
            history_path,
            [user_message, assistant_message],
        )

        if _is_clarification_required(result):
            clarification_question = _get_clarification_question(
                result
            )

            if not clarification_question:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "The agent requested clarification "
                        "without providing a question"
                    ),
                )

            _write_pending_clarification(
                conversation_dir=conversation_dir,
                original_question=pending_original_question,
                clarification_question=clarification_question,
                source=str(result.get("intent", "")) or None,
            )

            return {
                "conversation_id": conversation_id_str,
                "status": "waiting_for_clarification",
                "answer": answer,
                "clarification_question": clarification_question,
                "citations": result.get("citations", []),
                "limitations": result.get("limitations", []),
                "trace_file": "agent_trace.jsonl",
            }

        _delete_pending_clarification(conversation_dir)

        return {
            "conversation_id": conversation_id_str,
            "status": "completed",
            "answer": answer,
            "citations": result.get("citations", []),
            "limitations": result.get("limitations", []),
            "trace_file": "agent_trace.jsonl",
        }


@router.post("/{conversation_id}/messages/stream")
def stream_message(
    conversation_id: uuid.UUID,
    body: MessageIn,
    request: Request,
    x_llm_provider: str = Header(...),
    x_llm_model: str = Header(...),
    x_llm_api_key: str = Header(...),
):
    """Stream safe agent progress and the final response as server-sent events."""
    events: Queue[dict[str, Any] | None] = Queue()

    def run_message() -> None:
        token = _progress_callback.set(events.put)
        try:
            result = post_message(
                conversation_id,
                body,
                request,
                x_llm_provider,
                x_llm_model,
                x_llm_api_key,
            )
            events.put({"type": "answer", **result})
            events.put({"type": "done"})
        except HTTPException as exc:
            events.put({"type": "error", "message": str(exc.detail)})
        except Exception:
            logger.exception(
                "Streaming agent execution failed for conversation %s",
                conversation_id,
            )
            events.put({
                "type": "error",
                "message": "Unable to process the message",
            })
        finally:
            _progress_callback.reset(token)
            events.put(None)

    def event_stream():
        Thread(target=run_message, daemon=True).start()
        while True:
            try:
                event = events.get(timeout=15)
            except Empty:
                yield ": keep-alive\n\n"
                continue

            if event is None:
                break

            event_type = event.pop("type", "message")
            yield (
                f"event: {event_type}\n"
                f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{conversation_id}/messages")
def get_messages(
    conversation_id: uuid.UUID,
):
    """Return the persisted message history of a conversation."""

    conversation_dir = _get_conversation_dir(conversation_id)

    history = _read_jsonl(
        conversation_dir / "history.jsonl"
    )

    return {
        "conversation_id": str(conversation_id),
        "messages": history,
    }
