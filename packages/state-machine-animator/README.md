# State Machine Animator

Animated visualizations of state machines and interaction stacks for documentation and tutorials.

## Quick Start

```html
<div id="animation" style="width: 600px; height: 400px;"></div>

<script type="module">
  import { StateMachineAnimator } from './dist/state-machine-animator.js';

  const animator = new StateMachineAnimator({
    container: '#animation',
    theme: 'light',
  });

  await animator.playToolExecution({
    stack: {
      id: 'main',
      label: 'Agent',
      states: [{ type: 'TaskDefinition', label: 'Analyze data' }],
    },
    triggerState: { type: 'ToolCall', label: 'query_database' },
    tool: { id: 'db', name: 'Database', icon: '🗄️' },
    resultState: { type: 'ToolResult', label: '1000 rows returned' },
  });
</script>
```

## License

MIT - Part of the Gimle Hugin project.
