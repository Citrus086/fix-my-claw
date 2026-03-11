"""Anomaly detection data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Event:
    line_index: int
    speaker_role: str
    raw_text: str
    content_text: str
    normalized_text: str
    cluster_key: str = ""
    cluster_representative: str = ""


@dataclass(frozen=True)
class CycleMatch:
    period: int
    repetitions: int
    repeated_turns: int
    start_event_index: int
    end_event_index: int
    involved_roles: tuple[str, ...]
    line_indexes: tuple[int, ...]
    raw_lines: tuple[str, ...]
    pattern: tuple[tuple[str, str], ...]
    cluster_representatives: tuple[str, ...]


@dataclass(frozen=True)
class StagnationMatch:
    event_count: int
    distinct_cluster_count: int
    novel_cluster_ratio: float
    start_event_index: int
    end_event_index: int
    involved_roles: tuple[str, ...]
    line_indexes: tuple[int, ...]
    raw_lines: tuple[str, ...]
    cluster_representatives: tuple[str, ...]
    dominant_cluster_representative: str
    dominant_cluster_count: int


@dataclass(frozen=True)
class DetectorFinding:
    detector: str
    triggered: bool
    kind: str = "symptom"
    involved_roles: tuple[str, ...] = ()
    evidence: tuple[dict[str, Any], ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        out = {
            "detector": self.detector,
            "triggered": self.triggered,
            "kind": self.kind,
            "involved_roles": list(self.involved_roles),
            "evidence": list(self.evidence),
        }
        out.update(self.details)
        return out
