from enum import Enum


class OversightLevel(str, Enum):
    """How much user oversight a tool function needs, from least to most.

    AUTO              run without asking
    AUTO_FROM_MEMORY  run, filling arguments from memory
    CONFIRM_ONCE      ask the first time; the answer is kept in memory
    ALWAYS_ASK        needs a grant within the current reasoning session (for
                      example spending money); a grant given earlier in the
                      same session carries forward
    """

    AUTO = "auto"
    AUTO_FROM_MEMORY = "auto_from_memory"
    CONFIRM_ONCE = "confirm_once"
    ALWAYS_ASK = "always_ask"
