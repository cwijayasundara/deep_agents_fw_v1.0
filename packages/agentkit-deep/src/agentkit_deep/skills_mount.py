"""Owner-scoped, read-only skills mount.

`skills_mount({"main": [alpha_dir], "sub": [beta_dir]})` builds a backend where
`/skills/<owner>/<skill>/` exposes exactly that owner's skill directories. Each owner gets
its own route, so `SkillsMiddleware(sources=[skills_source(owner)])` lists only that owner's
skills: it `ls`es the *parent* level and treats every sub-directory with a `SKILL.md` as a
skill. Passing a skill directory itself as a source silently yields no skills, which is why
callers take the source from `skills_source` rather than building paths by hand.

Layout: `CompositeBackend(default=StateBackend(), routes={"/skills/<owner>/": view})`, where
each `view` is a `CompositeBackend` over an empty read-only root with one read-only
`FilesystemBackend(root_dir=skill_dir, virtual_mode=True)` route per skill. Writes are
refused twice: by the returned `FilesystemPermission` at the tool layer, and by the
backends themselves for anything that bypasses the tools.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from deepagents import FilesystemPermission
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from deepagents.backends.protocol import (
    FILE_NOT_FOUND,
    PERMISSION_DENIED,
    BackendProtocol,
    DeleteResult,
    EditResult,
    FileDownloadResponse,
    FileUploadResponse,
    GlobResult,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)

SKILLS_ROOT = "/skills/"
_READ_ONLY = "skills are read-only"


def skills_source(owner: str) -> str:
    """The skills *source* (parent level) for `owner`: what `skills=` / `SubAgent.skills` take."""
    return f"{SKILLS_ROOT}{owner}/"


def skills_routes(owners: Mapping[str, Sequence[Path]]) -> dict[str, BackendProtocol]:
    """One read-only route per owner, keyed by `skills_source(owner)`.

    A persistent agent folds these into `memory_backend(...)` instead of `skills_mount`."""
    return {
        skills_source(_segment(owner, "owner")): _owner_view(owner, dirs)
        for owner, dirs in owners.items()
    }


def skills_permissions() -> list[FilesystemPermission]:
    """The tool-level write deny over every skills route."""
    return [FilesystemPermission(operations=["write"], paths=[f"{SKILLS_ROOT}**"], mode="deny")]


def skills_mount(
    owners: Mapping[str, Sequence[Path]],
) -> tuple[BackendProtocol, list[FilesystemPermission]]:
    """Mount each owner's skill directories read-only under `skills_source(owner)`."""
    routes = skills_routes(owners)
    return CompositeBackend(default=StateBackend(), routes=routes), skills_permissions()


def _owner_view(owner: str, dirs: Sequence[Path]) -> BackendProtocol:
    routes: dict[str, BackendProtocol] = {}
    for d in dirs:
        if not d.is_dir():
            raise ValueError(f"skill directory for {owner!r} not found: {d}")
        prefix = f"/{_segment(d.name, 'skill')}/"
        if prefix in routes:
            raise ValueError(f"skill {d.name!r} is mounted twice for {owner!r}")
        routes[prefix] = _ReadOnlySkill(root_dir=d.resolve(), virtual_mode=True)
    return CompositeBackend(default=_EmptyRoot(), routes=routes)


def _segment(name: str, what: str) -> str:
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        raise ValueError(f"invalid {what} name for the skills mount: {name!r}")
    return name


class _ReadOnly(BackendProtocol):
    """Refuses every mutation (the async variants delegate to these by default)."""

    def write(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error=f"{file_path}: {_READ_ONLY}")

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,  # noqa: FBT001, FBT002 - protocol signature
    ) -> EditResult:
        return EditResult(error=f"{file_path}: {_READ_ONLY}")

    def delete(self, file_path: str) -> DeleteResult:
        return DeleteResult(error=f"{file_path}: {_READ_ONLY}")

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=p, error=PERMISSION_DENIED) for p, _ in files]


class _ReadOnlySkill(_ReadOnly, FilesystemBackend):
    """One skill directory, read-only."""


class _EmptyRoot(_ReadOnly):
    """The root of an owner view: holds no files of its own, only the skill routes."""

    def ls(self, path: str) -> LsResult:
        return LsResult(entries=[])

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        return ReadResult(error=f"File '{file_path}' not found")

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        return GrepResult(matches=[])

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        return GlobResult(matches=[])

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return [FileDownloadResponse(path=p, error=FILE_NOT_FOUND) for p in paths]
