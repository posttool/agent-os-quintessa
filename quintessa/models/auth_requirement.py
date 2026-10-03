from __future__ import annotations

from dataclasses import dataclass

from quintessa.models.auth_kind import AuthKind
from quintessa.models.auth_state import AuthState


@dataclass
class AuthRequirement:
    """What sign-in an app would need, and whether this user has done it."""

    kind: AuthKind = AuthKind.NONE
    state: AuthState = AuthState.SIMULATED
