import io
import json
import logging
import runpy
from collections.abc import Iterator
from pathlib import Path

import pytest

from autonomous_qa_agent.cli import main
from autonomous_qa_agent.config import Settings
from autonomous_qa_agent.container import build_container
from autonomous_qa_agent.error_handling import EXIT_INTERNAL_ERROR, EXIT_INVALID_REQUEST, EXIT_OK
from autonomous_qa_agent.llm import MockLLMProvider

EXAMPLES = Path(__file__).parents[2] / "examples" / "requirements"


@pytest.fixture(autouse=True)
def _remove_cli_log_handler() -> Iterator[None]:
    """The CLI installs a handler on the root logger; don't leak it into other tests."""
    root = logging.getLogger()
    before = list(root.handlers)
    level = root.level
    yield
    for handler in list(root.handlers):
        if handler not in before:
            root.removeHandler(handler)
    root.setLevel(level)


def test_module_entry_point(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["qa-agent", "analyse", str(EXAMPLES / "login.json")])
    with pytest.raises(SystemExit) as info:
        runpy.run_module("autonomous_qa_agent", run_name="__main__")
    assert info.value.code == EXIT_OK
    assert json.loads(capsys.readouterr().out)["status"] == "completed"


def test_container_wires_the_configured_provider() -> None:
    container = build_container(Settings())
    assert isinstance(container.llm, MockLLMProvider)
    assert container.requirement_analyst.name == "requirement_analyst"


@pytest.mark.parametrize(
    ("example", "status"),
    [("login.json", "completed"), ("vague-search.json", "needs_clarification")],
)
def test_analyse_prints_the_agent_response(
    example: str, status: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["analyse", str(EXAMPLES / example)]) == EXIT_OK
    output = json.loads(capsys.readouterr().out)
    assert output["agent"] == "requirement_analyst"
    assert output["status"] == status


def test_analyse_reads_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {"id": "REQ-9", "title": "t", "platform": "web", "description": "It can save."}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert main(["analyse", "-"]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["output"]["requirement_id"] == "REQ-9"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (None, "cannot read requirement file"),
        ("{not json", "requirement is not valid JSON"),
        ("[1, 2]", "must be a JSON object"),
        ('{"id": "REQ-1"}', "platform: Field required"),
    ],
)
def test_analyse_reports_bad_input(
    content: str | None, message: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "requirement.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    assert main(["analyse", str(path)]) == EXIT_INVALID_REQUEST
    captured = capsys.readouterr()
    assert captured.out == ""
    assert '"code": "invalid_request"' in captured.err
    assert message in captured.err


def test_trace_id_is_continued_into_the_response(capsys: pytest.CaptureFixture[str]) -> None:
    trace_id = "0af7651916cd43dd8448eb211c80319c"
    assert main(["--trace-id", trace_id, "analyse", str(EXAMPLES / "login.json")]) == EXIT_OK
    captured = capsys.readouterr()
    assert json.loads(captured.out)["trace_id"] == trace_id
    assert f'"trace_id":"{trace_id}"' in captured.err  # the log lines carry it too


def test_unexpected_errors_are_hidden_from_the_caller(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def broken(*_: object) -> None:
        raise RuntimeError("database password is hunter2")

    monkeypatch.setattr("autonomous_qa_agent.agents.RequirementAnalyst.run", broken)
    assert main(["analyse", str(EXAMPLES / "login.json")]) == EXIT_INTERNAL_ERROR
    captured = capsys.readouterr()
    # stderr holds one-line JSON logs, then the indented ErrorResponse
    error = json.loads(captured.err[captured.err.index('{\n  "code"') :])
    assert "hunter2" not in json.dumps(error)
    assert error["code"] == "internal_error"
    assert error["message"] == "An unexpected error occurred."
    assert len(error["trace_id"]) == 32
