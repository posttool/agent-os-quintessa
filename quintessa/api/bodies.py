"""Request bodies for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel

from quintessa.device import FOCUSED
from quintessa.models import InputKind, OversightLevel, ToolKind


class InputBody(BaseModel):
    kind: InputKind = InputKind.TEXT
    content: str
    sender: str = ""
    device: str = "phone"


class AnswerBody(BaseModel):
    values: dict[str, str] = {}
    dismissed: bool = False
    surface_context: str = ""


class ViewBody(BaseModel):
    document_id: str
    section_ids: list[str] | None = None  # None: drop the user's choice and refocus
    mode: str = FOCUSED


class ParameterBody(BaseModel):
    name: str
    type: str = "string"
    description: str = ""
    required: bool = True


class FunctionBody(BaseModel):
    name: str
    description: str = ""
    parameters: list[ParameterBody] = []
    returns: str = "string"
    oversight: OversightLevel = OversightLevel.AUTO
    long_running: bool = False


class ToolBody(BaseModel):
    name: str
    description: str
    kind: ToolKind = ToolKind.LLM
    functions: list[FunctionBody] = []
    grounding: str = ""
    endpoint: str = ""
    code: str = ""


class SourceBody(BaseModel):
    name: str
    kind: InputKind
    events: list[str]
    interval_seconds: float = 5.0
    device: str = "phone"
    sender: str = ""
    loop: bool = False


class TemplateSourceBody(BaseModel):
    template: str
    count: int = 6


class VibeSourceBody(BaseModel):
    description: str
    count: int = 8


class SourcePatch(BaseModel):
    speed: float | None = None
    enabled: bool | None = None


class EnabledBody(BaseModel):
    enabled: bool


class PersonaStartBody(BaseModel):
    persona_id: str
    date: str | None = None
    speed: float = 600.0


class PreferencesBody(BaseModel):
    """Only the fields sent change; null returns a setting to the platform default."""

    jev: bool | None = None
    jev_shadow: bool | None = None
    jev_filter: bool | None = None
    jev_drive: bool | None = None
    jev_rank: bool | None = None


class AppListingBody(BaseModel):
    app_id: str
    title: str
    store: str = ""
    developer: str = ""
    icon_url: str = ""
    category: str = ""
    rating: float | None = None
    store_url: str = ""
    summary: str = ""


class SettingsBody(BaseModel):
    chain: list[str]
    retries: int = 2
    base_delay: float = 1.0
