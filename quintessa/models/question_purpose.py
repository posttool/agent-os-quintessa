from enum import Enum


class QuestionPurpose(str, Enum):
    DISAMBIGUATION = "disambiguation"
    PERMISSION = "permission"
    INFORMATION = "information"
    # a finished session offers what the user can do next; nothing waits on it
    NEXT_STEP = "next_step"
