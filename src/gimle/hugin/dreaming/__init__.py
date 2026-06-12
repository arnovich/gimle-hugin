"""Dreaming: offline memory consolidation that feeds learnings back into prompts.

Episodic artifacts (insights saved during agent runs) are replayed offline and
distilled into ``Learning`` artifacts scoped to the config/task that produced
them. Those learnings are injected into the producing config/task's prompt on
the next run via the ``{{ learnings }}`` template block — a self-improving loop.

See ``tasks/closed/021-dreaming-memory-consolidation.md``.
"""
