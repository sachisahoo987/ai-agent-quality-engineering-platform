"""Shared base model, constrained types and helpers for every data contract."""

from collections import Counter
from collections.abc import Iterable
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class ContractModel(BaseModel):
    """Immutable, strict base for data exchanged between components.

    Frozen (no mutation after validation), rejects unknown fields, strips string whitespace.
    Collections are tuples so contracts are deeply immutable and safe to share across nodes.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
"""A string that is not empty after stripping whitespace."""

Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
"""Human-readable, URL- and log-safe identifier such as ``REQ-12`` or ``SC-001:step-3``."""

SecretRef = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Z][A-Z0-9_]{0,127}$")
]
"""Name of a secret (environment-variable style) resolved only at execution time.

Contracts never hold secret values: they are checkpointed, logged and reported.
"""

Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
"""A probability-like score in [0, 1]."""


def find_duplicates(values: Iterable[str]) -> list[str]:
    """Return the values that occur more than once, sorted."""
    return sorted(value for value, count in Counter(values).items() if count > 1)
