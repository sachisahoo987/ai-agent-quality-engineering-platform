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
| 2 | LLM interface + mock provider + contract tests | done |
| 3a | Requirement analyst agent, `AgentResponse`, CLI | done |
| 3a+ | Analyst quality iteration: decomposition, domain rules, NFRs, traceability | done |
| 3b | Scenario designer, reviewer, first LangGraph graph | next |
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

## Run the requirement analyst

The requirement analyst validates a requirement, then returns an `AgentResponse` that holds a
`RequirementAnalysis`. The analysis keeps what the requirement **states** apart from what the
analyst **infers**:

| Section | What it holds | Traces to |
|---|---|---|
| `conditions` | Explicit facts: only what the requirement states. Each keeps its `source_text` (verbatim) and `source_location`. Compound statements are split into one condition per action. `kind` is `functional`, `negative` or `non_functional`; a non-functional condition lists its `quality_attributes` (performance, scalability, reliability, availability, security, usability). | the requirement |
| `test_ideas` | Inferred scenarios. `provenance` is `derived` (follows from the stated text, such as the boundaries of a stated limit), `domain_practice` (what testers check for this kind of feature, such as expired OTPs or declined payments) or `llm_suggestion`. | `condition_id` |
| `ambiguities` | Clarifications. `kind` is `ambiguous` (vague wording) or `missing`. `necessity` is `mandatory` (the condition cannot be verified until it is answered) or `recommended` (testing can start). | `condition_id`, or none for the whole requirement |
| `risks` | `category`, `provenance` and the conditions affected | `condition_ids` |
| `assumptions`, `dependencies` | What the analysis took for granted; external systems involved | |

**Condition IDs are stable.** `C-n` is the n-th statement, and a compound statement splits into
`C-n.1`, `C-n.2`, ... Test idea IDs are scoped to their condition (`C-1.2:T-3`), so adding a
statement or an idea does not renumber the others.

**No thresholds are invented.** When a non-functional statement has no measurable threshold
("should load quickly"), the analyst asks a mandatory question instead of assuming a number.
No rule template contains a number, and a test enforces that.

`status` is `needs_clarification` only when a **mandatory** question is open or nothing is
testable; recommendations alone give `completed`. Rules produce the analysis. The configured LLM
can only add test ideas, clarifications and risks that reference existing conditions; it cannot
add conditions. If the LLM fails, the rule-based result is returned with a warning. With the
default mock provider, the output is fully deterministic.

```powershell
uv run qa-agent analyse examples/requirements/banking-login.json  # completed: OTP, session ideas
uv run qa-agent analyse examples/requirements/checkout.json       # completed: 3 conditions
uv run qa-agent analyse examples/requirements/load-time.json      # needs_clarification
uv run qa-agent analyse examples/requirements/login.json          # status: completed
uv run qa-agent analyse examples/requirements/vague-search.json   # status: needs_clarification
Get-Content my-requirement.json | uv run qa-agent analyse -       # read from stdin
uv run python -m autonomous_qa_agent analyse examples/requirements/login.json   # same, as a module
```

The response JSON goes to stdout and the JSON logs go to stderr. Each run has a `trace_id`
that appears in the response and on every log line. Pass `--trace-id <32 hex chars>` to
continue an existing trace.

Failures print an `ErrorResponse` to stderr, holding `code`, a public `message`, safe
`details` and the `trace_id`:

| Exit code | Meaning |
|---|---|
| `0` | success (`completed` or `needs_clarification`) |
| `2` | `invalid_request`: unreadable file, bad JSON, or invalid fields (named in `details`) |
| `1` | anything else; unexpected errors show only `internal_error`, and the traceback is logged |

A requirement is a JSON object:

| Field | Required | Notes |
|---|---|---|
| `id` | yes | letters, digits, `.` `_` `:` `-`, for example `REQ-12` |
| `title` | yes | up to 200 characters |
| `platform` | yes | `web`, `android` or `ios` |
| `description` | one of the two | free text; used for conditions when there are no criteria |
| `acceptance_criteria` | one of the two | list of strings |
| `priority` | no | `critical`, `high`, `medium` (default), `low` |
| `source` | no | ticket URL or file path |

From Python:

```python
import asyncio
from autonomous_qa_agent.container import build_container

requirement = {"id": "REQ-1", "title": "Login", "platform": "web", "description": "It can log in."}
analyst = build_container().requirement_analyst
response = asyncio.run(analyst.run(requirement))
print(response.status, [c.text for c in response.output.edge_cases])
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
  ports/           LLMProvider protocol, LLMRequest/LLMResponse, structured-output parsing
  llm/             MockLLMProvider, provider factory
  agents/          RequirementAnalyst
    requirement_rules/  concepts (shared vocabulary), statements (decomposition),
                        quality (NFR rules), domains (feature rules), engine
  container.py     composition root (the only module that imports adapters)
  error_handling.py  exceptions -> ErrorResponse, exit codes (shared by every entry point)
  cli.py           `qa-agent` command
  workflows/ safety/ tools/ api/   (added in later steps)
examples/requirements/   sample requirements; each one is also a regression test
tests/unit/        mirrors src/
```

## Extending the analyst rules

The rules are data in `src/autonomous_qa_agent/agents/requirement_rules/`:

- **New feature domain:** add a `DomainRule` to `domains.py`: a `Concept` (the words that
  trigger it), test ideas, clarifications (with an optional `answered_by` pattern, so the
  question is skipped when the requirement already states the answer), risks and dependencies.
- **New quality-attribute wording:** add terms to the attribute's `Concept` in `quality.py`, or
  widen its `measurable` pattern.
- **New vocabulary:** add a `Concept` to `concepts.py`. Inflections are matched automatically.

Never put numbers in templates; ask for them in a clarification instead.
