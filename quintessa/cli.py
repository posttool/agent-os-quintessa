"""Command line harness: `python -m quintessa say "..."`, `personas`, `persona ID`."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from quintessa.llm import LLMError
from quintessa.llm.factory import build_llm
from quintessa.loop import AgentRuntime
from quintessa.models import InputEvent, InputKind, UXFieldKind, UXRequest, UXResponse
from quintessa.persona import AuraPersonaClient, PersonaSimulation
from quintessa.serde import to_dict


def _search_backend():
    if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
        return None
    from quintessa.tools.search import GeminiGroundedSearch

    return GeminiGroundedSearch(project=os.environ["GOOGLE_CLOUD_PROJECT"],
                                location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"))


def _answer_in_terminal(runtime: AgentRuntime):
    async def ask(request: UXRequest) -> None:
        print(f"\n? {request.prompt}")
        values = {}
        for field in request.fields:
            if field.kind in (UXFieldKind.DISPLAY_TEXT, UXFieldKind.BUTTON):
                continue
            hint = f" {field.options}" if field.options else ""
            values[field.name] = await asyncio.to_thread(input, f"  {field.label or field.name}{hint}: ")
        runtime.answer(UXResponse(request.id, values))

    runtime.ux.on_request(lambda r: asyncio.get_running_loop().create_task(ask(r)))


def _print_session(session) -> None:
    print(f"\n[{session.status.value}] {session.trigger.kind.value}: {session.trigger.content[:100]}")
    for step in session.steps:
        print(f"  {step.index}. {step.capability} ({step.model}): {step.summary or step.error}")


async def main_async(args: argparse.Namespace) -> None:
    if args.command == "personas":
        for p in await AuraPersonaClient().list_personas():
            print(f"{p.id}  {p.name}, {p.age}, {p.occupation}, {p.city}")
        return

    memory_path = Path(args.data) / "memory.json"
    try:
        llm = build_llm(args.models)
    except LLMError as e:
        raise SystemExit(f"quintessa: {e}") from e
    runtime = AgentRuntime(llm, data_dir=args.data, search=_search_backend())
    if memory_path.exists() and not args.fresh:
        runtime.store.load(memory_path)
    _answer_in_terminal(runtime)

    if args.command == "say":
        await runtime.run(InputEvent(InputKind.TEXT, " ".join(args.text)))
    elif args.command == "persona":
        sim = PersonaSimulation(runtime, AuraPersonaClient(), speed=args.speed)
        await sim.start(args.id, args.date)
        await sim.wait()
        await runtime.wait_idle()

    for session in sorted(runtime.store.sessions.values(), key=lambda s: s.started_at):
        _print_session(session)
    print("\nbrief:", json.dumps(to_dict(runtime.device.state.brief), indent=1))
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    runtime.store.save(memory_path)
    print(f"memory saved to {memory_path}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="quintessa")
    parser.add_argument("--models", help="model chain, e.g. gemini:gemini-3.8-flash,claude:claude-opus-5-5")
    parser.add_argument("--data", default="data", help="where memory and downloads are kept")
    parser.add_argument("--fresh", action="store_true", help="start with empty memory")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    say = sub.add_parser("say", help="send one text input")
    say.add_argument("text", nargs="+")
    sub.add_parser("personas", help="list Aura personas")
    persona = sub.add_parser("persona", help="replay a persona's day")
    persona.add_argument("id")
    persona.add_argument("--date")
    persona.add_argument("--speed", type=float, default=600.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
