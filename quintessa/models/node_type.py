from enum import Enum


class NodeType(str, Enum):
    PERSONAL_PREFERENCE = "personal_preference"
    PROJECT_CONTEXT = "project_context"
    AMBIENT_STATE = "ambient_state"
    TOOL_KNOWLEDGE = "tool_knowledge"
    ACTIVE_PROCESS = "active_process"
    DOCUMENT = "document"
    PERSON = "person"
    ROUTINE = "routine"
