from enum import Enum


class ToolBinding(str, Enum):
    """How an installed app's calls actually run. Only SIMULATED exists
    today: a model grounded in the app's listing plays the app. The others
    name the real backends an app can later be bound to."""

    SIMULATED = "simulated"
    MCP = "mcp"
    WEB_API = "web_api"
    ANDROID = "android"
