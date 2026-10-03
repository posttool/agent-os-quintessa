from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def user_folder_name(user_id: str) -> str:
    """A file-system-safe name for anything stored per user."""
    return hashlib.sha256(user_id.encode()).hexdigest()[:32]


class FileStateBackend:
    """One JSON file per user under `root`. File names are a hash of the user
    id, so any id is safe to use; writes go to a temp file and are renamed
    into place, so a crash mid-write never leaves a half-written state."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, user_id: str) -> Path:
        return self.root / f"{user_folder_name(user_id)}.json"

    async def load(self, user_id: str) -> dict[str, Any] | None:
        path = self.path_for(user_id)
        if not path.exists():
            return None
        return json.loads(await asyncio.to_thread(path.read_text))

    async def save(self, user_id: str, data: dict[str, Any]) -> None:
        text = json.dumps(data)
        await asyncio.to_thread(self._write, self.path_for(user_id), text)

    @staticmethod
    def _write(path: Path, text: str) -> None:
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    async def delete(self, user_id: str) -> None:
        self.path_for(user_id).unlink(missing_ok=True)

    async def list_users(self) -> list[str]:
        users = []
        for path in sorted(self.root.glob("*.json")):
            users.append(json.loads(path.read_text())["user_id"])
        return users
