import json
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .state import AgentState
from .llm import LLM

MAX_RETRIEVAL_ITERATIONS = 2


class SupportingPage(BaseModel):
    document_id: str
    page_number: int


class AxisAssessment(BaseModel):
    axis: str
    status: Literal["covered", "partial", "absent", "contradictory"]
    finding: str = Field(
        description="Fait trouvé avec document et page, ou ce qui manque exactement."
    )


class EvidenceAssessment(BaseModel):
    # L'analyse AVANT la décision : l'ordre des champs = ordre de génération.
    axes: list[AxisAssessment] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    reason: str

    decision: Literal["ANSWER", "RETRIEVE_MORE", "CLARIFY", "ABSTAIN"]

    supporting_pages: list[SupportingPage] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    follow_up_queries: list[str] = Field(default_factory=list)
    clarification_question: str = ""

    @model_validator(mode="after")
    def _coherence(self):
        if self.decision == "ANSWER" and not self.supporting_pages:
            raise ValueError("ANSWER exige au moins une page dans supporting_pages.")
        if self.decision == "RETRIEVE_MORE" and not self.follow_up_queries:
            raise ValueError("RETRIEVE_MORE exige des follow_up_queries.")
        if self.decision == "CLARIFY" and not self.clarification_question.strip():
            raise ValueError("CLARIFY exige une clarification_question.")
        return self


EVIDENCE_EVALUATOR_SYSTEM = """
Tu es l'évaluateur de preuves d'un système de questions-réponses sur des
contrats d'assurance habitation. Tu ne réponds JAMAIS à la question : tu juges
si les pages fournies permettent d'y répondre de façon fiable, et tu décides
de la suite.

## Entrées
- question_originale : ce que l'utilisateur a demandé. Elle prime en cas de
  divergence avec la reformulation.
- question_contextualisee : la question rendue autonome avec l'historique.
- axes_de_recherche : les aspects à couvrir.
- pages : contenus COMPLETS (pas seulement les chunks qui ont déclenché la
  récupération). Lis chaque page en entier : exceptions, notes et tableaux
  peuvent se trouver loin de l'extrait.
- documents_disponibles : documents réellement ingérés pour ce contrat.
- requetes_deja_executees et iteration : historique de recherche.
- date_du_jour : pour tout raisonnement temporel.

## Méthode
1. Pour chaque axe, cherche la réponse dans les pages, avec document et page.
2. Distingue ce qui est écrit de ce qui est déduit. Un calcul simple sur des
   valeurs écrites est permis (ex. 20 % de 3 000 €). Une valeur absente des
   pages (indice de référence, taux de vétusté, montant non indiqué) est une
   information MANQUANTE : ne la complète jamais de mémoire.
3. Absence et négation :
   - Une garantie listée comme non souscrite, un plafond à 0 € ou une
     exclusion explicite sont des RÉPONSES, pas des lacunes.
   - Le simple silence des passages récupérés n'est pas un « non ».
4. Hiérarchie : les Conditions Particulières priment sur les Conditions
   Générales quand elles se contredisent ; les CG complètent les CP quand
   celles-ci renvoient à elles. Ne présente jamais une règle générale comme
   un chiffre propre au contrat. <à adapter : place des avenants et annexes>
5. Contradictions : si deux passages se contredisent, ne tranche pas
   arbitrairement. Liste le conflit (avec pages) dans contradictions. Une
   contradiction sur un point déterminant n'impose pas ABSTAIN : si les deux
   passages sont en main, décide ANSWER et la réponse devra présenter les deux.
6. Temps et portée : vérifie que le fait vaut à la date de l'événement
   (date d'effet, périodes saisonnières) et pour la garantie visée.

## Décisions
ANSWER : le cœur de la question est couvert et chaque fait que la réponse
utilisera est dans les pages. Renseigne supporting_pages. Les lacunes non
critiques vont dans limitations (la réponse devra les dire).
RETRIEVE_MORE : l'information manquante est probablement dans un document de
documents_disponibles non encore exploré pour ce point. Renseigne
follow_up_queries : courtes, ciblées (terme exact du contrat), différentes de
requetes_deja_executees. Pas de reformulation cosmétique d'une requête passée.
CLARIFY : la réponse change selon une circonstance que l'utilisateur n'a pas
donnée (ex. dégât chez lui ou chez le voisin) ET tu ne peux pas répondre en
énumérant les cas. Une seule question, précise. Si la circonstance figure dans
l'historique, ne demande pas.
ABSTAIN : l'information n'est dans aucun document disponible, ou une recherche
complémentaire a déjà été faite sur ce point sans résultat. Liste
missing_information.

Sois exigeant : n'utilise ANSWER que si tu pourrais citer la page de chaque
fait. Ne confonds pas la proximité lexicale avec une preuve : « plafond »
dans une page ne répond pas à « quel plafond pour ce sinistre ».

## Exemples
- « Mon PC portable est tombé » : la page liste « Bris de matériel
  informatique » parmi les options non souscrites → ANSWER (non couvert).
- « Mon plafond RC en euros ? » : la page donne 3 000 × indice FFB, la valeur
  de l'indice est absente → ANSWER avec limitations: ["valeur de l'indice
  absente des documents"]. Ne calcule pas de montant.
- « Mon taux de vétusté ? » : les CP parlent de valeur d'usage sans taux, les
  CG sont disponibles et n'ont pas été interrogées sur la vétusté →
  RETRIEVE_MORE ; si déjà interrogées sans résultat → ABSTAIN.

## Interdictions
Aucune connaissance externe sur l'assurance ou d'autres contrats. Aucun
chiffre, page ou citation inventés. Ne rédige pas la réponse finale.
"""


