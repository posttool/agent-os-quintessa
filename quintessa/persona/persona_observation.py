from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PersonaObservation:
    """One ambient observation from a persona's simulated day, as stored by
    the Aura persona service: {time, device, type, data, senderApp, sender}."""

    date: str
    time: str
    device: str
    type: str
    data: str
    sender_app: str = ""
    sender: str = ""
    id: str = ""
