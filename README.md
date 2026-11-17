# Autonomous QA Agent

Phase 1 provides a typed core package for QA-agent requests and responses, a provider-independent LLM boundary, deterministic mock inference, environment-based settings, JSON logging with correlation context, and centralized error translation.

## Requirements

- Python 3.12 or newer
- No external model service is used in this phase.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:APP_ENV = "development"
$env:LLM_PROVIDER = "mock"
```

Settings are read from environment variables. `.env` loading is deliberately disabled in code; use `.env.example` as a reference and export values in your shell or explicitly load a local environment file in your deployment tooling.

## Run validation

```powershell
pytest
ruff check .
```

## Core flow

```python
from autonomous_qa_agent.config import Settings
from autonomous_qa_agent.llm import MockLLMProvider
from autonomous_qa_agent.services import AgentService

service = AgentService(provider=MockLLMProvider())
response = service.handle("Verify the task creation flow")
```

Alternatively, `create_agent_service(Settings())` selects the configured mock provider and accepts a custom `LLMProvider` for dependency injection. The provider interface is the only model boundary. This phase intentionally does not include external LLM integrations, browser/mobile automation, MCP, or workflow orchestration.
