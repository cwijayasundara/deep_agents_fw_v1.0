from __future__ import annotations

import re

_URL = re.compile(r"https?://[^\s)\]>\"']+")


def extract_urls(text: str) -> set[str]:
    return {u.rstrip(".,;") for u in _URL.findall(text)}


_SOURCES_HEADING = re.compile(r"^#{1,6}\s*Sources\b", re.IGNORECASE | re.MULTILINE)


def sources_section(report: str) -> float:
    """1.0 if the report has a markdown heading named Sources."""
    return 1.0 if _SOURCES_HEADING.search(report) else 0.0


def source_count_ok(report: str, min_sources: int) -> float:
    return 1.0 if len(extract_urls(report)) >= min_sources else 0.0


def tool_recall(expected: list[str], called: list[str]) -> float:
    """Share of the expected tools that were called at least once; 1.0 when none are expected."""
    want = set(expected)
    return len(want & set(called)) / len(want) if want else 1.0


def citation_scores(report: str, retrieved_text: str) -> dict[str, float]:
    """Deterministic: does the report cite, and are cited URLs ones the agent really retrieved?"""
    cited = extract_urls(report)
    retrieved = extract_urls(retrieved_text)
    return {
        "has_citation": 1.0 if cited else 0.0,
        "citation_validity": (len(cited & retrieved) / len(cited)) if cited else 0.0,
    }
