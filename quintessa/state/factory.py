from __future__ import annotations

from pathlib import Path

from quintessa import config
from quintessa.state.file_backend import FileStateBackend
from quintessa.state.sql_backend import SqlStateBackend
from quintessa.state.state_backend import StateBackend


def state_backend_from_env(data_dir: str | Path = "data") -> StateBackend:
    """QUINTESSA_STATE=file keeps the old one-JSON-file-per-user store.
    Otherwise state lives in QUINTESSA_DATABASE_URL (default: a SQLite file
    in data_dir), and any users still in data_dir/agents are imported."""
    files = Path(data_dir) / "agents"
    if config.state_kind() == "file":
        return FileStateBackend(files)
    url = config.database_url() or f"sqlite:///{Path(data_dir) / 'quintessa.db'}"
    return SqlStateBackend(url, import_from=files)
