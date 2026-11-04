"""
Client LLM multi-fournisseurs (OpenAI, Anthropic, Gemini).

La clé API arrive avec chaque requête, vit dans cet objet en mémoire le temps
du tour, et n'est jamais écrite sur disque, ni dans l'état du graphe, ni dans
les logs. Ne jamais afficher une exception du fournisseur telle quelle : son
message peut contenir un fragment de la clé.
"""

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

SUPPORTED_PROVIDERS = ("openai", "anthropic", "gemini")


class LLMOutputError(Exception):
    """Le modèle n'a pas produit de sortie structurée exploitable."""


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    api_key: str = field(repr=False)  # exclue de repr(), donc des logs

    def __post_init__(self) -> None:
        if self.provider not in SUPPORTED_PROVIDERS:
            raise ValueError("Fournisseur LLM non supporté")
        if not self.model.strip():
            raise ValueError("Modèle LLM manquant")
        if not self.api_key.strip():
            raise ValueError("Clé API manquante")


def _build_chat_model(cfg: LLMConfig, with_temperature: bool) -> Any:
    temp: dict[str, Any] = {"temperature": 0} if with_temperature else {}

    if cfg.provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=cfg.model, api_key=cfg.api_key, timeout=90, max_retries=1, **temp
        )

    if cfg.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=cfg.model,
            api_key=cfg.api_key,
            timeout=90,
            max_retries=1,
            max_tokens=4096,
            **temp,
        )

    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=cfg.model, google_api_key=cfg.api_key, max_retries=1, timeout=90, **temp
    )


class LLM:
    """Interface minimale utilisée par les nœuds : `structured()`."""

    def __init__(self, cfg: LLMConfig) -> None:
        self._cfg = cfg
        self._use_temperature = True
        self._chat = _build_chat_model(cfg, True)

    def _invoke(self, call):
        try:
            return call()
        except Exception as exc:
            # Certains modèles (raisonnement) refusent temperature=0 : on réessaie sans.
            if self._use_temperature and "temperature" in str(exc).lower():
                self._use_temperature = False
                self._chat = _build_chat_model(self._cfg, False)
                return call()
            raise

    def structured(
        self,
        schema: type[BaseModel],
        system: str,
        messages: list[dict[str, str]],
        retries: int = 1,
    ) -> BaseModel:
        msgs = [("system", system)] + [(m["role"], m["content"]) for m in messages]

        for _ in range(retries + 1):
            try:
                out = self._invoke(
                    lambda: self._chat.with_structured_output(schema).invoke(msgs)
                )
            except (ValidationError, ValueError):
                continue

            if isinstance(out, schema):
                return out
            if isinstance(out, dict):
                try:
                    return schema.model_validate(out)
                except ValidationError:
                    continue

        raise LLMOutputError("Sortie structurée du modèle inexploitable") from None