def _render_pages(pages: list[dict[str, Any]]) -> str:
    blocks = []
    for i, p in enumerate(pages, 1):
        titles = p.get("titles") or []
        axes = p.get("matched_axes") or []
        header = (
            f'<page n="{i}" document_id="{p.get("document_id")}" '
            f'document_name="{p.get("document_name")}" '
            f'document_type="{p.get("document_type")}" '
            f'chapter="{p.get("chapter")}" page_number="{p.get("page_number")}" '
            f'titles="{" > ".join(map(str, titles))}" '
            f'matched_axes="{" | ".join(map(str, axes))}">'
        )
        blocks.append(f"{header}\n{p.get('page_content', '')}\n</page>")
    return "\n\n".join(blocks)


def _norm(q: str) -> str:
    return " ".join(q.casefold().split())


def _empty_result(decision: str, **kw) -> dict[str, Any]:
    base = {
        "evidence_decision": decision,
        "evidence_sufficient": decision == "ANSWER",
        "missing_information": [],
        "clarification_question": "",
        "evidence_evaluation_reason": "",
        "follow_up_queries": [],
        "supporting_pages": [],
        "axis_assessments": [],
        "limitations": [],
        "contradictions": [],
    }
    base.update(kw)
    return base


def evaluate_evidence(state: AgentState, llm: LLM) -> dict[str, Any]:
    original_question = state.get("original_question", "").strip()
    resolved_question = state.get("resolved_question", "").strip()
    question = resolved_question or original_question
    if not question:
        raise ValueError("Aucune question à évaluer.")

    pages = state.get("retrieved_pages", [])
    if not pages:
        return _empty_result(
            "ABSTAIN",
            missing_information=["Aucune preuve documentaire disponible."],
            evidence_evaluation_reason="Aucune page récupérée.",
        )

    executed = state.get("executed_queries", [])
    iteration = state.get(
        "retrieval_iteration",
        max(0, state.get("retrieval_attempts", 1) - 1),
    )

    context = (
        f"date_du_jour : {date.today().isoformat()}\n"
        f"iteration : {iteration}/{MAX_RETRIEVAL_ITERATIONS}\n"
        f"question_originale : {original_question or question}\n"
        f"question_contextualisee : {resolved_question or question}\n"
        f"axes_de_recherche : {json.dumps(state.get('search_axes', []), ensure_ascii=False)}\n"
        f"documents_disponibles : {json.dumps(state.get('available_documents', []), ensure_ascii=False)}\n"
        f"requetes_deja_executees : {json.dumps(executed, ensure_ascii=False)}\n\n"
        f"<pages>\n{_render_pages(pages)}\n</pages>"
    )

    result = llm.structured(
        schema=EvidenceAssessment,
        system=EVIDENCE_EVALUATOR_SYSTEM,
        messages=[{"role": "user", "content": context}],
        retries=1,
    )
    if not isinstance(result, EvidenceAssessment):
        raise TypeError("Le LLM doit retourner un EvidenceAssessment.")

    decision = result.decision
    follow_ups = result.follow_up_queries

    available_pages = {
        (str(page.get("document_id")), page.get("page_number"))
        for page in pages
    }
    supporting_pages = []
    seen_supporting_pages = set()
    for page in result.supporting_pages:
        key = (page.document_id, page.page_number)
        if key in available_pages and key not in seen_supporting_pages:
            supporting_pages.append(page.model_dump())
            seen_supporting_pages.add(key)

    missing_information = list(result.missing_information)
    reason = result.reason
    if decision == "ANSWER" and not supporting_pages:
        decision = "ABSTAIN"
        missing_information.append(
            "L'évaluateur n'a pas désigné de page d'appui parmi les pages récupérées."
        )
        reason = (
            f"{reason} Les pages d'appui proposées ne correspondent pas "
            "aux preuves disponibles."
        )

    # Garde-fou déterministe contre les boucles de recherche.
    if decision == "RETRIEVE_MORE":
        seen = {
            _norm(q.get("query", "") if isinstance(q, dict) else q)
            for q in executed
        }
        follow_ups = [q for q in follow_ups if _norm(q) not in seen]
        if not follow_ups or iteration >= MAX_RETRIEVAL_ITERATIONS:
            decision = "ABSTAIN"
            missing_information.append(
                "Aucune nouvelle recherche complémentaire ne peut être exécutée."
            )

    return _empty_result(
        decision,
        missing_information=missing_information,
        clarification_question=result.clarification_question,
        evidence_evaluation_reason=reason,
        follow_up_queries=follow_ups if decision == "RETRIEVE_MORE" else [],
        supporting_pages=supporting_pages if decision == "ANSWER" else [],
        axis_assessments=[axis.model_dump() for axis in result.axes],
        limitations=result.limitations,
        contradictions=result.contradictions,
    )