#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Shared utilities for relation classification components."""

from __future__ import annotations

from typing import Any, Optional, Sequence, Tuple

LABEL_LIST = [
    "has_symptom",
    "has_cause",
    "needs_diagnosis",
    "uses_treatment",
    "belongs_to_department",
    "no_relation",
]
LABEL_TO_ID = {label: idx for idx, label in enumerate(LABEL_LIST)}
ID_TO_LABEL = {idx: label for label, idx in LABEL_TO_ID.items()}


def normalize_span(value: Any) -> Optional[Tuple[int, int]]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return int(value[0]), int(value[1])
        except (TypeError, ValueError):
            return None
    return None


def insert_entity_markers(
    text: str,
    head_span: Optional[Sequence[int]],
    tail_span: Optional[Sequence[int]],
    head_text: str,
    tail_text: str,
    head_tag: str = "e1",
    tail_tag: str = "e2",
) -> str:
    """Wrap entity spans with special markers for encoder awareness."""
    if head_span and tail_span and len(head_span) == 2 and len(tail_span) == 2:
        spans = [
            (int(head_span[0]), int(head_span[1]), f"<{head_tag}>", f"</{head_tag}>", "head"),
            (int(tail_span[0]), int(tail_span[1]), f"<{tail_tag}>", f"</{tail_tag}>", "tail"),
        ]
        spans.sort(key=lambda x: x[0])
        pieces = []
        last_idx = 0
        for start, end, open_tag, close_tag, _ in spans:
            start = max(0, start)
            end = max(start, end)
            pieces.append(text[last_idx:start])
            pieces.append(open_tag)
            pieces.append(text[start:end])
            pieces.append(close_tag)
            last_idx = end
        pieces.append(text[last_idx:])
        return "".join(pieces)
    return f"<{head_tag}>{head_text}</{head_tag}> <{tail_tag}>{tail_text}</{tail_tag}> " + text
