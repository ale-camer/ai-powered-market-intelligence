"""Repository layer for vector embedding storage and similarity search."""

import math

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from market_intel.loaders.models import EnrichedSignalModel


def compute_cosine_similarity(vec1: list[float] | None, vec2: list[float] | None) -> float:
    """Compute cosine similarity between two float vectors.

    Cosine similarity = (A . B) / (||A|| * ||B||)
    Range: [-1.0, 1.0]

    Args:
        vec1: First float vector.
        vec2: Second float vector.

    Returns:
        Cosine similarity score as float, 0.0 if vectors are empty or orthogonal.
    """
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))
    norm_a = math.sqrt(sum(a * a for a in vec1))
    norm_b = math.sqrt(sum(b * b for b in vec2))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot_product / (norm_a * norm_b)


class EmbeddingRepository:
    """Asynchronous repository for storing and querying document embeddings."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with an active AsyncSession.

        Args:
            session: SQLAlchemy AsyncSession.
        """
        self.session = session

    async def upsert(self, signal: EnrichedSignalModel) -> EnrichedSignalModel:
        """Insert or update an enriched signal and its embedding.

        Args:
            signal: EnrichedSignalModel instance to upsert.

        Returns:
            The merged and persisted EnrichedSignalModel instance.
        """
        merged_signal = await self.session.merge(signal)
        await self.session.flush()
        return merged_signal

    async def similarity_search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        symbol: str | None = None,
        signal_type: str | None = None,
    ) -> list[tuple[EnrichedSignalModel, float]]:
        """Perform a cosine similarity search returning top-K results.

        Args:
            query_embedding: The query vector (1536 dimensions for OpenAI embeddings).
            top_k: Maximum number of closest matches to return (default: 5).
            symbol: Optional ticker symbol filter.
            signal_type: Optional signal type filter.

        Returns:
            List of tuples (EnrichedSignalModel, similarity_score) sorted descending by score.
        """
        bind = self.session.get_bind()
        is_postgres = bind is not None and bind.dialect.name == "postgresql"

        if is_postgres:
            # Native pgvector cosine distance operator <=>
            # distance = 1 - cosine_similarity (for normalized vectors)
            distance_expr = EnrichedSignalModel.embedding.cosine_distance(query_embedding).label(
                "distance"
            )
            stmt = select(EnrichedSignalModel, distance_expr).where(
                EnrichedSignalModel.embedding.is_not(None)
            )

            if symbol:
                stmt = stmt.where(EnrichedSignalModel.symbol == symbol)
            if signal_type:
                stmt = stmt.where(EnrichedSignalModel.signal_type == signal_type)

            stmt = stmt.order_by("distance").limit(top_k)
            result = await self.session.execute(stmt)

            return [(row[0], float(1.0 - row[1])) for row in result.all()]

        # Non-PostgreSQL fallback (e.g. SQLite in unit tests): Python in-memory cosine ranking
        stmt_fallback = select(EnrichedSignalModel).where(
            EnrichedSignalModel.embedding.is_not(None)
        )
        if symbol:
            stmt_fallback = stmt_fallback.where(EnrichedSignalModel.symbol == symbol)
        if signal_type:
            stmt_fallback = stmt_fallback.where(EnrichedSignalModel.signal_type == signal_type)

        result_fallback = await self.session.execute(stmt_fallback)
        signals = result_fallback.scalars().all()

        scored: list[tuple[EnrichedSignalModel, float]] = []
        for sig in signals:
            score = compute_cosine_similarity(sig.embedding, query_embedding)
            scored.append((sig, score))

        # Sort descending by similarity score
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
