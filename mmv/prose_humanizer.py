"""Pure functional prose humanization and de-slopping engine.

Based on the Prose Humanizer editorial framework:
- Marker T1: Synthetic vocabulary & cliché purge ('testament to', 'delve', 'tapestry of', 'dance of light and shadow').
- Marker T2/T3: Stripping on-the-nose framing ('we see', 'this panel shows') and moralizing/meta commentary ('creating a sense of...').
- Marker T5: Tightening cadence into grounded sensory nouns and active verbs.
"""
from __future__ import annotations

import re
from typing import Any

# Regex patterns for high-frequency AI prose tropes and replacements
CLICHE_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Marker T1: Synthetic tropes
    (re.compile(r"\b(?:stands?\s+as|serves?\s+as|is)\s+(?:a\s+)?testament\s+to\b", re.IGNORECASE), "is evidence of"),
    (re.compile(r"\b(?:a\s+)?testament\s+to\b", re.IGNORECASE), "evidence of"),
    (re.compile(r"\bdelving\s+into\b", re.IGNORECASE), "entering"),
    (re.compile(r"\bdelved\s+into\b", re.IGNORECASE), "entered"),
    (re.compile(r"\bdelves\s+into\b", re.IGNORECASE), "enters"),
    (re.compile(r"\bdelve\s+into\b", re.IGNORECASE), "enter"),
    (re.compile(r"\b(?:a\s+)?(?:rich\s+|vibrant\s+|complex\s+)?tapestry\s+of\b", re.IGNORECASE), "a mixture of"),
    (re.compile(r"\b(?:a\s+)?(?:delicate\s+|intricate\s+|subtle\s+)?dance\s+of\s+(?:light\s+and\s+shadow|shadow\s+and\s+light|shadows?)\b", re.IGNORECASE), "stark light and deep shadows"),
    (re.compile(r"\bpalpable\s+tension\b", re.IGNORECASE), "heavy stillness"),
    (re.compile(r"\b(?:an?\s+)?unspoken\s+understanding\b", re.IGNORECASE), "a shared glance"),
    (re.compile(r"\b(?:a\s+)?beacon\s+of\s+hope\b", re.IGNORECASE), "a single light"),
    (re.compile(r"\bechoes?\s+of\s+(?:the\s+)?past\b", re.IGNORECASE), "remnants"),

    # Marker T3: Conversational throat-clearing and frame-level narrator artifacts
    (re.compile(r"^(?:in\s+this\s+(?:shot|panel|image|frame)|this\s+(?:shot|panel|image|frame)\s+(?:shows|depicts|features|captures)|we\s+(?:can\s+)?(?:see|observe|witness)|in\s+a\s+world\s+where)\s*,?\s*", re.IGNORECASE), ""),
    (re.compile(r"\bwe\s+(?:can\s+)?see\s+", re.IGNORECASE), ""),

    # Marker T2/T3: Abstract atmosphere tags (trailing purple explanations)
    (re.compile(r",?\s*(?:creating|evoking|adding\s+to|giving)\s+(?:a\s+sense\s+of|an\s+atmosphere\s+of|a\s+feeling\s+of)\s+[^,.;]+([.;]|$)", re.IGNORECASE), r"\1"),
)

PUNCTUATION_CLEANUP: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\s+([,.;])"), r"\1"),
    (re.compile(r",\s*,"), ","),
    (re.compile(r",\s*\."), "."),
    (re.compile(r"\s{2,}"), " "),
)


def humanize_direction(text: str) -> str:
    """Purge synthetic clichés, throat-clearing, and abstract purple prose from a direction string.

    Returns the cleaned, somatically grounded direction preserving concrete nouns and camera directives.
    """
    if not text or not isinstance(text, str):
        return ""

    cleaned = text.strip()
    for pattern, replacement in CLICHE_REPLACEMENTS:
        cleaned = pattern.sub(replacement, cleaned)

    for pattern, replacement in PUNCTUATION_CLEANUP:
        cleaned = pattern.sub(replacement, cleaned)

    cleaned = cleaned.strip()
    # Capitalize the leading character if needed
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]

    return cleaned


def humanize_panels(panels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return an immutable copy of panels with humanized, de-slopped direction texts."""
    return [
        {
            **panel,
            "direction": humanize_direction(str(panel.get("direction", "")))
        }
        for panel in panels
    ]
