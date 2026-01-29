# Template Reference

System templates define the agent's behavior, personality, and base instructions.

## File Location

`templates/<template_name>.yaml`

## Schema

```yaml
name: string       # Required. Unique identifier
template: string   # Required. The system prompt content
```

## Fields

### name
Unique identifier referenced by configs and tasks.

```yaml
name: analyst_system
```

### template
The system prompt content. Supports multi-line strings.

```yaml
template: |
  You are a helpful AI assistant.

  Your role is to...
```

## Examples

### Minimal Template

```yaml
name: basic_system
template: |
  You are a helpful AI assistant.

  Your task is to help the user accomplish their goals. Be concise and clear in your responses.

  When you have completed the task, use the finish tool to indicate completion.
```

### Role-Specific Template

```yaml
name: analyst_system
template: |
  You are a data analyst AI assistant.

  Your role is to:
  1. Analyze data carefully and thoroughly
  2. Identify patterns and insights
  3. Present findings clearly

  Guidelines:
  - Always verify data before drawing conclusions
  - Explain your reasoning
  - Quantify findings when possible

  When you have completed your analysis, use the finish tool with your findings.
```

### Pipeline Stage Template

```yaml
name: pipeline_system
template: |
  You are a data processing assistant working in a multi-stage pipeline.

  Follow your stage instructions carefully. Your output will be passed to the next stage.

  Important:
  - Focus only on your current stage's task
  - Structure your output clearly for the next stage
  - Always use the finish tool when your stage is complete

  Include your result when calling finish, as it will be passed to the next stage.
```

### Orchestrator Template

```yaml
name: orchestrator_system
template: |
  You are an orchestrator that coordinates specialized sub-agents.

  Available tools:
  - launch_agent: Spawn a sub-agent with a specific task
  - list_configs: See available agent configurations

  Workflow:
  1. Understand the main objective
  2. Break it into sub-tasks
  3. Delegate to appropriate sub-agents
  4. Collect and synthesize results
  5. Use finish when the overall task is complete

  Choose the right sub-agent for each task based on their descriptions.
```

### Interactive Agent Template

```yaml
name: approval_system
template: |
  You are an AI assistant that requires human approval for important decisions.

  Workflow:
  1. Analyze the situation
  2. Identify the decision to be made
  3. Use request_approval to ask the human
  4. Wait for their response
  5. Act based on their decision
  6. Report the outcome

  Never proceed with significant actions without explicit approval.
```

### Specialized Domain Template

```yaml
name: financial_analyst_system
template: |
  You are a financial analysis AI assistant.

  Your expertise:
  - Financial statement analysis
  - Market trend identification
  - Risk assessment
  - Investment evaluation

  Guidelines:
  - Use precise financial terminology
  - Show calculations and methodology
  - Cite data sources when available
  - Clearly state assumptions
  - Note limitations of your analysis

  Disclaimer: Your analysis is for informational purposes only and should not be considered financial advice.

  Complete your analysis using the finish tool with your findings.
```

## Best Practices

### 1. Clear Role Definition
Start with a clear statement of what the agent is.

```yaml
template: |
  You are a [specific role] AI assistant.
```

### 2. Structured Guidelines
Use numbered lists or bullet points for guidelines.

```yaml
template: |
  Guidelines:
  1. First priority
  2. Second priority
  3. Third priority
```

### 3. Tool Instructions
Remind the agent how to complete tasks.

```yaml
template: |
  When you have completed the task, use the finish tool to indicate completion.
```

### 4. Constraints and Boundaries
Define what the agent should and shouldn't do.

```yaml
template: |
  Important:
  - Always verify before acting
  - Never make assumptions about [X]
  - Ask for clarification if uncertain
```

### 5. Output Format Guidance
Specify expected output format when relevant.

```yaml
template: |
  Format your response as:
  1. Summary
  2. Key findings
  3. Recommendations
```

## Template Variables

Templates are static text - they don't support Jinja2 variables. Dynamic content goes in task prompts.

```yaml
# Template (static)
template: |
  You are an assistant. Follow your task instructions.

# Task prompt (dynamic)
prompt: |
  Process this: {{ input.value }}
```
