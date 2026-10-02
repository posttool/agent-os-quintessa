from enum import Enum


class TriggerType(str, Enum):
    TIME = "time"
    LOCATION = "location"
    ACTIVITY = "activity"
    OBSERVATION = "observation"
