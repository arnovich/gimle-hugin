# Branching Example - Problem-Solving Agent

This example demonstrates stack branching in Hugin, showing how agents can explore multiple solution approaches in parallel.

## Concept

**Stack Branching** allows an agent to:
- Create multiple parallel execution paths (branches)
- Each branch explores a different approach to the same problem
- Branches run concurrently with isolated contexts
- Results can be compared to choose the best solution

Think of it like exploring multiple paths in a maze simultaneously, then choosing the best one.

## Key Features

### Branch Isolation
- Each branch sees the main branch history **up to the fork point**
- Branches **don't see each other**'s work
- Branches complete independently

### Parallel Execution
- All active branches step forward together
- No waiting for one branch to finish before starting another
- Efficient exploration of solution space

### Custom Tools

#### `create_branch`
Creates a new branch to explore a specific approach.

**Parameters:**
- `branch_name`: Descriptive name (e.g., "optimized_for_speed")
- `approach_description`: What this branch will explore

#### `compare_branches`
Compares results from all branches, showing completion status and interaction counts.

## Running the Example

### Basic Problem Solving
```bash
uv run hugin run \
  --task solve_problem \
  --task-path examples/branching
```

### Custom Problem
```bash
uv run hugin run \
  --task solve_problem \
  --task-path examples/branching \
  --parameters '{"problem": "Design a caching strategy for a web API", "criteria": "Balance hit rate and memory usage"}'
```

## Workflow Demonstration

```
Main Branch: Analyze problem
         │
         ├─> Identify 3 approaches
         │
         ├─> create_branch("approach_a", "Optimize for speed")
         ├─> create_branch("approach_b", "Optimize for memory")
         └─> create_branch("approach_c", "Balance both")
              │
              ▼
         ┌────┴────┬────────┐
         │         │        │
    Branch A   Branch B  Branch C
         │         │        │
    (speed)   (memory)  (balance)
         │         │        │
     finish()  finish()  finish()
         │         │        │
         └────┬────┴────────┘
              │
              ▼
         compare_branches()
              │
              ▼
         Select best approach
              │
              ▼
         finish() on main
```

## Branch Visibility Example

```python
# Main branch sees all main interactions
main_branch_context = [task_def, analyze, create_branch_a, create_branch_b]

# Branch A sees:
# - Main branch up to fork point (task_def, analyze)
# - Its own interactions (solve_for_speed, finish)
branch_a_context = [task_def, analyze, solve_for_speed, finish]

# Branch B sees:
# - Main branch up to fork point (task_def, analyze)
# - Its own interactions (solve_for_memory, finish)
# - Does NOT see Branch A's work
branch_b_context = [task_def, analyze, solve_for_memory, finish]
```

## Architecture

### How Branches Get Different Tools

The main branch uses the `solve_problem` task with the `problem_solver` config, which includes branching tools (`create_branch`, `compare_branches`).

When `create_branch` is called, it loads the `explore_branch` task from the registry. This task:
- Specifies only `builtins.finish:finish` in its `tools` field
- Uses a different `system_template` (`branch_solver_system`)

This prevents recursive branch creation - branches can only finish, not create more branches.

```yaml
# tasks/explore_branch.yaml
tools:
  - builtins.finish:finish  # Only finish tool
system_template: branch_solver_system
```

The Task's `tools` field **replaces** (not extends) the config's tools when present, giving branches a different tool set than the main branch.

## Use Cases

This pattern is ideal for:

- **Algorithm Selection** - Try multiple algorithms, pick the best
- **Optimization Problems** - Explore different optimization strategies
- **Design Decisions** - Test different architectures in parallel
- **A/B Testing** - Compare different prompt variations
- **Rollouts** - Explore game trees or decision paths
- **Hypothesis Testing** - Validate multiple hypotheses concurrently

## When to Use Branching

Use branching when:
- ✓ Multiple valid approaches exist
- ✓ Trade-offs need to be evaluated (speed vs memory, simple vs complex)
- ✓ You want to explore options in parallel
- ✓ Each approach is independent and self-contained

Don't use branching when:
- ✗ Only one clear solution path exists
- ✗ Solutions depend on each other (use sequential tasks instead)
- ✗ You need branches to communicate (use multi-agent messaging instead)
