from enum import Enum


class AuthState(str, Enum):
    """SIMULATED: the app is played by a model, so no sign-in happens.
    NEEDED: a real binding needs the user to sign in before calls run.
    CONNECTED: credentials are stored for this user."""

    SIMULATED = "simulated"
    NEEDED = "needed"
    CONNECTED = "connected"
