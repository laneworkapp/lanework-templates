"""Shared validation code for lanework-templates.

`validate_templates.py` (the lint script and CI's validation job) and
`build_index.py` (the index job) both import this module, so there is one
code path that knows what a valid `.lanework-template` descriptor looks
like — see CONTRIBUTING.md.

Validation is JSON Schema 2020-12 against the vendored copy of the real
Lanework descriptor schema in `schema/1/` (see `schema/1/SOURCE.md`), using
`jsonschema` + `referencing` so `required`, `const` and `$ref` all work the
way the schema authors intended. YAML is parsed with `yaml.safe_load` only:
a descriptor's content is data, never executed.
"""
from __future__ import annotations

import dataclasses
import json
import os
import pathlib
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "schema" / "1"
TEMPLATES_DIR = REPO_ROOT / "templates"

_SCHEMA_FILES = ("common.json", "board.json", "lane.json", "card.json", "template.json")
_TEMPLATE_SCHEMA_NAME = "template.json"


@dataclasses.dataclass
class Problem:
    """One readable validation failure: where, and what rule it broke."""

    pointer: str
    message: str
    file: pathlib.Path | None = None

    def render(self, file_label: str | None = None) -> str:
        label = file_label if file_label is not None else relpath(self.file) if self.file else "?"
        return f"{label} {self.pointer}: {self.message}"


def relpath(path: pathlib.Path) -> str:
    try:
        return os.path.relpath(path)
    except ValueError:
        return str(path)


def load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text())


_validator_cache: Draft202012Validator | None = None


def get_validator() -> Draft202012Validator:
    """The Draft 2020-12 validator for a descriptor, `$ref`s and all resolved."""
    global _validator_cache
    if _validator_cache is not None:
        return _validator_cache

    # Every schema/1/*.json file's own "$id" is a lanework:/// URI, a scheme
    # Python's urllib.parse (which the `referencing` library uses to join a
    # relative $ref against a base URI) does not know is hierarchical — it
    # leaves "common.json#/$defs/..." unresolved instead of joining it to
    # the referencing file's location. Registering each file under its bare
    # name instead (ignoring "$id") gives relative $refs a base urljoin
    # actually knows how to join, which is what every $ref in this schema
    # set ("board.json#", "common.json#/$defs/...") is written as.
    resources = []
    for name in _SCHEMA_FILES:
        schema = load_schema(name)
        resources.append((name, Resource.from_contents(schema)))
    registry = Registry().with_resources(resources)

    _validator_cache = Draft202012Validator({"$ref": _TEMPLATE_SCHEMA_NAME}, registry=registry)
    return _validator_cache


def parse_yaml(path: pathlib.Path) -> tuple[Any, str | None]:
    """Parse a descriptor's YAML. Never executes anything — safe_load only."""
    text = path.read_text()
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return None, str(exc)
    return data, None


def collect_files(paths: list[str]) -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for raw in paths:
        p = pathlib.Path(raw)
        if p.is_dir():
            files.extend(sorted(p.glob("*.lanework-template")))
        elif p.is_file():
            files.append(p)
        else:
            raise SystemExit(f"error: {raw} not found")
    return files


def _pointer(path: tuple) -> str:
    if not path:
        return "/"
    return "/" + "/".join(str(part) for part in path)


def _forbidden_message(key: Any, path: tuple) -> str:
    if key in ("id", "created", "modified"):
        return (
            f"`{key}` is not allowed in a template descriptor: ids and modification "
            "stamps are assigned only once the app turns this descriptor into a real board"
        )
    if key == "cards":
        if len(path) == 1:
            return (
                "`cards` is not allowed at the descriptor root: a board's starter "
                "cards nest inside a `lanes:` entry, not at the top"
            )
        return "`cards` is not allowed on a starter card: a card carries no starter cards of its own"
    if key == "lanes":
        return "`lanes` is not allowed here: `lanes:` only nests at the descriptor root"
    if key == "order":
        return (
            "`order` is not allowed here: a descriptor lane or card's position is "
            "its index in the list, not an `order` key"
        )
    return f"`{key}` is not allowed in a template descriptor"


def _readable_message(error, path: tuple) -> str:
    key = path[-1] if path else None

    if error.validator == "required":
        missing = list(error.validator_value)
        if missing == ["schema"] or "schema" in missing:
            return "missing `schema`: every descriptor must declare `schema: 1` at its root"
        return f"missing required field(s): {', '.join(missing)}"

    if error.validator == "not":
        return _forbidden_message(key, path)

    if error.validator == "pattern" and key == "url" and "author" in path:
        return f"author url must be a GitHub profile (https://github.com/<user>) — got {error.instance!r}"

    if key == "schema" and error.validator in ("type", "anyOf"):
        return f"`schema` must be an integer (e.g. `schema: 1`), got {error.instance!r}"

    if key == "title" and error.validator in ("anyOf", "type"):
        return "title must be plain text on a single line (a string, number or boolean — not a mapping or list)"

    return error.message


def validate_data(data: Any) -> list[Problem]:
    """Validate an already-parsed descriptor. Returns readable problems, empty if valid."""
    if not isinstance(data, dict):
        kind = "nothing" if data is None else type(data).__name__
        return [Problem(pointer="/", message=f"a template descriptor must be a YAML mapping at the top level, got {kind}")]

    validator = get_validator()
    groups: dict[tuple, list] = {}
    for error in validator.iter_errors(data):
        groups.setdefault(tuple(error.absolute_path), []).append(error)

    problems: list[Problem] = []
    for path in sorted(groups, key=lambda p: tuple(str(part) for part in p)):
        errors = groups[path]
        not_errors = [e for e in errors if e.validator == "not"]
        chosen = not_errors if not_errors else errors
        seen_messages = set()
        for error in chosen:
            message = _readable_message(error, path)
            if message in seen_messages:
                continue
            seen_messages.add(message)
            problems.append(Problem(pointer=_pointer(path), message=message))
    return problems


def validate_file(path: pathlib.Path) -> list[Problem]:
    data, yaml_error = parse_yaml(path)
    if yaml_error is not None:
        return [Problem(pointer="/", message=f"invalid YAML: {yaml_error}", file=path)]
    problems = validate_data(data)
    for problem in problems:
        problem.file = path
    return problems
