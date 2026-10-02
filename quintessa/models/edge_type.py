from enum import Enum


class EdgeType(str, Enum):
    RELATES_TO = "relates_to"
    EXECUTING_FOR = "executing_for"
    PART_OF = "part_of"
    DEPENDS_ON = "depends_on"
    CONFLICTS_WITH = "conflicts_with"
    SUPERSEDES = "supersedes"
    MENTIONS = "mentions"
