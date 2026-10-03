from enum import Enum


class ToolKind(str, Enum):
    BUILTIN = "builtin"
    LLM = "llm"
    WEB_API = "web_api"
    MCP = "mcp"
    CODE = "code"
    APP = "app"
