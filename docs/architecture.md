# Architecture

## Principles

1. **Rules decide first; the LLM only adds to them.** Every agent has a rule-based core and
   uses the LLM only to enrich it. The system works with the mock provider; a real model
   improves quality without changing behaviour contracts.
2. **The LLM proposes; a deterministic executor acts.** The planner emits a typed
   `ExecutionPlan` built from a closed set of `ActionType`s. The executor maps each step to
   exactly one MCP tool call. The LLM never picks tools freely.
3. **Each layer has one job.** LangGraph controls the flow. MCP provides the tools. Pydantic
   contracts are the data passed between them.
4. **Dependency rule.** `models ← ports ← agents ← workflows ← api`. The `llm` and `tools`
   adapters implement the interfaces in `ports`. Only `container.py`, the composition root,
   imports adapters. Dependency injection is plain constructor injection, with no framework.
5. **Deny by default.** Every step declares an `ActionRisk`. Unknown tools and hosts are
   refused. Destructive actions need a recorded `ApprovalDecision`.

## Modules

| Module | Responsibility |
|---|---|
| `models` | Immutable Pydantic contracts, enums, domain errors. No I/O. |
| `ports` | `Protocol`s: `LLMProvider`, `ToolGateway`, `ApprovalGate`, `ArtifactStore`, `RunRepository`, `Clock`; provider-independent structured-output parsing |
| `agents` | One class per role. Typed input to typed output; depends on ports only. |
| `workflows` | LangGraph state, graph builder, thin nodes, routing, loop limits, approval pauses |
| `safety` | `PolicyEngine`, `EnvironmentGuard`, secret resolution |
| `llm` | `MockLLMProvider`, provider factory |
| `tools` | MCP session manager, `ActionType` → tool mapper, result normaliser; our own FastMCP servers for Playwright and Appium |
| `api` | FastAPI: start, inspect and resume runs; approvals; reports |
| `observability` | JSON/console logging, context binding, key-based redaction |
| `config` | Typed, immutable settings |

## Agents

| Agent | Input → output | Uses the LLM? |
|---|---|---|
| RequirementAnalyst | `Requirement` → `RequirementAnalysis` (stated conditions, test ideas, mandatory and recommended clarifications, risks, dependencies; all traced to condition ids) | enrich |
| ScenarioDesigner | analysis → `TestScenario[]` (each traces to conditions) | enrich |
| ScenarioReviewer | scenarios → coverage gate; sends work back at most 2 times | no |
| ExecutionPlanner | scenarios + `TargetEnvironment` + app map → `ExecutionPlan` | resolve unclear step wording |
| Executor | plan → `TestResult[]`, with a policy check on every tool call | no |
| FailureAnalyst | failed result + evidence → `FailureAnalysis` | explain |
| HealingAdvisor | analysis + read-only snapshot → `HealingRecommendation[]` | explain |
| Reporter | state → `RunReport` (JSON, Markdown, JUnit) | summary |

Every agent takes an `AgentRequest[Input]` (`request_id`, `trace_id`, typed `input`) and returns
an `AgentResponse[Output]` that echoes both ids and holds the typed output, a `status`
(`completed` or `needs_clarification`), `llm_enriched`, and user-safe `warnings`. A bare input is
wrapped in a new envelope that continues the current trace. LLM enrichment is
additions-only and is merged after the rule results; a `ProviderError` or unusable model output
degrades to the rule-based result with a warning rather than failing the run.

### Requirement analysis rules

The analyst's rule engine (`agents/requirement_rules/`) is data-driven:

```text
Requirement -> statements (criteria, or behaviour sentences) -> split compound statements
            -> one TestableCondition per clause (C-n / C-n.k, with verbatim source_text)
            -> for each condition:
                 stated text    -> derived test ideas (stated limits, required fields)
                 QualityRule    -> non_functional + attributes; mandatory question if no threshold
                 wording        -> mandatory question for unverifiable words ("some", "etc")
                 DomainRule[]   -> domain test ideas, recommended questions, risks, dependencies
                 generic input  -> recommended questions, only when no feature rule applies
            -> requirement level: title, missing criteria, priority / platform / unclear risks
```

