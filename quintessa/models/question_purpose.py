from enum import Enum


class QuestionPurpose(str, Enum):
    DISAMBIGUATION = "disambiguation"
    PERMISSION = "permission"
    INFORMATION = "information"
