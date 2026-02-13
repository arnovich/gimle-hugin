"""CLI command for rating artifacts as a human."""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from gimle.hugin.artifacts.feedback import ArtifactFeedback
from gimle.hugin.storage.local import LocalStorage


def _list_artifacts(storage: LocalStorage) -> List[Dict[str, Any]]:
    """List all artifacts with type and preview."""
    artifacts: List[Dict[str, Any]] = []
    for artifact_id in storage.list_artifacts():
        try:
            meta = storage.load_artifact_metadata(artifact_id)
            artifacts.append(
                {
                    "id": artifact_id,
                    "type": meta.get("type", "Unknown"),
                    "preview": meta.get("preview", ""),
                    "format": meta.get("format"),
                }
            )
        except Exception:
            continue
    return artifacts


def _prompt_artifact(
    artifacts: List[Dict[str, Any]],
) -> Optional[str]:
    """Prompt user to pick an artifact. Returns artifact ID."""
    if not artifacts:
        print("No artifacts found in storage.")
        return None

    print("\nAvailable artifacts:\n")
    for i, art in enumerate(artifacts):
        short_id = art["id"][:12]
        fmt = f" ({art['format']})" if art.get("format") else ""
        preview = art.get("preview", "")
        if len(preview) > 50:
            preview = preview[:47] + "..."
        preview = preview.replace("\n", " ")
        print(f"  {i + 1:3d}. [{art['type']}{fmt}] {short_id}")
        if preview:
            print(f"       {preview}")

    print()
    try:
        choice = input(f"Select artifact (1-{len(artifacts)}): ")
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(artifacts):
            artifact_id: str = artifacts[idx]["id"]
            return artifact_id
    except ValueError:
        pass

    print(f"Invalid choice: {choice}")
    return None


def _prompt_rating() -> Optional[int]:
    """Prompt user for a rating 1-5."""
    try:
        value = input("Rating (1-5): ")
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    try:
        rating = int(value)
        if 1 <= rating <= 5:
            return rating
    except ValueError:
        pass

    print(f"Invalid rating: {value} (must be 1-5)")
    return None


def _prompt_comment() -> Optional[str]:
    """Prompt user for an optional comment."""
    try:
        comment = input("Comment (optional, Enter to skip): ")
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    return comment if comment.strip() else None


def rate_artifact_cli(
    storage_path: str,
    artifact_id: Optional[str] = None,
    rating: Optional[int] = None,
    comment: Optional[str] = None,
    prompt_comment: bool = False,
) -> int:
    """Run the rate artifact CLI flow.

    Args:
        storage_path: Path to storage directory.
        artifact_id: Artifact UUID (prompted if None).
        rating: Rating 1-5 (prompted if None).
        comment: Comment string or None.
        prompt_comment: If True, prompt for comment interactively.

    Returns:
        Exit code (0 for success).
    """
    path = Path(storage_path)
    if not path.exists():
        print(f"Error: Storage path '{path}' does not exist.")
        return 1

    storage = LocalStorage(base_path=storage_path)

    # Track whether we are in interactive mode
    interactive = False

    # Select artifact
    if artifact_id is None:
        interactive = True
        artifacts = _list_artifacts(storage)
        artifact_id = _prompt_artifact(artifacts)
        if artifact_id is None:
            return 1

    # Verify artifact exists
    try:
        storage.load_artifact(artifact_id)
    except Exception:
        print(f"Error: Artifact '{artifact_id}' not found.")
        return 1

    # Get rating
    if rating is None:
        interactive = True
        rating = _prompt_rating()
        if rating is None:
            return 1

    # Get comment - prompt when explicitly requested or interactive
    if comment is None and (prompt_comment or interactive):
        comment = _prompt_comment()

    # Check for existing human rating
    for fb_id in storage.list_feedback(artifact_id):
        try:
            existing = storage.load_feedback(fb_id)
            if existing.source == "human":
                print("Error: Already rated this artifact.")
                return 1
        except (ValueError, OSError):
            continue

    # Create and save feedback
    try:
        feedback = ArtifactFeedback(
            artifact_id=artifact_id,
            rating=rating,
            comment=comment,
            agent_id=None,
            source="human",
        )
    except (ValueError, TypeError) as e:
        print(f"Error: {e}")
        return 1

    storage.save_feedback(feedback)

    short_id = artifact_id[:12]
    print(f"\nSaved rating {rating}/5 for artifact {short_id}")
    if comment:
        print(f"Comment: {comment}")
    print(f"Feedback ID: {feedback.id}")

    return 0


def main() -> int:
    """Entry point for the rate command."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Rate an artifact as a human reviewer"
    )
    parser.add_argument(
        "--storage-path",
        type=str,
        default="./storage",
        help="Path to storage directory (default: ./storage)",
    )
    parser.add_argument(
        "--artifact-id",
        type=str,
        default=None,
        help="UUID of the artifact to rate (interactive if omitted)",
    )
    parser.add_argument(
        "--rating",
        type=int,
        choices=[1, 2, 3, 4, 5],
        default=None,
        help="Rating from 1 (poor) to 5 (excellent)",
    )
    parser.add_argument(
        "--comment",
        type=str,
        default=None,
        help="Optional comment explaining the rating",
    )

    args = parser.parse_args()

    return rate_artifact_cli(
        storage_path=args.storage_path,
        artifact_id=args.artifact_id,
        rating=args.rating,
        comment=args.comment,
        prompt_comment=args.comment is None,
    )


if __name__ == "__main__":
    sys.exit(main())
