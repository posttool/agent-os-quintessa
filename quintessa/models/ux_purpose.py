from enum import Enum


class UXPurpose(str, Enum):
    DISAMBIGUATION = "disambiguation"
    PERMISSION = "permission"
    INFORMATION = "information"
