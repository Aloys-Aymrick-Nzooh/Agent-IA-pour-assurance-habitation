
from typing import Any, Sequence

import numpy as np
from sentence_transformers import SentenceTransformer


DEFAULT_MODEL_NAME = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
EMBEDDING_DIMENSION = 384


class EmbeddingService:
    """Generate local embeddings for document chunks."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        *,
        batch_size: int = 32,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")

        self.model_name = model_name
        self.batch_size = batch_size
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        """Load the model lazily and reuse it."""
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)

        return self._model

    def embed_texts(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        """Return one 384-dimensional embedding per input text."""
        if not texts:
            return []

        normalized_texts = []

        for text in texts:
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Embedding texts must be non-empty strings")

            normalized_texts.append(text.strip())

        embeddings = self.model.encode(
            normalized_texts,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        embeddings = np.asarray(embeddings, dtype=np.float32)

        expected_shape = (len(normalized_texts), EMBEDDING_DIMENSION)

        if embeddings.shape != expected_shape:
            raise ValueError(
                f"Unexpected embedding shape: {embeddings.shape}; "
                f"expected {expected_shape}"
            )

        if not np.isfinite(embeddings).all():
            raise ValueError("Embeddings contain non-finite values")

        return embeddings.tolist()

    def embed_chunks(
        self,
        chunks: Sequence[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Add an embedding to each chunk without altering its metadata."""
        texts = [chunk.get("chunk_text") for chunk in chunks]
        embeddings = self.embed_texts(texts)

        return [
            {
                **chunk,
                "embedding": embedding,
            }
            for chunk, embedding in zip(chunks, embeddings)
        ]
