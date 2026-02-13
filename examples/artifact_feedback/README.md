# Artifact Feedback Example - Knowledge Curator

This example demonstrates the **artifact feedback/rating system** in Hugin. A single "knowledge curator" agent creates insights, rates them, and then queries to see how ratings affect search ranking.

Built-in tools used:

- `save_insight` - Store research findings as artifacts
- `query_artifacts` - Search the knowledge base (ratings affect ranking)
- `get_artifact_content` - Retrieve full artifact content
- `rate_artifact` - Rate an artifact 1-5 with an optional comment

## 3-Phase Workflow

Run the phases in order. Each builds on the previous, using the same storage.

### Phase 1: Create Insights

Save several research insights as artifacts.

```bash
uv run hugin run \
  --task create_insights \
  --task-path examples/artifact_feedback
```

### Phase 2: Rate Insights

Review each artifact and assign a quality rating (1-5) with a comment.

```bash
uv run hugin run \
  --task rate_insights \
  --task-path examples/artifact_feedback
```

### Phase 3: Query with Ratings

Query the knowledge base and observe how ratings affect result ordering.

```bash
uv run hugin run \
  --task query_with_ratings \
  --task-path examples/artifact_feedback
```

### Custom Topic

All three tasks accept a `topic` parameter (default: "Renewable Energy"):

```bash
uv run hugin run \
  --task create_insights \
  --task-path examples/artifact_feedback \
  --parameters '{"topic": "Quantum Computing"}'
```

## Workflow Diagram

```
Phase 1: create_insights
         │
         ▼
    query_artifacts("Renewable Energy")
    └─> No existing artifacts
         │
         ▼
    save_insight(insight A)  ──> artifact-aaa
    save_insight(insight B)  ──> artifact-bbb
    save_insight(insight C)  ──> artifact-ccc
         │
         ▼
    finish("Saved 3 insights")

Phase 2: rate_insights
         │
         ▼
    query_artifacts("Renewable Energy")
    └─> Found 3 artifacts (no ratings yet)
         │
         ▼
    get_artifact_content("artifact-aaa") ──> read full text
    rate_artifact("artifact-aaa", 5, "Excellent depth")
         │
    get_artifact_content("artifact-bbb") ──> read full text
    rate_artifact("artifact-bbb", 3, "Decent overview")
         │
    get_artifact_content("artifact-ccc") ──> read full text
    rate_artifact("artifact-ccc", 4, "Good analysis")
         │
         ▼
    finish("Rated all 3 artifacts")

Phase 3: query_with_ratings
         │
         ▼
    query_artifacts("Renewable Energy")
    └─> Results now include average_rating & rating_count
        Higher-rated artifacts appear first:
          1. artifact-aaa (avg: 5.0)
          2. artifact-ccc (avg: 4.0)
          3. artifact-bbb (avg: 3.0)
         │
         ▼
    finish("Ratings improve search quality")
```

## How Ratings Affect Search

When artifacts have ratings:

- `query_artifacts` results include `average_rating` and `rating_count`
- Higher-rated artifacts are ranked above lower-rated ones
- Unrated artifacts rank below rated ones
- This creates a feedback loop where quality content surfaces naturally
