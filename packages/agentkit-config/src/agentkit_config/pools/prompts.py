from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

from agentkit_config.errors import SpecError, SpecErrors, read_utf8
from agentkit_config.pools.frontmatter import split_front_matter
from agentkit_config.registry import Registry

ALLOWED_VARS = {"agent_name", "date"}
MAX_FRAGMENT_DEPTH = 5
FLAT_VERSION = "0.0.0"
_VAR = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_FRAGMENT = re.compile(r"\{\{>\s*([^\s{}]+)\s*\}\}")
_VERSION_FILE = re.compile(r"v(\d+\.\d+\.\d+)")
_NUMERIC = re.compile(r"\d+(\.\d+){0,2}")

Version = tuple[int, int, int]


@dataclass(frozen=True)
class Prompt:
    name: str
    text: str
    source: str
    version: str = FLAT_VERSION
    owner: str | None = None
    eval_suite: str | None = None

    @property
    def prompt_id(self) -> str:
        return f"{self.name}@{self.version}"


def variables(text: str) -> set[str]:
    return set(_VAR.findall(text))


def fragments(text: str) -> list[str]:
    """The refs of every `{{> name}}` include in `text`."""
    return _FRAGMENT.findall(text)


def render(prompt: Prompt, *, agent_name: str, date: str) -> str:
    values = {"agent_name": agent_name, "date": date}
    return _VAR.sub(lambda m: values.get(m.group(1), m.group(0)), prompt.text)


def _ver(v: str) -> Version:
    a, b, c = (int(x) for x in v.split("."))
    return (a, b, c)


def _err(file: str, path: str, msg: str) -> SpecErrors:
    return SpecErrors([SpecError(file, path, msg)])


