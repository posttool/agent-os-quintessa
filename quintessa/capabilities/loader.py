from __future__ import annotations

from pathlib import Path

import yaml

from quintessa.models import Capability

BUILTIN_DIR = Path(__file__).parent


def _read(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    _, front, body = text.split("---", 2)
    return yaml.safe_load(front), body.strip()


def load_capabilities(directory: str | Path | None = None, names: list[str] | None = None) -> dict[str, Capability]:
    """Load capability markdown files (front matter: name, description,
    executor). Files starting with "_" are prompts, not capabilities.
    `names` restricts which capabilities are active."""
    folder = Path(directory) if directory else BUILTIN_DIR
    capabilities: dict[str, Capability] = {}
    for path in sorted(folder.glob("*.md")):
        if path.name.startswith("_"):
            continue
        meta, body = _read(path)
        if names is not None and meta["name"] not in names:
            continue
        capabilities[meta["name"]] = Capability(
            name=meta["name"],
            description=meta["description"],
            executor=meta.get("executor", meta["name"]),
            instructions=body,
            source_path=str(path),
        )
    return capabilities


def load_prompt(name: str, directory: str | Path | None = None) -> str:
    folder = Path(directory) if directory else BUILTIN_DIR
    path = folder / f"_{name}.md"
    if not path.exists():
        path = BUILTIN_DIR / f"_{name}.md"
    return _read(path)[1]
