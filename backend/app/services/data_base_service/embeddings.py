import os
from functools import lru_cache
from typing import Any, Sequence

import numpy as np
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

# Les constantes ci-dessous sont lues à l'import : le .env doit déjà être chargé.
load_dotenv()


# bge-m3 : multilingue, contexte long, 1024 dimensions, sans préfixe.
# Alternative plus légère : intfloat/multilingual-e5-base (768 dimensions,
# préfixes "query: " / "passage: " gérés automatiquement ci-dessous).
# Changer de modèle impose de supprimer les index LanceDB existants et de
# réindexer les documents : les dimensions ne sont pas compatibles.
DEFAULT_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1024"))
MAX_SEQ_LENGTH = 512


def build_embedding_text(chunk: dict[str, Any]) -> str:
    """
    Construit le texte contextuel utilisé pour calculer l'embedding.
    Le texte original du chunk reste inchangé dans chunk_text.
    """
    document_type = (
        chunk.get("document_type")
        or chunk.get("document_name")
        or "Type de document inconnu"
    )

    chapter = chunk.get("chapter") or "Chapitre non identifié"

    titles = chunk.get("titles") or []
    if not isinstance(titles, list) or not all(
        isinstance(title, str) for title in titles
    ):
        raise ValueError("Le champ 'titles' doit être une liste de chaînes.")

    chunk_text = chunk.get("chunk_text")
    if not isinstance(chunk_text, str) or not chunk_text.strip():
        raise ValueError("Le champ 'chunk_text' est vide ou invalide.")

    titles_text = " > ".join(title.strip() for title in titles if title.strip())

    return (
        f"Type de document : {document_type}\n"
        f"Chapitre : {chapter}\n"
        f"Titres de la page : {titles_text or 'Titre non identifié'}\n"
        f"Texte : {chunk_text.strip()}"
    )


class EmbeddingService:
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        *,
        batch_size: int = 16,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size doit être supérieur ou égal à 1.")

        self.model_name = model_name
        self.batch_size = batch_size
        self._model: SentenceTransformer | None = None

        # Les modèles E5 exigent des préfixes ; bge-m3 n'en veut pas.
        if "e5" in model_name.lower():
            self.query_prefix, self.passage_prefix = "query: ", "passage: "
        else:
            self.query_prefix = self.passage_prefix = ""

    @property
    def model(self) -> SentenceTransformer:
        # Chargement paresseux : le modèle n'est chargé qu'à la première
        # demande d'embedding, puis réutilisé.
        if self._model is None:
            model = SentenceTransformer(self.model_name)
            # Plafonne la longueur : 512 tokens couvrent un chunk de 1800 caractères.
            model.max_seq_length = min(model.max_seq_length or MAX_SEQ_LENGTH, MAX_SEQ_LENGTH)
            self._model = model
        return self._model

    def embed_texts(
        self, texts: Sequence[str], *, is_query: bool = False
    ) -> list[list[float]]:
        if not texts:
            return []

        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Tous les textes à vectoriser doivent être non vides.")

        prefix = self.query_prefix if is_query else self.passage_prefix
        embeddings = self.model.encode(
            [prefix + text for text in texts],
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        embeddings = np.asarray(embeddings, dtype=np.float32)

        expected_shape = (len(texts), EMBEDDING_DIMENSION)
        if embeddings.shape != expected_shape:
            raise ValueError(
                f"Dimensions d'embeddings invalides : {embeddings.shape}; "
                f"attendu : {expected_shape}. Vérifie EMBEDDING_DIMENSION."
            )

        if not np.isfinite(embeddings).all():
            raise ValueError("Les embeddings contiennent des valeurs non finies.")

        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text], is_query=True)[0]

    def embed_chunks(
        self, chunks: Sequence[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not chunks:
            return []

        # L'embedding représente le type de document, le chapitre,
        # les titres de page et le texte du chunk.
        embedding_texts = [build_embedding_text(chunk) for chunk in chunks]

        embeddings = self.embed_texts(embedding_texts)

        # On conserve toutes les métadonnées et le texte original.
        return [
            {
                **chunk,
                "embedding_text": embedding_text,
                "embedding": embedding,
            }
            for chunk, embedding_text, embedding in zip(
                chunks, embedding_texts, embeddings
            )
        ]


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    """Instance unique partagée (ingestion + agent) : un seul modèle en mémoire."""
    return EmbeddingService()