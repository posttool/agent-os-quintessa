from __future__ import annotations

import json
from importlib import resources
from typing import Any

from quintessa.llm import ResilientLLM
from quintessa.llm import schema as s
from quintessa.models import AmbientSource, InputKind

SCHEMA = s.obj(
    {
        "sender": s.string(),
        "device": s.string(),
        "events": s.array(s.string(), "Each item is the full content of one incoming event."),
    }
)


def ambient_templates() -> list[dict[str, Any]]:
    return json.loads(resources.files("quintessa.samples").joinpath("ambient_templates.json").read_text())


async def source_from_template(
    llm: ResilientLLM, template: dict[str, Any], persona: dict[str, Any] | None, count: int = 5
) -> AmbientSource:
    """Write a realistic stream for a template (emails, SMS, a drive to work),
    grounded in the persona when one is given."""
    result = await llm.generate_json(
        system=(
            "You simulate incoming data for a personal agent test harness. Write realistic, "
            "specific events in order, grounded in the person's life. "
            "Respond only with JSON matching the schema."
        ),
        prompt=json.dumps({"template": template, "persona": persona, "count": count}, indent=1),
        schema=SCHEMA,
        purpose="ambient:generate",
    )
    return AmbientSource(
        name=template["name"],
        kind=InputKind(template["kind"]),
        events=result.data["events"],
        interval_seconds=template.get("interval_seconds", 5.0),
        device=result.data["device"] or template.get("device", "phone"),
        sender=result.data["sender"],
    )


VIBE_SCHEMA = s.obj(
    {
        "name": s.string("Short slug for the source."),
        "kind": s.enum_of(InputKind),
        "device": s.string(),
        "sender": s.string(),
        "interval_seconds": s.number("Seconds between events at normal speed."),
        "events": s.array(s.string(), "Each item is the full content of one incoming event."),
    }
)


async def source_from_description(
    llm: ResilientLLM, description: str, persona: dict[str, Any] | None, count: int = 8
) -> AmbientSource:
    """Vibe-code a new ambient source from a plain description, such as
    "a smart oven reporting a roast" or "a flight with a gate change"."""
    result = await llm.generate_json(
        system=(
            "You design simulated ambient data sources for a personal agent test harness. "
            "From the description, pick the input kind and write realistic events in order, "
            "grounded in the person's life when one is given. Respond only with JSON matching the schema."
        ),
        prompt=json.dumps({"description": description, "persona": persona, "count": count}, indent=1),
        schema=VIBE_SCHEMA,
        purpose="ambient:vibe",
    )
    d = result.data
    return AmbientSource(
        name=d["name"],
        kind=InputKind(d["kind"]),
        events=d["events"],
        interval_seconds=max(float(d["interval_seconds"]), 1.0),
        device=d["device"] or "phone",
        sender=d["sender"],
    )
