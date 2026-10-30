
from typing import Any, Sequence

import numpy as np
from sentence_transformers import SentenceTransformer


DEFAULT_MODEL_NAME = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
EMBEDDING_DIMENSION = 384


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
        batch_size: int = 32,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size doit être supérieur ou égal à 1.")

        self.model_name = model_name
        self.batch_size = batch_size
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        # Chargement paresseux : le modèle n'est chargé qu'à la première
        # demande d'embedding, puis réutilisé.
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Tous les textes à vectoriser doivent être non vides.")

        embeddings = self.model.encode(
            list(texts),
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
                f"attendu : {expected_shape}."
            )

        if not np.isfinite(embeddings).all():
            raise ValueError("Les embeddings contiennent des valeurs non finies.")

        return embeddings.tolist()

    def embed_chunks(
        self, chunks: Sequence[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not chunks:
            return []

        # L'embedding représente le type de document, le chapitre,
        # les titres de page et le texte du chunk.
        embedding_texts = [
            build_embedding_text(chunk) for chunk in chunks
        ]

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
