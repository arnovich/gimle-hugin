# Artifacts Example - Research Assistant

This example demonstrates the artifact system in Hugin, showing how agents can build long-term knowledge through three builtin tools:

- `builtins.save_insight` - Store findings as artifacts
- `builtins.query_artifacts` - Search previous research
- `builtins.get_artifact_content` - Retrieve full artifact content

## Concept

The Research Assistant demonstrates **long-term memory** through artifacts:

1. **Query First**: Before researching, check if we already have knowledge on this topic
2. **Build Knowledge**: Research and save new findings as markdown artifacts
3. **Cumulative Learning**: Each session adds to the knowledge base
4. **Persistence**: Artifacts survive across agent runs - true long-term memory

## Running the Example

### First Research Session
```bash
uv run hugin run \
  --task research_topic \
  --task-path examples/artifacts \
  --parameters '{"topic": "Quantum Computing", "focus_areas": ["applications", "challenges"]}'
```

### Continue Research (builds on previous)
```bash
uv run hugin run \
  --task continue_research \
  --task-path examples/artifacts \
  --parameters '{"query": "Quantum Computing", "new_focus": "2024 breakthroughs"}'
```

### Query Existing Research
```bash
uv run hugin run \
  --task research_topic \
  --task-path examples/artifacts \
  --parameters '{"topic": "Machine Learning"}'
```

## Workflow Demonstration

### Initial Research
```
User starts research_topic (topic: "AI Safety")
         │
         ▼
    query_artifacts("AI Safety")
    └─> No existing artifacts found
         │
         ▼
    Conduct research on AI Safety
         │
         ▼
    save_insight(findings in markdown)
    └─> Artifact saved: abc123
         │
         ▼
    finish("Saved research on AI Safety")
```

### Continued Research
```
User starts continue_research (query: "AI Safety")
         │
         ▼
    query_artifacts("AI Safety")
    └─> Found 1 artifact (preview shown)
         │
         ▼
    get_artifact_content("abc123")
    └─> Full content retrieved
         │
         ▼
    Research new developments (building on existing)
         │
         ▼
    save_insight(updated findings in markdown)
    └─> Artifact saved: def456
         │
         ▼
    finish("Updated research with new findings")
```

## Artifact Format

Artifacts are saved in markdown format for readability:

```markdown
# Research: Quantum Computing

**Date**: 2024-01-07
**Focus**: Applications and Challenges

## Key Findings

### Applications
- Cryptography and security
- Drug discovery and molecular modeling
- Financial modeling and optimization

### Challenges
- Quantum decoherence
- Error correction complexity
- Scalability limitations

## Sources
- Recent research papers
- Industry developments
- Academic institutions
```

## Storage Location

All artifacts are stored in `--storage-path` (default: `./storage`):
```
./data/research/
└── artifacts/
    ├── <uuid-1>  # First research artifact
    ├── <uuid-2>  # Updated research artifact
    └── ...       # More artifacts accumulate over time
```

## Use Cases

This pattern is ideal for:
- **Research assistants** - Building knowledge bases over time
- **Documentation agents** - Accumulating project documentation
- **Analysis agents** - Tracking insights across multiple analyses
- **Learning agents** - Building understanding incrementally
- **Memory-critical workflows** - Any task requiring long-term recall
