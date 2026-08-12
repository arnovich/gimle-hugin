"""The dream's episodic corpus is bounded by SIZE, newest-first.

This replayed a scope's entire history into one prompt every night, so the corpus
grew without bound. A scope whose artifacts are large eventually crossed the
model's usable limit and started consolidating nothing — silently, because a dream
that saves zero learnings still succeeds.

Bounded on size rather than count because artifact sizes differ by an order of
magnitude between scopes sharing a store. In the case that exposed this, three
personas each had 53 artifacts: the short-form one still worked while the two
long-form ones had been dead for weeks. A count cap would have left both broken.
"""

from types import SimpleNamespace

from gimle.hugin.dreaming.consolidate import (
    DEFAULT_CORPUS_CHARS,
    _episodic_block,
)
from gimle.hugin.dreaming.provenance import ArtifactProvenance


def _env(contents):
    """Build an Environment stub returning canned artifact content."""
    return SimpleNamespace(
        query_engine=SimpleNamespace(
            get_artifact_content=lambda aid: contents[aid]
        )
    )


def _prov(aid, created_at=None):
    return ArtifactProvenance(
        artifact_id=aid,
        artifact_type="Text",
        config="c",
        task="t",
        interaction_id="i",
        created_at=created_at,
    )


def test_small_corpus_is_untouched():
    """Keep a within-budget scope byte-identical to the old behaviour.

    The short-form persona was still working, and must keep working.
    """
    contents = {"a": "alpha", "b": "beta", "c": "gamma"}
    provs = [
        _prov("a", "2026-01-01T00:00:00Z"),
        _prov("b", "2026-01-02T00:00:00Z"),
        _prov("c", "2026-01-03T00:00:00Z"),
    ]
    block = _episodic_block(_env(contents), provs)
    for text in contents.values():
        assert text in block


def test_oldest_are_dropped_when_over_budget():
    """Drop the oldest memories first when the corpus exceeds its budget."""
    contents = {"old": "O" * 400, "mid": "M" * 400, "new": "N" * 400}
    provs = [
        _prov("old", "2026-01-01T00:00:00Z"),
        _prov("mid", "2026-06-01T00:00:00Z"),
        _prov("new", "2026-12-01T00:00:00Z"),
    ]
    block = _episodic_block(_env(contents), provs, max_chars=900)
    assert "N" * 400 in block, "the newest memory must survive"
    assert "M" * 400 in block
    assert "O" * 400 not in block, "the oldest is dropped first"


def test_kept_corpus_reads_chronologically():
    """Selection is newest-first, but the prompt should still read oldest→newest."""
    contents = {"one": "FIRST", "two": "SECOND", "three": "THIRD"}
    provs = [
        _prov("three", "2026-03-01T00:00:00Z"),
        _prov("one", "2026-01-01T00:00:00Z"),
        _prov("two", "2026-02-01T00:00:00Z"),
    ]
    block = _episodic_block(_env(contents), provs)
    assert block.index("FIRST") < block.index("SECOND") < block.index("THIRD")


def test_one_oversized_artifact_still_yields_a_corpus():
    """Never return an empty block.

    An empty corpus makes the dream silently do nothing, which is the exact
    failure this fixes.
    """
    contents = {"huge": "H" * 5000}
    block = _episodic_block(
        _env(contents), [_prov("huge", "2026-01-01T00:00:00Z")], max_chars=10
    )
    assert "H" * 5000 in block


def test_missing_created_at_sorts_oldest_and_is_dropped_first():
    """Treat an undated artifact as the oldest.

    Conservative: it is dropped before anything we can actually date.
    """
    contents = {"undated": "U" * 400, "dated": "D" * 400}
    provs = [_prov("undated", None), _prov("dated", "2026-01-01T00:00:00Z")]
    block = _episodic_block(_env(contents), provs, max_chars=500)
    assert "D" * 400 in block
    assert "U" * 400 not in block


def test_budget_default_is_generous_enough_for_a_short_form_scope():
    """Leave a healthy short-form scope entirely untrimmed at the default."""
    # ~53 artifacts of ~1.5KB (the working persona's real shape) must not be
    # trimmed at all — the fix must not degrade a scope that was healthy.
    contents = {f"a{i}": "x" * 1500 for i in range(53)}
    provs = [
        _prov(f"a{i}", f"2026-01-{i % 28 + 1:02d}T00:00:00Z") for i in range(53)
    ]
    block = _episodic_block(_env(contents), provs)
    assert block.count("[a") == 53
    assert 53 * 1500 < DEFAULT_CORPUS_CHARS
