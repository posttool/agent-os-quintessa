"""Command line harness: `python -m quintessa --user ID say "..."`, `persona`, `export`, `restore`, `decisions`."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from quintessa.decide import jev_options_from_env
from quintessa.decide.report import agreement_report
from quintessa.llm import LLMError
from quintessa.llm.factory import build_llm
from quintessa.host import AgentHost
from quintessa.loop import AgentRuntime
from quintessa.memory import MemoryStore
from quintessa.models import InputEvent, InputKind, UXFieldKind, UXRequest, UXResponse
from quintessa.persona import AuraPersonaClient, PersonaSimulation
from quintessa.serde import to_dict
from quintessa.state import FileStateBackend, StateFormatError


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

    if args.command == "serve":
        import uvicorn

        from quintessa.api.server import build_app

        config = uvicorn.Config(build_app(args.data), host=args.host, port=args.port, log_level="info")
        await uvicorn.Server(config).serve()
        return

    backend = FileStateBackend(Path(args.data) / "agents")
    if args.command == "users":
        print("\n".join(await backend.list_users()))
        return
    if args.command == "decisions":
        saved = await backend.load(args.user)
        store = MemoryStore()
        if saved is not None:
            store.load_data(saved["memory"])
        print(agreement_report(store.sessions.values()))
        return

    try:
        llm = build_llm(args.models)
    except LLMError as e:
        raise SystemExit(f"quintessa: {e}") from e
    host = AgentHost(llm, backend, data_dir=args.data, search=_search_backend(), **jev_options_from_env())
    agent = await host.agent(args.user)
    _answer_in_terminal(agent)
    before = set(agent.store.sessions)

    if args.command == "say":
        await host.run(args.user, InputEvent(InputKind.TEXT, " ".join(args.text)))
    elif args.command == "persona":
        sim = PersonaSimulation(agent, AuraPersonaClient(), speed=args.speed)
        await sim.start(args.id, args.date)
        await sim.wait()
        await agent.wait_idle()
    elif args.command == "export":
        Path(args.file).write_text(json.dumps(await host.export_state(args.user), indent=1))
        print(f"agent state for {args.user} written to {args.file}")
    elif args.command == "restore":
        try:
            await host.restore_state(args.user, json.loads(Path(args.file).read_text()))
        except (StateFormatError, json.JSONDecodeError) as e:
            raise SystemExit(f"quintessa: cannot restore {args.file}: {e}") from e
        print(f"agent state for {args.user} restored from {args.file}")
    elif args.command == "clear":
        await host.clear(args.user)
        print(f"agent state for {args.user} cleared")

    for session in sorted(agent.store.sessions.values(), key=lambda s: s.started_at):
        if session.id not in before:
            _print_session(session)
    if args.command in ("say", "persona"):
        print("\nbrief:", json.dumps(to_dict(agent.device.state.brief), indent=1))
    await host.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(prog="quintessa")
    parser.add_argument("--user", default=os.environ.get("QUINTESSA_USER", "local"), help="whose agent to use")
    parser.add_argument("--models", help="model chain, e.g. gemini:gemini-3.8-flash,claude:claude-opus-5-5")
    parser.add_argument("--data", default="data", help="where agent state and downloads are kept")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    say = sub.add_parser("say", help="send one text input")
    say.add_argument("text", nargs="+")
    sub.add_parser("personas", help="list Aura personas")
    persona = sub.add_parser("persona", help="replay a persona's day (clears the user's agent first)")
    persona.add_argument("id")
    persona.add_argument("--date")
    persona.add_argument("--speed", type=float, default=600.0)
    export = sub.add_parser("export", help="download the user's agent state to a file")
    export.add_argument("file")
    restore = sub.add_parser("restore", help="replace the user's agent state from a file")
    restore.add_argument("file")
    sub.add_parser("clear", help="clear the user's agent state")
    sub.add_parser("users", help="list users with saved agent state")
    sub.add_parser("decisions", help="how often the Jev shadow agreed with the LLM's next-step choices")
    serve = sub.add_parser("serve", help="run the API and web app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
