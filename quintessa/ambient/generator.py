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
