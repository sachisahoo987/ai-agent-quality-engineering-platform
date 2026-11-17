# Autonomous QA Agent

An autonomous AI QA engineer. It understands requirements, generates test scenarios, plans
execution, drives Playwright and Appium through MCP, analyses failures and recommends
self-healing actions. Every risky step requires human approval.

- **No paid or hosted model is needed.** The application talks to a provider-independent LLM
  interface, and a deterministic mock provider is the default.
- **Claude Code is a development assistant only**, not the runtime.

See [docs/architecture.md](docs/architecture.md) for the design.

## Status

| Step | Scope | State |
|---|---|---|
| 1 | Project setup, settings, structured logging, domain data contracts | done |
| 2 | LLM interface + mock provider + contract tests | next |
| 3 | Requirement analyst, scenario designer, reviewer, first LangGraph graph | planned |
| 4 | Safety policy, execution planner, plan approval pause | planned |
| 5 | MCP tool gateway, Playwright MCP server, executor | planned |
| 6 | Failure analysis, healing advisor, healing approval + verification | planned |
| 7 | Reporter, FastAPI | planned |
| 8 | Appium MCP server, mobile flow | planned |

## Setup

Requires [uv](https://docs.astral.sh/uv/). uv provides Python 3.12 automatically.

```powershell
uv sync
```

> Keep the repository outside `Documents` on machines with Windows Defender
> *Controlled Folder Access* enabled. Otherwise tools such as git, uv and Python
> cannot write there.

## Validate

```powershell
uv run pytest --cov            # unit tests, coverage gate 90%
uv run ruff check .
uv run ruff format --check .
uv run mypy                    # strict
```

## Configuration

Settings come from environment variables; see [.env.example](.env.example).
A `.env` file is read only when passed explicitly, `load_settings(env_file=".env")`.
Values are case-insensitive and invalid values fail at startup.

## Layout

```text
src/autonomous_qa_agent/
  models/          domain contracts (Pydantic only): requirement, scenario, execution plan,
                   results, analysis/healing, approval, report, enums, errors
  config/          typed settings
  observability/   JSON/console logging, context binding, secret redaction
  ports/ agents/ workflows/ safety/ llm/ tools/ api/   (added in later steps)
tests/unit/        mirrors src/
```
