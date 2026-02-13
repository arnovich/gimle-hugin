"""Artifact Query Engine for searching and retrieving artifacts."""

import logging
import re
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from gimle.hugin.artifacts.artifact import Artifact
    from gimle.hugin.storage.storage import Storage

logger = logging.getLogger(__name__)

# Scoring constants
PHRASE_MATCH_BONUS = 5.0
RATING_NEUTRAL = 3.0
RATING_BOOST_MULTIPLIER = 1.5


class ArtifactQueryResult:
    """Result from an artifact query.

    Attributes:
        artifact_id: The ID of the artifact.
        artifact_type: The type of the artifact.
        content_preview: The preview of the artifact content.
        score: The score of the artifact.
        metadata: The metadata of the artifact.
    """

    def __init__(
        self,
        artifact_id: str,
        artifact_type: str,
        content_preview: str,
        score: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize query result."""
        self.artifact_id = artifact_id
        self.artifact_type = artifact_type
        self.content_preview = content_preview
        self.score = score
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "content_preview": self.content_preview,
            "score": self.score,
            "metadata": self.metadata,
        }


class ArtifactQueryEngine:
    """
    Engine for querying artifacts stored in storage.

    Provides simple keyword-based search across artifact content.
    Can be extended later with more sophisticated search (embeddings, etc).

    Attributes:
        storage: The storage to use for the query engine.
    """

    def __init__(self, storage: "Storage"):
        """Initialize the query engine with a storage backend.

        Args:
            storage: The storage to use for the query engine.
        """
        self.storage = storage

    def query(
        self,
        query: str,
        limit: int = 10,
        artifact_type: Optional[str] = None,
    ) -> List[ArtifactQueryResult]:
        """
        Query artifacts using keyword search.

        Args:
            query: Search query string (keywords)
            limit: Maximum number of results to return
            artifact_type: Optional filter by artifact type (e.g., "Text")

        Returns:
            A list of ArtifactQueryResult objects, sorted by relevance score.
        """
        # Get all artifact IDs from storage
        artifact_ids = self.storage.list_artifacts()

        # Pre-load all ratings to avoid N+1 queries
        ratings_by_artifact = self._load_ratings_map()

        results: List[ArtifactQueryResult] = []

        # Normalize query for case-insensitive matching
        query_lower = query.lower()
        query_terms = re.findall(r"\w+", query_lower)

        for artifact_id in artifact_ids:
            try:
                # Load artifact (shallow load to avoid loading full interaction chain)
                artifact = self.storage.load_artifact(artifact_id)

                # Filter by type if specified
                if (
                    artifact_type
                    and artifact.__class__.__name__ != artifact_type
                ):
                    continue

                # Extract searchable content based on artifact type
                content = self._extract_content(artifact)
                if not content:
                    continue

                # Calculate relevance score
                content_lower = content.lower()
                score = self._calculate_score(query_terms, content_lower)

                if score > 0:
                    # Apply rating boost
                    boost, avg, count = self._get_rating_boost(
                        artifact_id, ratings_by_artifact
                    )
                    score += boost

                    # Skip results where boost made score non-positive
                    if score <= 0:
                        continue

                    # Create preview (first 200 chars with query context)
                    preview = self._create_preview(
                        content, query_terms, max_length=200
                    )

                    metadata: Dict[str, Any] = {
                        "created_at": (
                            getattr(artifact, "created_at")
                            if hasattr(artifact, "created_at")
                            else None
                        )
                    }
                    if count > 0:
                        metadata["average_rating"] = avg
                        metadata["rating_count"] = count

                    result = ArtifactQueryResult(
                        artifact_id=artifact_id,
                        artifact_type=artifact.__class__.__name__,
                        content_preview=preview,
                        score=score,
                        metadata=metadata,
                    )
                    results.append(result)

            except Exception as e:
                # Skip artifacts that fail to load
                logger.error(f"Failed to load artifact {artifact_id}: {e}")
                continue

        # Sort by score (descending) and limit
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def get_artifact_content(self, artifact_id: str) -> Optional[str]:
        """
        Get the full content of an artifact by ID.

        Args:
            artifact_id: The ID of the artifact.

        Returns:
            The full content of the artifact as a string, or None if not found.
        """
        try:
            artifact = self.storage.load_artifact(artifact_id)
            return self._extract_content(artifact)
        except Exception as e:
            logger.error(f"Error loading artifact {artifact_id}: {e}")
            return None

    def list_recent_artifacts(
        self, limit: int = 10, artifact_type: Optional[str] = None
    ) -> List[ArtifactQueryResult]:
        """
        List most recent artifacts.

        Args:
            limit: The maximum number of results to return.
            artifact_type: Optional filter by type.

        Returns:
            A list of ArtifactQueryResult objects, sorted by creation time.
        """
        artifact_ids = self.storage.list_artifacts()
        ratings_by_artifact = self._load_ratings_map()
        results: List[ArtifactQueryResult] = []

        for artifact_id in artifact_ids:
            try:
                artifact = self.storage.load_artifact(artifact_id)

                # Filter by type if specified
                if (
                    artifact_type
                    and artifact.__class__.__name__ != artifact_type
                ):
                    continue

                content = self._extract_content(artifact)
                if not content:
                    continue

                preview = content[:200] + ("..." if len(content) > 200 else "")

                metadata: Dict[str, Any] = {
                    "created_at": (
                        getattr(artifact, "created_at")
                        if hasattr(artifact, "created_at")
                        else None
                    )
                }
                _, avg, count = self._get_rating_boost(
                    artifact_id, ratings_by_artifact
                )
                if count > 0:
                    metadata["average_rating"] = avg
                    metadata["rating_count"] = count

                result = ArtifactQueryResult(
                    artifact_id=artifact_id,
                    artifact_type=artifact.__class__.__name__,
                    content_preview=preview,
                    score=0.0,
                    metadata=metadata,
                )
                results.append(result)

            except Exception:
                continue

        # Sort by creation time (most recent first)
        results.sort(
            key=lambda r: r.metadata.get("created_at", ""), reverse=True
        )
        return results[:limit]

    def _extract_content(self, artifact: "Artifact") -> Optional[str]:
        """Extract searchable content from an artifact.

        Args:
            artifact: The artifact to extract content from.

        Returns:
            The searchable content of the artifact as a string, or None if not found.
        """
        artifact_type = artifact.__class__.__name__

        # Handle File and Image artifacts - use name/description, not binary content
        if artifact_type in ("File", "Image"):
            parts = []
            if hasattr(artifact, "name") and artifact.name:
                parts.append(str(artifact.name))
            if hasattr(artifact, "description") and artifact.description:
                parts.append(str(artifact.description))
            return " ".join(parts) if parts else None

        # Handle Text/Code artifacts - use content field
        if hasattr(artifact, "content"):
            return str(getattr(artifact, "content"))

        # Fallback: try to get string representation
        return str(artifact)

    def _calculate_score(self, query_terms: List[str], content: str) -> float:
        """
        Calculate relevance score for content.

        Simple scoring: count of matching terms, with bonus for phrase matches.

        Args:
            query_terms: The terms to search for.
            content: The content to search in.

        Returns:
            The relevance score of the content.
        """
        if not query_terms:
            return 0.0

        score = 0.0

        # Count individual term matches
        for term in query_terms:
            # Count occurrences of this term
            count = content.count(term)
            score += count

        # Bonus for phrase match (all terms appear in order)
        if len(query_terms) > 1:
            # Check if all terms appear close together
            phrase_pattern = (
                r"\b" + r"\W+".join(re.escape(t) for t in query_terms) + r"\b"
            )
            if re.search(phrase_pattern, content, re.IGNORECASE):
                score += PHRASE_MATCH_BONUS

        return score

    def _create_preview(
        self, content: str, query_terms: List[str], max_length: int = 200
    ) -> str:
        """
        Create a preview with context around query terms.

        Tries to show the part of content that contains query terms.

        Args:
            content: The content to create a preview for.
            query_terms: The terms to search for.
            max_length: The maximum length of the preview.

        Returns:
            The preview of the content.
        """
        if not query_terms:
            return content[:max_length] + (
                "..." if len(content) > max_length else ""
            )

        # Find first occurrence of any query term
        content_lower = content.lower()
        first_match_pos = len(content)

        for term in query_terms:
            pos = content_lower.find(term)
            if pos != -1 and pos < first_match_pos:
                first_match_pos = pos

        if first_match_pos < len(content):
            # Start preview a bit before the match
            start = max(0, first_match_pos - 50)
            end = min(len(content), start + max_length)

            preview = content[start:end]

            # Add ellipsis if truncated
            if start > 0:
                preview = "..." + preview
            if end < len(content):
                preview = preview + "..."

            return preview
        else:
            # No match found, return beginning
            return content[:max_length] + (
                "..." if len(content) > max_length else ""
            )

    def _load_ratings_map(
        self,
    ) -> Dict[str, List[int]]:
        """Pre-load all feedback ratings grouped by artifact.

        Returns:
            Dict mapping artifact_id to list of ratings.
        """
        ratings: Dict[str, List[int]] = defaultdict(list)
        for feedback_uuid in self.storage.list_feedback():
            try:
                feedback = self.storage.load_feedback(feedback_uuid)
                ratings[feedback.artifact_id].append(feedback.rating)
            except (ValueError, OSError) as e:
                logger.warning("Skipping feedback %s: %s", feedback_uuid, e)
        return dict(ratings)

    def _get_rating_boost(
        self,
        artifact_id: str,
        ratings_map: Dict[str, List[int]],
    ) -> Tuple[float, float, int]:
        """Calculate rating boost for an artifact.

        Args:
            artifact_id: The artifact to get boost for.
            ratings_map: Pre-loaded ratings map.

        Returns:
            Tuple of (boost, average_rating, count).
            Unrated artifacts return (0.0, 0.0, 0).
        """
        ratings = ratings_map.get(artifact_id, [])
        if not ratings:
            return 0.0, 0.0, 0
        avg = sum(ratings) / len(ratings)
        boost = (avg - RATING_NEUTRAL) * RATING_BOOST_MULTIPLIER
        return boost, avg, len(ratings)
