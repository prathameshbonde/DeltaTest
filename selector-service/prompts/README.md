# System Prompts

This directory contains system prompts for the LLM-based test selection functionality.

## Available Prompts

- **`system_prompt.md`** - Default general-purpose test selection prompt

## Creating Custom Prompts

### Format Requirements

1. **Markdown format** - Use standard Markdown for readability
2. **Clear instructions** - Specify the role and task clearly
3. **JSON response format** - Include the exact JSON schema expected
4. **Domain-specific guidance** - Add specialized instructions for your use case

### Required Response Schema

Your prompt must instruct the LLM to return JSON with this structure:

```json
{
  "selected_tests": ["com.example.TestClass#testMethod"],
  "explanations": {
    "com.example.TestClass#testMethod": "Reason for selection"
  },
  "confidence": 0.85,
  "metadata": {
    "custom_field": "custom_value"
  }
}
```

### Key Guidelines

- **Emphasize allowed_tests only** - Prevent hallucination by stressing that only tests from the provided `allowed_tests` array should be returned
- **Define confidence scoring** - Provide clear guidelines for confidence levels (0.0-1.0)
- **Include selection strategy** - Explain how to prioritize tests based on your domain needs
- **Specify explanation format** - Guide how to write concise, evidence-based explanations

### Usage Examples

#### Environment Variable
```bash
export LLM_PROMPT_FILE=/path/to/your/custom_prompt.md
export LLM_MODE=openai
export LLM_API_KEY=your_api_key
```

#### Programmatic
```python
from app.model_adapter import ExternalLLMAdapter

adapter = ExternalLLMAdapter(prompt_file='custom_prompt.md')
```

#### Hybrid Mode
```bash
export LLM_MODE=hybrid
export HYBRID_LLM_BACKEND=openai
export LLM_PROMPT_FILE=/path/to/custom_prompt.md
```

## Prompt Categories

### General Purpose
- Balanced approach between precision and recall
- Suitable for most Java/Gradle projects
- Example: `system_prompt.md`

### Security-Focused
- Prioritizes security-critical test coverage
- Emphasizes authentication, authorization, input validation
- Example: `security_focused_prompt.md`

### Performance-Focused (Example)
```markdown
# Performance-Focused Test Selection
You are a performance-aware CI assistant...
- Prioritize performance regression tests
- Include load and stress tests for critical paths
- Focus on memory and CPU intensive operations
```

### Integration-Heavy (Example)
```markdown
# Integration Test Selection
You are an integration-focused CI assistant...
- Prioritize end-to-end and integration tests
- Include cross-service dependency tests
- Focus on data flow and API contract tests
```


## Best Practices

1. **Start with defaults** - Copy and modify existing prompts
2. **Test incrementally** - Make small changes and test frequently
3. **Domain expertise** - Include knowledge specific to your application domain
4. **Clear constraints** - Be explicit about limitations and requirements
5. **Feedback loop** - Monitor results and refine prompts based on performance