from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class SpecError:
    file: str
    path: str
    message: str
    severity: Literal["error", "warning"] = "error"

    def __str__(self) -> str:
        return f"{self.file}:{self.path}: {self.message}"


class SpecErrors(Exception):
    """A collection of spec problems, reported together."""

    def __init__(self, errors: list[SpecError]) -> None:
        self.errors = list(errors)
        super().__init__("\n".join(str(e) for e in self.errors))

    @property
    def warnings(self) -> list[SpecError]:
        return [e for e in self.errors if e.severity == "warning"]

    def raise_if_errors(self) -> None:
        if any(e.severity == "error" for e in self.errors):
            raise self


def read_utf8(path: Path) -> str:
    """Read a text file; undecodable or unreadable files become SpecErrors naming it."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        msg = f"file is not valid UTF-8: {exc.reason}"
        raise SpecErrors([SpecError(str(path), "", msg)]) from exc
    except OSError as exc:
        raise SpecErrors([SpecError(str(path), "", f"cannot read file: {exc}")]) from exc
