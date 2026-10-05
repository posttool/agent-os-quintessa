from enum import Enum


class FieldKind(str, Enum):
    DISPLAY_TEXT = "display_text"
    FREE_TEXT = "free_text"
    OPTION = "option"
    MULTI_OPTION = "multi_option"  # pick any number of the options
    SUGGESTION = "suggestion"
    NUMBER = "number"
    LOCATION = "location"
    CONFIRM = "confirm"
    BUTTON = "button"
