#!/bin/bash
# Test script for hugin-agent-creator plugin
# Creates a fresh environment, installs hugin, and tests the plugin

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HUGIN_REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
TEST_DIR="${1:-/tmp/test-hugin-plugin-$$}"

echo "=== Hugin Agent Creator Plugin Test ==="
echo "Plugin dir: $SCRIPT_DIR"
echo "Hugin repo: $HUGIN_REPO"
echo "Test dir:   $TEST_DIR"
echo ""

# Create test directory
echo "Creating test directory..."
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

# Create fresh Python environment with uv
echo "Creating fresh Python environment..."
uv venv .venv
source .venv/bin/activate

# Install hugin from the repo
echo "Installing hugin from repo..."
uv pip install "$HUGIN_REPO"

# Verify installation
echo "Verifying hugin installation..."
hugin --version || echo "hugin CLI installed"

echo ""
echo "=== Environment Ready ==="
echo ""
echo "Test directory: $TEST_DIR"
echo "Python env:     $TEST_DIR/.venv"
echo ""
echo "To test the plugin manually:"
echo ""
echo "  cd $TEST_DIR"
echo "  source .venv/bin/activate"
echo "  claude --plugin-dir $SCRIPT_DIR"
echo ""
echo "Then in Claude Code, try:"
echo ""
echo "  /hugin-agent-creator:hugin-guide"
echo "  /hugin-agent-creator:hugin-scaffold my_test_agent minimal"
echo ""
echo "After scaffolding, test the agent:"
echo ""
echo "  hugin run --task my_test_agent_task --task-path ./my_test_agent"
echo ""
echo "=== Quick Test: Scaffold a minimal agent ==="
echo ""

# Create a minimal test agent manually to verify hugin works
mkdir -p test_agent/configs test_agent/tasks test_agent/templates

cat > test_agent/configs/test_agent.yaml << 'EOF'
name: test_agent
description: Test agent created by test script
system_template: test_system
llm_model: haiku-latest
tools:
  - builtins.finish:finish
interactive: false
options: {}
EOF

cat > test_agent/tasks/test_task.yaml << 'EOF'
name: test_task
description: Simple test task
parameters:
  input:
    type: string
    description: Test input
    required: false
    default: "Hello from test!"
prompt: |
  Echo this input back: {{ input.value }}

  Use the finish tool with the input as your result.
EOF

cat > test_agent/templates/test_system.yaml << 'EOF'
name: test_system
template: |
  You are a test agent. Simply echo back what you receive.
  Use the finish tool when done.
EOF

echo "Created test_agent/ with minimal config"
echo ""
echo "To run the test agent (requires ANTHROPIC_API_KEY):"
echo ""
echo "  cd $TEST_DIR"
echo "  source .venv/bin/activate"
echo "  hugin run --task test_task --task-path ./test_agent"
echo ""
echo "=== Setup Complete ==="
