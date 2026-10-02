import pytest

from quintessa.llm import InvalidOutputError
from quintessa.llm import schema as s

SCHEMA = s.obj(
    {
        "name": s.string(),
        "kind": s.enum_of(["a", "b"]),
        "score": s.number(),
        "tags": s.array(s.string()),
        "parent": s.nullable(s.obj({"id": s.string()})),
    }
)


def test_valid_output_passes():
    s.validate({"name": "x", "kind": "a", "score": 1, "tags": ["t"], "parent": None}, SCHEMA)
    s.validate({"name": "x", "kind": "b", "score": 1.5, "tags": [], "parent": {"id": "p"}}, SCHEMA)


@pytest.mark.parametrize(
    "bad",
    [
        {"name": "x", "kind": "c", "score": 1, "tags": [], "parent": None},
        {"name": "x", "kind": "a", "score": "1", "tags": [], "parent": None},
        {"name": "x", "kind": "a", "score": 1, "tags": [3], "parent": None},
        {"name": "x", "kind": "a", "score": 1, "tags": []},
        {"name": "x", "kind": "a", "score": 1, "tags": [], "parent": {}},
    ],
)
def test_invalid_output_fails(bad):
    with pytest.raises(InvalidOutputError):
        s.validate(bad, SCHEMA)


def test_schemas_are_closed():
    assert SCHEMA["additionalProperties"] is False
    assert SCHEMA["required"] == list(SCHEMA["properties"])