class PromptRegistry(Registry[Prompt]):
    """Prompts by name (highest version) plus every version and the label table.

    A flat `name.md` is the unversioned prompt at 0.0.0; `name/v1.2.3.md` files are versions."""

    def __init__(self) -> None:
        super().__init__("prompt")
        self._versions: dict[str, dict[Version, Prompt]] = {}
        self._labels: dict[str, dict[str, str]] = {}

    @staticmethod
    def from_roots(roots: Sequence[Path]) -> PromptRegistry:
        reg = PromptRegistry()
        flat: set[str] = set()
        for root in roots:
            base = root / "prompts"
            for path in sorted(base.glob("**/*.md")):
                rel = path.relative_to(base)
                match = _VERSION_FILE.fullmatch(path.stem)
                meta, body = split_front_matter(read_utf8(path), file=str(path))
                text = body.rstrip("\n")
                if match is None:
                    name = rel.with_suffix("").as_posix()
                    reg.register(name, Prompt(name, text, str(path)), source=str(path))
                    reg._versions.setdefault(name, {})[_ver(FLAT_VERSION)] = reg._entries[name]
                    flat.add(name)
                    continue
                name = rel.parent.as_posix()
                version = match.group(1)
                owner, suite = meta.get("owner"), meta.get("eval_suite")
                prompt = Prompt(
                    name,
                    text,
                    str(path),
                    version,
                    None if owner is None else str(owner),
                    None if suite is None else str(suite),
                )
                known = reg._versions.setdefault(name, {})
                if _ver(version) in known:
                    msg = (
                        f"duplicate prompt {name!r}@{version}: defined in both "
                        f"{known[_ver(version)].source} and {path}"
                    )
                    raise _err(str(path), "", msg)
                known[_ver(version)] = prompt
            reg._load_labels(base / "labels.yaml")
        for name, versions in reg._versions.items():
            if name in flat and any(v.version != FLAT_VERSION for v in versions.values()):
                raise _err(
                    versions[max(versions)].source,
                    "",
                    f"prompt {name!r} is both flat and versioned",
                )
            if name not in reg._entries:
                top = versions[max(versions)]
                reg.register(name, top, source=top.source)
        return reg

    def _load_labels(self, path: Path) -> None:
        if not path.is_file():
            return
        data = yaml.safe_load(read_utf8(path)) or {}
        if not isinstance(data, dict):
            raise _err(str(path), "", "labels.yaml must map prompt name to {label: version}")
        for name, labels in data.items():
            if not isinstance(labels, dict):
                raise _err(str(path), str(name), "labels must map label name to a version")
            table = self._labels.setdefault(str(name), {})
            for label, version in labels.items():
                if str(label) in table:
                    raise _err(str(path), f"{name}.{label}", f"duplicate label {label!r}")
                table[str(label)] = str(version)

    def versions(self, name: str) -> list[str]:
        return [v.version for _, v in sorted(self._versions.get(name, {}).items())]

    def label_errors(self) -> list[str]:
        """One message per label that points at a prompt or version that does not exist."""
        out: list[str] = []
        for name, table in sorted(self._labels.items()):
            for label, version in sorted(table.items()):
                if name not in self._versions:
                    out.append(f"label {name}@{label} names an unknown prompt")
                elif not _NUMERIC.fullmatch(version) or version.count(".") != 2:
                    out.append(f"label {name}@{label} is not an exact version: {version!r}")
                elif _ver(version) not in self._versions[name]:
                    avail = ", ".join(self.versions(name))
                    out.append(
                        f"label {name}@{label} points at missing version {version}; "
                        f"available: {avail}"
                    )
        return out

    def get_ref(self, ref: str, *, file: str, path: str) -> Prompt:
        """Resolve `name`, `name@1`, `name@1.2`, `name@1.2.0` or `name@<label>`."""
        name, _, selector = ref.partition("@")
        by_version = self._versions.get(name)
        if by_version is None:
            self.get(name, file=file, path=path)  # raises the unknown-name error
            raise AssertionError  # pragma: no cover
        avail = f"available: {', '.join(self.versions(name))}"
        if not selector:
            return by_version[max(by_version)]
        if _NUMERIC.fullmatch(selector):
            want = tuple(int(x) for x in selector.split("."))
            hits = [v for v in by_version if v[: len(want)] == want]
            if not hits:
                raise _err(file, path, f"prompt {name!r} has no version {selector}; {avail}")
            return by_version[max(hits)]
        target = self._labels.get(name, {}).get(selector)
        if target is None:
            labels = ", ".join(sorted(self._labels.get(name, {}))) or "(none)"
            msg = f"prompt {name!r} has no label {selector!r}; labels: {labels}; {avail}"
            raise _err(file, path, msg)
        if (
            not _NUMERIC.fullmatch(target)
            or target.count(".") != 2
            or _ver(target) not in by_version
        ):
            msg = (
                f"label {selector!r} of prompt {name!r} points at missing version {target}; {avail}"
            )
            raise _err(file, path, msg)
        return by_version[_ver(target)]


def compose(
    prompt: Prompt, prompts: PromptRegistry, *, file: str = "<prompt>", path: str = ""
) -> str:
    """The prompt text with every `{{> name}}` fragment expanded (recursively, depth <= 5).

    A cycle, a missing fragment or too deep a chain is a SpecError, never a RecursionError."""

    def expand(p: Prompt, stack: list[str]) -> str:
        def sub(m: re.Match[str]) -> str:
            ref = m.group(1)
            frag = prompts.get_ref(ref, file=file, path=path)
            if frag.name in stack:
                cycle = " -> ".join([*stack[stack.index(frag.name) :], frag.name])
                raise _err(file, path, f"prompt fragment cycle: {cycle}")
            if len(stack) > MAX_FRAGMENT_DEPTH:
                chain = " -> ".join([*stack, frag.name])
                raise _err(
                    file, path, f"prompt fragments nest deeper than {MAX_FRAGMENT_DEPTH}: {chain}"
                )
            return expand(frag, [*stack, frag.name])

        return _FRAGMENT.sub(sub, p.text)

    return expand(prompt, [prompt.name])
