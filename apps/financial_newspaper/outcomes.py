"""Deterministic completion evidence, separate from editorial quality."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gimle.hugin.agent.session import Session


def assess_edition(session: Session) -> dict:
    """Check current-run output and content coverage, not factual correctness."""
    values = session.environment.env_vars
    articles = values.get("newspaper_articles", [])
    receipt = values.get("newspaper_layout_receipt", {})
    if not isinstance(receipt, dict):
        receipt = {}
    expected = values.get(
        "newspaper_expected_articles", values.get("number_of_articles", 3)
    )
    valid_articles = isinstance(articles, list) and all(
        isinstance(article, dict)
        and all(
            isinstance(article.get(key), str) and article[key].strip()
            for key in ("id", "headline", "content", "category")
        )
        for article in articles
    )
    count = len(articles) if isinstance(articles, list) else 0
    ids = [article["id"] for article in articles] if valid_articles else []
    checks = {
        "current_execution": bool(values.get("newspaper_execution_id"))
        and receipt.get("execution_id") == values.get("newspaper_execution_id")
        and receipt.get("session_id") == session.id,
        "required_article_count": type(expected) is int
        and expected > 0
        and count == expected,
        "article_fields": valid_articles and count > 0,
        "unique_article_ids": bool(ids) and len(set(ids)) == len(ids),
        "rendered_current_articles": False,
        "layout_in_output_directory": False,
        "layout_digest": False,
    }
    try:
        checks["rendered_current_articles"] = (
            receipt.get("articles_sha256")
            == hashlib.sha256(
                json.dumps(articles, sort_keys=True, allow_nan=False).encode(
                    "utf-8"
                )
            ).hexdigest()
        )
        layout = Path(receipt.get("layout_file", ""))
        output_dir = Path(
            values.get("newspaper_layout_dir", "storage/newspaper_layouts")
        )
        checks["layout_in_output_directory"] = (
            layout.is_absolute()
            and not layout.is_symlink()
            and layout.resolve().parent == output_dir.resolve()
            and layout.name != "latest.html"
        )
        if checks["current_execution"] and checks["layout_in_output_directory"]:
            content = layout.read_bytes()
            checks["layout_digest"] = bool(content) and (
                hashlib.sha256(content).hexdigest()
                == receipt.get("html_sha256")
            )
    except (OSError, ValueError, TypeError):
        pass  # missing/malformed evidence is a failed check, not success
    scores = (
        [
            float(article["quality_score"])
            for article in articles
            if isinstance(article, dict)
            and type(article.get("quality_score")) in (int, float)
            and math.isfinite(article["quality_score"])
        ]
        if isinstance(articles, list)
        else []
    )
    return {
        "schema_version": 1,
        "checker": "newspaper-completion-v1",
        "task_id": session.id,
        "execution_id": values.get("newspaper_execution_id"),
        "expected_articles": expected,
        "observed_articles": count,
        "checks": checks,
        "output_complete": all(checks.values()),
        "quality": {
            "independent_evaluation": "not_run",
            "editor_self_score_advisory": (
                sum(scores) / len(scores) if scores else None
            ),
        },
        "layout_file": receipt.get("layout_file"),
    }


def validate_edition(session: Session) -> bool:
    """Additional check used by the session's single outcome reporter."""
    return bool(assess_edition(session)["output_complete"])
