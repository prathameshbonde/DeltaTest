# Security

- This project does not execute arbitrary code from inputs. The FastAPI server validates payloads via Pydantic.
- External LLM is disabled by default and needs explicit env vars.
- In GitHub Actions, `pull_request_target` job does not build or execute PR code with elevated permissions beyond standard steps.
