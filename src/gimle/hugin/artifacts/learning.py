"""Learning Artifact: a consolidated lesson distilled by the dream.

A ``Learning`` is the *semantic* memory type produced by offline consolidation
(the "dreaming" pass): many episodic artifacts are replayed and distilled into a
reusable lesson that is injected back into the producing config/task's prompt on
the next run. See ``src/gimle/hugin/dreaming/``.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.utils.uuid import with_uuid


@with_uuid
@Artifact.register("Learning")
@dataclass
class Learning(Artifact):
    """A consolidated lesson scoped to the config/task it applies to.

    Attributes:
        content: The lesson, in prose ready to drop into a prompt.
        scope_config: The config name this learning improves (or None).
        scope_task: The task name this learning improves (or None for
            config-wide learnings).
        scope_app: An optional coarser app/world scope key (v2).
        source_artifact_ids: The episodic artifacts this was distilled from
            (evidence / traceability).
        confidence: The dream's self-assessed confidence in [0, 1].
        derived_from: Provenance marker; "dream" for consolidated learnings.
            Used to exclude learnings from the dream's own input
            (no dreams-eating-dreams).
    """

    content: str
    scope_config: Optional[str] = None
    scope_task: Optional[str] = None
    scope_app: Optional[str] = None
    source_artifact_ids: List[str] = field(default_factory=list)
    confidence: float = 0.0
    derived_from: str = "dream"
