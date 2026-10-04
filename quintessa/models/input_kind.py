from enum import Enum


class InputKind(str, Enum):
    TEXT = "text"
    SPEECH = "speech"
    MESSAGE = "message"
    LOCATION = "location"
    VISION = "vision"
    SCREEN = "screen"
    NOTIFICATION = "notification"
    SENSOR = "sensor"
    PROCESS_PROGRESS = "process_progress"
