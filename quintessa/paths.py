from __future__ import annotations

import hashlib


def user_folder_name(user_id: str) -> str:
    """A file-system-safe name for anything stored per user."""
    return hashlib.sha256(user_id.encode()).hexdigest()[:32]
