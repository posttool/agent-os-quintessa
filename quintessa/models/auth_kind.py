from enum import Enum


class AuthKind(str, Enum):
    NONE = "none"
    OAUTH = "oauth"
    API_KEY = "api_key"
