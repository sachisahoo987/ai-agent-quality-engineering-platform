import pytest
from pydantic import BaseModel, ValidationError

from autonomous_qa_agent.llm import MockLLMProvider
from autonomous_qa_agent.models import ProviderError
from autonomous_qa_agent.ports import LLMRequest, generate_structured, parse_structured


class Answer(BaseModel):
    verdict: str
    score: int


@pytest.mark.parametrize(
    "text",
    [
        '{"verdict": "ok", "score": 3}',
        '  ```json\n{"verdict": "ok", "score": 3}\n```  ',
        '```\n{"verdict": "ok", "score": 3}\n```',
    ],
)
def test_parse_structured_accepts_plain_and_fenced_json(text: str) -> None:
    assert parse_structured(text, Answer) == Answer(verdict="ok", score=3)


def test_parse_structured_rejects_non_json() -> None:
    with pytest.raises(ProviderError, match="not valid JSON"):
        parse_structured("Sure! Here it is.", Answer)


def test_parse_structured_names_mismatched_fields() -> None:
    with pytest.raises(ProviderError, match="does not match Answer: score") as info:
        parse_structured('{"verdict": "ok", "score": "high"}', Answer)
    assert isinstance(info.value.__cause__, ValidationError)


def test_parse_structured_reports_root_level_mismatch() -> None:
    with pytest.raises(ProviderError, match="<root>"):
        parse_structured("[1, 2]", Answer)


async def test_generate_structured_attaches_the_schema() -> None:
    llm = MockLLMProvider({"judge": '{"verdict": "ok", "score": 1}'})
    req = LLMRequest(task="judge", system="s", prompt="p")

    assert await generate_structured(llm, req, Answer) == Answer(verdict="ok", score=1)
    assert llm.requests[0].response_schema == Answer.model_json_schema()


async def test_generate_structured_keeps_an_explicit_schema() -> None:
    llm = MockLLMProvider({"judge": '{"verdict": "ok", "score": 1}'})
    req = LLMRequest(task="judge", system="s", prompt="p", response_schema={"type": "object"})
    await generate_structured(llm, req, Answer)
    assert llm.requests[0].response_schema == {"type": "object"}


@pytest.mark.parametrize(
    "fields",
    [{"task": "bad task"}, {"system": " "}, {"temperature": 3.0}, {"max_output_tokens": 0}],
)
def test_llm_request_is_validated(fields: dict[str, object]) -> None:
    data: dict[str, object] = {"task": "t", "system": "s", "prompt": "p"} | fields
    with pytest.raises(ValidationError):
        LLMRequest.model_validate(data)
