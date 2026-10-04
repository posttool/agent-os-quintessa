"""The fixed text Quintessa sends to models, kept out of the code so it can
be read and tuned on its own. Capability prompts live next to their loader in
quintessa/capabilities/; everything else is here.

A prompt is a markdown file. Optional front matter says where it is used and
which {placeholders} it takes; the body is filled with str.format, so a
prompt with placeholders writes a literal brace as {{ or }}. Structured text
(Jev's questions) is YAML."""

from __future__ import annotations

from functools import cache
from importlib import resources
from typing import Any

import yaml


@cache
def _body(name: str) -> str:
    text = resources.files(__name__).joinpath(f"{name}.md").read_text()
    if text.startswith("---"):
        _, _front, text = text.split("---", 2)
    return text.strip()


def prompt(name: str, /, **values: Any) -> str:
    """The prompt `name` (a path under quintessa/prompts/, without .md),
    with its placeholders filled."""
    return _body(name).format(**values) if values else _body(name)


@cache
def data(name: str) -> Any:
    """The YAML file `name` (without .yaml) under quintessa/prompts/."""
    return yaml.safe_load(resources.files(__name__).joinpath(f"{name}.yaml").read_text())
