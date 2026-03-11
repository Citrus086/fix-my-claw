"""Clustering logic for anomaly detection."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, TYPE_CHECKING

from .models import Event
from .text_utils import calc_similarity, extract_progress_markers, progress_markers_compatible

if TYPE_CHECKING:
    from ..config import AppConfig


def find_similar_group(
    signature: str,
    groups: list[dict[str, Any]],
    threshold: float,
    progress_markers: tuple[str, ...],
) -> dict[str, Any] | None:
    """Find a similar group for a signature."""
    for group in groups:
        if not progress_markers_compatible(progress_markers, group["progress_markers"]):
            continue
        if calc_similarity(signature, group["representative"]) >= threshold:
            return group
    return None


def assign_clusters(cfg: "AppConfig", events: list[Event]) -> list[Event]:
    """Assign cluster keys to events based on similarity."""
    if not cfg.anomaly_guard.similarity_enabled:
        return events

    groups: list[dict[str, Any]] = []
    clustered: list[Event] = []
    for event in events:
        text = event.normalized_text
        if len(text) < cfg.anomaly_guard.similarity_min_chars:
            clustered.append(event)
            continue
        markers = extract_progress_markers(text)
        group = find_similar_group(
            text,
            groups,
            cfg.anomaly_guard.similarity_threshold,
            markers,
        )
        if group is None:
            group = {
                "key": f"cluster:{len(groups) + 1}",
                "representative": text,
                "progress_markers": markers,
            }
            groups.append(group)
        clustered.append(
            replace(
                event,
                cluster_key=str(group["key"]),
                cluster_representative=str(group["representative"]),
            )
        )
    return clustered
