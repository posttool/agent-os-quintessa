from quintessa.clock import now
from quintessa.models import (
    Document,
    DocumentSection,
    DocumentStatus,
    InputEvent,
    InputKind,
    KeyDate,
    Permission,
    ReasoningSession,
    TraceStep,
)
from quintessa.serde import from_dict, to_dict


def test_document_round_trip():
    doc = Document(
        id="doc-math",
        title="Math test prep",
        status=DocumentStatus.ACTIVE,
        sections=[DocumentSection("s1", "Graphing", status="not started", actions_taken=["quiz"])],
        key_dates=[KeyDate("2026-05-29 16:00", "Test in testing center 4A", tentative=True)],
    )
    data = to_dict(doc)
    assert data["status"] == "active"
    assert isinstance(data["created_at"], str)
    assert from_dict(Document, data) == doc


def test_session_round_trip():
    session = ReasoningSession(trigger=InputEvent(InputKind.TEXT, "hi"))
    session.steps.append(TraceStep(0, "memory", "save", "because", output={"a": [1]}, ended_at=now()))
    session.permissions.append(Permission("t", "f", True, "session"))
    assert from_dict(ReasoningSession, to_dict(session)) == session
