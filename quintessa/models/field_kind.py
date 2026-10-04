from enum import Enum


class FieldKind(str, Enum):
    DISPLAY_TEXT = "display_text"
    FREE_TEXT = "free_text"
    OPTION = "option"
    SUGGESTION = "suggestion"
    NUMBER = "number"
    LOCATION = "location"
    CONFIRM = "confirm"
    BUTTON = "button"
