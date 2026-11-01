from __future__ import annotations

import re

_URL = re.compile(r"https?://[^\s)\]>\"']+")


def extract_urls(text: str) -> set[str]:
    return {u.rstrip(".,;") for u in _URL.findall(text)}


def citation_scores(report: str, retrieved_text: str) -> dict[str, float]:
    """Deterministic: does the report cite, and are cited URLs ones the agent really retrieved?"""
    cited = extract_urls(report)
    retrieved = extract_urls(retrieved_text)
    return {
        "has_citation": 1.0 if cited else 0.0,
        "citation_validity": (len(cited & retrieved) / len(cited)) if cited else 0.0,
    }
