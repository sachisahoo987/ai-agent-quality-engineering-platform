"""Command-line entry point: ``qa-agent analyse <requirement.json>``.

On success the ``AgentResponse`` is printed as JSON on stdout. On failure an ``ErrorResponse``
is printed as JSON on stderr, next to the logs, so stdout can always be piped as a result.
Every invocation runs in its own trace; its ``trace_id`` is in the output and on every log line.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from autonomous_qa_agent.config.settings import load_settings
from autonomous_qa_agent.container import build_container
from autonomous_qa_agent.error_handling import EXIT_OK, exit_code_for, to_error_response
from autonomous_qa_agent.models.errors import InvalidRequestError
from autonomous_qa_agent.observability.logging import configure_logging, trace_context


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qa-agent", description="Autonomous QA agent")
    parser.add_argument("--env-file", type=Path, help="optional .env file with settings")
    parser.add_argument("--trace-id", help="continue an existing trace (32 lowercase hex chars)")
    commands = parser.add_subparsers(dest="command", required=True)
    analyse = commands.add_parser("analyse", help="analyse a requirement JSON file")
    analyse.add_argument("requirement", help="path to a requirement JSON file, or - for stdin")
    return parser


def _read_requirement(source: str) -> dict[str, object]:
    try:
        text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
        payload = json.loads(text)
    except OSError as exc:
        problem = f"cannot read requirement file: {exc.strerror or type(exc).__name__}"
        raise InvalidRequestError(problem, details=[problem]) from exc
    except json.JSONDecodeError as exc:
        problem = f"requirement is not valid JSON: {exc.msg} (line {exc.lineno})"
        raise InvalidRequestError(problem, details=[problem]) from exc
    if not isinstance(payload, dict):
        problem = "the requirement must be a JSON object"
        raise InvalidRequestError(problem, details=[problem])
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = load_settings(env_file=args.env_file)
    configure_logging(settings.log_level, settings.log_format, stream=sys.stderr)
    container = build_container(settings)

    with trace_context(args.trace_id):
        try:
            payload = _read_requirement(args.requirement)
            response = asyncio.run(container.requirement_analyst.run(payload))
        except Exception as exc:  # every failure goes through the central handler
            error = to_error_response(exc)
            print(error.model_dump_json(indent=2), file=sys.stderr)
            return exit_code_for(error)

    print(response.model_dump_json(indent=2))
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