- **Concepts are the only vocabulary.** A `Concept` is a named group of related terms, with
  inflections handled. Rules refer to concepts, so each word list exists once.
- **Facts versus inference.** Conditions hold only stated text. Everything the rules infer is
  a `TestIdea` with a `provenance` and a `condition_id`. Domain knowledge never becomes a
  condition.
- **Context-aware questions.** A domain clarification is skipped when its `answered_by` pattern
  matches the requirement. Generic input questions apply only to input-related conditions that
  no feature rule covers. Non-functional conditions never get input or error-handling questions.
- **No invented thresholds.** Quality and domain templates contain no numbers, which a test
  enforces. A missing threshold is a mandatory `missing` clarification.
- **Mandatory versus recommended.** Mandatory questions block testing (vague wording, a missing
  NFR threshold, nothing testable) and set `needs_clarification`. Recommended ones (domain
  details, missing acceptance criteria on a testable requirement) do not.

## Workflow

```text
ingest → analyse → design ⇄ review (≤2) → plan → [approval: plan] → execute (parallel per scenario)
       → collect → all passed? → report
                 → failures   → analyse_failures → recommend_healing → [approval: healing]
                                → verify_healing (re-run affected scenario once) → report
```

- **Approval pauses happen only between phases.** Live MCP sessions can't be
  checkpointed, so the plan pause comes before sessions open and the healing pause after
  they close. The plan approval lists every risky step up front.
- **Healing never edits test source code.** Approved healing is verified by a re-run;
  changing the repository is a separate explicit action.
- The checkpointer is `MemorySaver` to start, then SQLite, with `thread_id = run_id`.

## LangGraph and MCP

```text
FastAPI → RunService → LangGraph (checkpointed)
  execute node → Executor → ToolGateway → PolicyEngine (deny → BLOCKED)
                                        → MCPToolGateway → stdio → playwright_server / appium_server
```

- Each run opens MCP sessions in one async context and calls `list_tools()` to check them;
  a missing tool fails fast.
- Tool risk comes from our own policy configuration, not from what an MCP server says
  about its tools.
- Tool errors are normalised into `ExecutionError` with a category hint. Assertion
  failures are never retried automatically.
- Tests use `FakeToolGateway` and the MCP SDK's in-memory transport.

## Errors and tracing

- **Tracing:** `trace_context()` binds a `trace_id` to every log record in its scope through
  context variables, so it also reaches asyncio tasks. Entry points open one trace per unit of
  work, and agents bind `request_id` and `agent` inside it.
- **Error handling:** `error_handling.to_error_response()` is the single place where
  exceptions become an `ErrorResponse`. A `QAAgentError` returns its `code`, `public_message`
  and public-safe `details`, and its internal message is logged. Any other exception becomes
  `internal_error`, and its traceback is logged. Errors carry the current `trace_id`. The
  FastAPI exception handlers will call the same function.

## Contract decisions

- Contracts are frozen, reject unknown fields, strip whitespace, and use tuples for
  collections.
- Identifiers are readable strings (`REQ-1`, `SC-001`) because they are generated by
  rules and the LLM.
- **Secrets are never stored in contracts.** `ExecutableStep.secret_ref` names an
  environment variable that is resolved only at execution time. Plans are checkpointed,
  logged and reported, so they must never carry secret values.
- `ExecutableStep.risk` has no default.
- Durations are derived from timestamps, never stored separately.
- `RunReport` checks its own consistency: the summary must equal the summary computed
  from the latest attempt per scenario.
- `HealingRecommendation` has no auto-apply flag. Every recommendation needs approval.
- The execution result of one test is `TestResult` (one attempt, with its `StepResult`s); there
  is no separate `TestExecutionResult` type.
- `Ambiguity.kind` separates vague criteria (`ambiguous`) from absent ones (`missing`), so
  missing acceptance criteria reuse the same contract instead of adding a parallel one.
  `Ambiguity.necessity` separates `mandatory` questions from `recommended` ones.
- `RequirementAnalysis` rejects test ideas, clarifications and risks that reference unknown
  condition ids, so traceability cannot silently break. A `Risk` references at least one
  condition.
- LLM enrichment cannot add conditions; explicit facts come only from the requirement text.
  Proposals that reference unknown conditions are dropped rather than failing the run.
