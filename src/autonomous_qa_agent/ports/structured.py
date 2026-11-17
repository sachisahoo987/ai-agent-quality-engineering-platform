"""Turn a model's text answer into a validated Pydantic object."""

import json
import re

from pydantic import BaseModel, ValidationError

from autonomous_qa_agent.models.errors import ProviderError
from autonomous_qa_agent.ports.llm import LLMProvider, LLMRequest

# Models often wrap JSON in a Markdown code fence despite being told not to.
_FENCE = re.compile(r"^```(?:json)?\s*(?P<body>.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def parse_structured[ModelT: BaseModel](text: str, schema: type[ModelT]) -> ModelT:
    """Parse ``text`` as JSON matching ``schema``. Raises ``ProviderError`` when it does not."""
    body = text.strip()
    if match := _FENCE.match(body):
        body = match.group("body")
    try:
        return schema.model_validate(json.loads(body))
    except json.JSONDecodeError as exc:
        raise ProviderError(f"model output is not valid JSON: {exc.msg}") from exc
    except ValidationError as exc:
        fields = ", ".join(".".join(map(str, e["loc"])) or "<root>" for e in exc.errors())
        raise ProviderError(f"model output does not match {schema.__name__}: {fields}") from exc


async def generate_structured[ModelT: BaseModel](
    provider: LLMProvider, request: LLMRequest, schema: type[ModelT]
) -> ModelT:
    """Ask ``provider`` for an answer matching ``schema``.

    The schema is attached to the request when the caller did not set one.
    """
    if request.response_schema is None:
        request = request.model_copy(update={"response_schema": schema.model_json_schema()})
    response = await provider.complete(request)
    return parse_structured(response.text, schema)
