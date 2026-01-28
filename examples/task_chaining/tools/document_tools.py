"""Document processing tools for task chaining example."""

import json
from typing import Any

from gimle.hugin.interaction.stack import Stack
from gimle.hugin.tools.tool import ToolResponse


def extract_text(document: str, stack: Stack, **kwargs: Any) -> ToolResponse:
    """Extract and clean text from a document.

    This simulates text extraction from various document formats.
    In a real scenario, this might use OCR, PDF parsing, etc.
    """
    # Simulate text extraction (in reality, might do OCR, PDF parsing, etc.)
    sentences = [s.strip() for s in document.split(".") if s.strip()]
    extracted = {
        "raw_text": document,
        "word_count": len(document.split()),
        "char_count": len(document),
        "sentences": sentences,
    }

    return ToolResponse(
        is_error=False,
        content={
            "status": "extracted",
            "extracted_data": extracted,
            "message": f"Extracted {extracted['word_count']} words, "
            f"{len(sentences)} sentences",
        },
    )


def analyze_content(content: str, stack: Stack, **kwargs: Any) -> ToolResponse:
    """Analyze the content for key metrics and patterns.

    Takes extracted text (as JSON string) and produces analysis.
    """
    try:
        data = json.loads(content) if isinstance(content, str) else content
    except json.JSONDecodeError:
        # If not JSON, treat as raw text
        data = {"raw_text": content, "sentences": content.split(".")}

    raw_text: str = data.get("raw_text", "")
    sentences: list[str] = data.get("sentences", [])

    # Simple analysis
    words = raw_text.lower().split()
    unique_words = set(words)

    vocab_richness = round(len(unique_words) / len(words), 2) if words else 0.0
    avg_sent_len = round(len(words) / len(sentences), 1) if sentences else 0.0
    key_observations: list[str] = []

    # Add some observations
    if vocab_richness > 0.7:
        key_observations.append("High vocabulary diversity")
    if avg_sent_len > 15:
        key_observations.append("Complex sentence structure")
    elif avg_sent_len < 8:
        key_observations.append("Simple, concise sentences")

    analysis: dict[str, Any] = {
        "total_words": len(words),
        "unique_words": len(unique_words),
        "vocabulary_richness": vocab_richness,
        "avg_sentence_length": avg_sent_len,
        "sentence_count": len(sentences),
        "key_observations": key_observations,
    }

    return ToolResponse(
        is_error=False,
        content={
            "status": "analyzed",
            "analysis": analysis,
            "message": f"Analyzed content: {analysis['unique_words']} unique words, "
            f"vocabulary richness {analysis['vocabulary_richness']}",
        },
    )


def create_summary(analysis: str, stack: Stack, **kwargs: Any) -> ToolResponse:
    """Create a summary from the analysis results.

    Takes analysis (as JSON string) and produces a human-readable summary.
    """
    try:
        data = json.loads(analysis) if isinstance(analysis, str) else analysis
    except json.JSONDecodeError:
        return ToolResponse(
            is_error=True,
            content={"error": "Invalid analysis data format"},
        )

    analysis_data = data.get("analysis", data)

    # Build summary
    observations = analysis_data.get("key_observations", [])
    obs_text = (
        ", ".join(observations) if observations else "No notable patterns"
    )

    summary = {
        "title": "Document Analysis Summary",
        "metrics": {
            "words": analysis_data.get("total_words", 0),
            "unique_words": analysis_data.get("unique_words", 0),
            "sentences": analysis_data.get("sentence_count", 0),
        },
        "insights": obs_text,
        "recommendation": (
            "The document shows "
            + (
                "rich vocabulary"
                if analysis_data.get("vocabulary_richness", 0) > 0.7
                else "moderate vocabulary diversity"
            )
            + " with "
            + (
                "complex"
                if analysis_data.get("avg_sentence_length", 0) > 15
                else "straightforward"
            )
            + " sentence structure."
        ),
    }

    return ToolResponse(
        is_error=False,
        content={
            "status": "completed",
            "summary": summary,
            "message": "Document processing pipeline complete",
        },
    )
