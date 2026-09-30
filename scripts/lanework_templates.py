"""Shared validation code for lanework-templates.

`validate_templates.py` (the lint script and CI's validation job) and
`build_index.py` (the index job) both import this module, so there is one
code path that knows what a valid `.lanework-template` descriptor looks
like — see CONTRIBUTING.md.

Validation is JSON Schema 2020-12 against the vendored copy of the real
Lanework descriptor schema in `schema/1/` (see `schema/1/SOURCE.md`), using
`jsonschema` + `referencing` so `required`, `const` and `$ref` all work the
way the schema authors intended. YAML is parsed with a `SafeLoader` subclass
only: a descriptor's content is data, never executed, and never a new tag.

A few rules the vendored schema can't express on its own (a JSON Schema
can't refuse a *repeated* mapping key, or fix a regex engine's `$`) live
here instead, as plain Python checks that never touch `schema/1/` — see
`_repo_side_problems` and `check_templates_directory`.
"""
from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import re
import reprlib
import subprocess
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "schema" / "1"
TEMPLATES_DIR = REPO_ROOT / "templates"

_SCHEMA_FILES = ("common.json", "board.json", "lane.json", "card.json", "template.json")
_TEMPLATE_SCHEMA_NAME = "template.json"

# A file bigger than this has no legitimate reason to be a board template,
# and it bounds how much text a pathological descriptor can make us parse
# and re-print in a message. State in CONTRIBUTING.md.
MAX_DESCRIPTOR_BYTES = 64 * 1024

# Any message we build, and any value we echo into one, is capped — a
# deeply alias-nested YAML value can otherwise make a single `repr()` run
# to hundreds of megabytes (measured: a 504-byte file, 155 MB to stderr).
_MESSAGE_LIMIT = 200

_bounded_repr = reprlib.Repr()
_bounded_repr.maxlevel = 3
_bounded_repr.maxlist = 5
_bounded_repr.maxdict = 5
_bounded_repr.maxtuple = 5
_bounded_repr.maxset = 5
_bounded_repr.maxfrozenset = 5
_bounded_repr.maxstring = 80
_bounded_repr.maxlong = 40
_bounded_repr.maxother = 80

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\.lanework-template$")
_ALLOWED_EXTRA_FILES = {"README.md"}

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
_TRAILING_WS_RE = re.compile(r"[ \t\r\n\x0b\x0c]+\Z")


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


def _safe_repr(value: Any) -> str:
    """A `repr()` that can't be made to blow up by a deeply alias-nested
    YAML value: bounded depth, bounded element counts, bounded length."""
    try:
        return _bounded_repr.repr(value)
    except Exception:
        return "<unrepresentable value>"


def _truncate(text: str, limit: int = _MESSAGE_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


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


# ---------------------------------------------------------------------------
# YAML loading: safe, UTF-8 explicit, no duplicate mapping keys.
# ---------------------------------------------------------------------------


class _DuplicateKeyError(Exception):
    """A mapping in the document repeats a key. Carries the key and a
    JSON-pointer-shaped path to where it happened."""

    def __init__(self, key: Any, pointer: str) -> None:
        self.key = key
        self.pointer = pointer
        super().__init__(f"duplicate key {key!r} at {pointer}")


class _AnchorError(Exception):
    """The document uses a YAML anchor (`&name`) or alias (`*name`)."""

    def __init__(self, token: str, line: int) -> None:
        self.token = token
        self.line = line
        super().__init__(f"{token} at line {line}")


class _StrictSafeLoader(yaml.SafeLoader):
    """A `SafeLoader` that refuses a mapping key repeated at any depth, and
    any anchor or alias.

    Anchors and aliases are refused while the node graph is composed, before
    anything is expanded: a descriptor has no use for them, and a consumer
    that expands aliases can be made to hang on a few KiB of nesting.

    PyYAML's ordinary behaviour silently keeps the last of any duplicate key
    (`title: a` then `title: b` in the same mapping just becomes `title:
    b`) — the app's own Yams-based reader refuses this outright. This
    subclass only changes how mapping and sequence NODES become Python
    dicts/lists (still no new tags, still nothing executed, still every
    scalar handled exactly as SafeLoader's own resolvers do); it doesn't
    support YAML's `<<:` merge-key shorthand, which is fine — a descriptor
    has no legitimate use for it.
    """

    def compose_node(self, parent, index):  # noqa: D401 - PyYAML hook
        if self.check_event(yaml.AliasEvent):
            event = self.peek_event()
            raise _AnchorError(f"alias `*{event.anchor}`", event.start_mark.line + 1)
        event = self.peek_event()
        if getattr(event, "anchor", None) is not None:
            raise _AnchorError(f"anchor `&{event.anchor}`", event.start_mark.line + 1)
        return super().compose_node(parent, index)


def _construct_mapping_no_dupes(loader: _StrictSafeLoader, node: yaml.Node) -> dict:
    path: list = getattr(loader, "_lt_path", [])
    mapping: dict = {}
    seen: set = set()
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        try:
            hash(key)
            dedup_key: Any = key
        except TypeError:
            dedup_key = repr(key)
        if dedup_key in seen:
            pointer = "/" + "/".join(str(part) for part in (*path, key))
            raise _DuplicateKeyError(key, pointer)
        seen.add(dedup_key)
        path.append(key)
        loader._lt_path = path
        try:
            value = loader.construct_object(value_node, deep=True)
        finally:
            path.pop()
            loader._lt_path = path
        mapping[key] = value
    return mapping


def _construct_sequence_with_path(loader: _StrictSafeLoader, node: yaml.Node) -> list:
    path: list = getattr(loader, "_lt_path", [])
    result: list = []
    for index, child in enumerate(node.value):
        path.append(index)
        loader._lt_path = path
        try:
            result.append(loader.construct_object(child, deep=True))
        finally:
            path.pop()
            loader._lt_path = path
    return result


_StrictSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping_no_dupes,
)
_StrictSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_SEQUENCE_TAG,
    _construct_sequence_with_path,
)


def parse_yaml(path: pathlib.Path) -> tuple[Any, str | None]:
    """Parse a descriptor's YAML. Returns `(data, None)` or `(None, message)`
    with a message already readable — never a raw traceback for a file
    that's merely too big, not UTF-8, has a duplicate key, or is too deeply
    nested."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        return None, f"could not read this file: {exc}"

    if size > MAX_DESCRIPTOR_BYTES:
        return None, (
            f"descriptor is {size:,} bytes, over the {MAX_DESCRIPTOR_BYTES // 1024} KiB "
            "limit (see CONTRIBUTING.md)"
        )

    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, f"not valid UTF-8: {exc}"

    try:
        data = yaml.load(text, Loader=_StrictSafeLoader)
    except _DuplicateKeyError as exc:
        return None, f"duplicate key {exc.key!r} at {exc.pointer}: a mapping may not repeat a key"
    except _AnchorError as exc:
        return None, (
            f"YAML anchors and aliases (`&name`, `*name`) are not allowed: found {exc.token} "
            f"at line {exc.line} — write the value out in full"
        )
    except RecursionError:
        return None, "descriptor is too deeply nested to parse"
    except yaml.YAMLError as exc:
        return None, f"invalid YAML: {_truncate(str(exc))}"
    return data, None


def list_directory_entries(dir_path: pathlib.Path) -> list[pathlib.Path]:
    """What lint looks at in `dir_path`: the entries git tracks there, so a
    Finder `.DS_Store` or an editor swap file beside the seeds can't turn a
    local run red while CI, from a clean checkout, stays green. Falls back to
    every entry in the directory outside a git repo, when git is missing, or
    when git tracks nothing there yet (a brand-new directory, or a scratch
    copy) — there is nothing to filter by. A tracked entry that isn't on disk
    is dropped (it's a pending deletion); a tracked subdirectory's files
    surface as the subdirectory itself, which the directory rules refuse.
    Note a new template must be `git add`ed before local lint sees it."""
    try:
        result = subprocess.run(
            ["git", "-C", str(dir_path), "ls-files", "-z", "--", "."],
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return sorted(dir_path.iterdir(), key=lambda p: p.name)

    names = {raw.split(b"/", 1)[0].decode("utf-8", "surrogateescape") for raw in result.stdout.split(b"\0") if raw}
    if not names:
        return sorted(dir_path.iterdir(), key=lambda p: p.name)
    entries = [dir_path / name for name in names if (dir_path / name).is_symlink() or (dir_path / name).exists()]
    return sorted(entries, key=lambda p: p.name)


def list_templates(dir_path: pathlib.Path) -> list[pathlib.Path]:
    """The `*.lanework-template` files lint and the indexer read from a directory."""
    return [e for e in list_directory_entries(dir_path) if e.name.endswith(".lanework-template")]


def collect_files(paths: list[str]) -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for raw in paths:
        p = pathlib.Path(raw)
        if p.is_dir():
            files.extend(list_templates(p))
        elif p.is_file():
            files.append(p)
        else:
            raise SystemExit(f"error: {raw} not found")
    return files


def find_case_collisions(names: list[str]) -> dict[str, str]:
    """Maps each name (in the order given) that repeats an earlier one,
    case-insensitively, to the first name it collides with.

    Defence in depth, not a rule that can fire on its own: the slug grammar
    (`^[a-z0-9]+(-[a-z0-9]+)*\\.lanework-template$`) is lowercase-only, so
    two names that both pass it can never differ only by case, and
    `check_templates_directory` only feeds it grammar-valid names. It stays
    a pure string function so it can be tested directly (two case-differing
    files can't coexist on a case-insensitive filesystem, APFS) and so
    `build_index` can re-check the slugs it derived (Q21: the slug keys the
    cache and accessibility ids; CI runs on Linux, where both files really
    could coexist and silently shadow one another if the grammar ever
    loosened)."""
    seen: dict[str, str] = {}
    collisions: dict[str, str] = {}
    for name in names:
        key = name.lower()
        if key in seen:
            collisions[name] = seen[key]
        else:
            seen[key] = name
    return collisions


def check_templates_directory(dir_path: pathlib.Path) -> list[Problem]:
    """Directory-level rules a single descriptor can't see on its own: the
    slug grammar, case-insensitive slug uniqueness, regular files only (no
    symlinks), and nothing in `templates/` besides `*.lanework-template`
    and an optional `README.md`. Only what git tracks there is checked (see
    `list_directory_entries`)."""
    problems: list[Problem] = []
    entries = list_directory_entries(dir_path)
    valid_names: list[str] = []
    valid_entries: dict[str, pathlib.Path] = {}

    for entry in entries:
        name = entry.name
        if entry.is_symlink():
            problems.append(
                Problem(pointer="/", message="is a symlink: templates/ may hold only regular files", file=entry)
            )
            continue
        if name in _ALLOWED_EXTRA_FILES:
            continue
        if not entry.is_file():
            problems.append(
                Problem(
                    pointer="/",
                    message="is not a regular file: templates/ may hold only *.lanework-template files (and an optional README.md)",
                    file=entry,
                )
            )
            continue
        if not _SLUG_RE.match(name):
            problems.append(
                Problem(
                    pointer="/",
                    message=(
                        "doesn't match the slug grammar ^[a-z0-9]+(-[a-z0-9]+)*\\.lanework-template$ "
                        "(and isn't README.md) — templates/ may hold only *.lanework-template files"
                    ),
                    file=entry,
                )
            )
            continue
        valid_names.append(name)
        valid_entries[name] = entry

    for name, first in find_case_collisions(valid_names).items():
        problems.append(
            Problem(pointer="/", message=f"collides case-insensitively with {first}", file=valid_entries[name])
        )
    return problems


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
        return f"author url must be a GitHub profile (https://github.com/<user>) — got {_safe_repr(error.instance)}"

    if key == "schema" and error.validator in ("type", "anyOf"):
        return f"`schema` must be an integer (e.g. `schema: 1`), got {_safe_repr(error.instance)}"

    if key == "title" and error.validator in ("anyOf", "type"):
        return "title must be plain text on a single line (a string, number or boolean — not a mapping or list)"

    return error.message


# ---------------------------------------------------------------------------
# Repo-side rules the vendored schema (byte-identical to its source, never
# hand-edited) can't express.
# ---------------------------------------------------------------------------


def _check_repo_side_text(value: Any, pointer: str) -> list[Problem]:
    if not isinstance(value, str):
        return []
    problems: list[Problem] = []
    core = _TRAILING_WS_RE.sub("", value)
    if core != value:
        problems.append(Problem(pointer=pointer, message="must not end in whitespace or a newline"))
    if _CONTROL_CHAR_RE.search(core):
        problems.append(Problem(pointer=pointer, message="must not contain control characters"))
    return problems


def _repo_side_problems(data: Any) -> list[Problem]:
    """`schema/1/common.json`'s author-url pattern is anchored with `$`,
    which Python's `re` (unlike ECMA-262) matches just before a trailing
    newline — so a url ending in `\\n` passes the vendored schema. Checked
    here instead of by editing schema/1/, which stays byte-identical to its
    source."""
    problems: list[Problem] = []
    if not isinstance(data, dict):
        return problems
    template_meta = data.get("template")
    if isinstance(template_meta, dict):
        author = template_meta.get("author")
        if isinstance(author, dict):
            if "url" in author:
                problems.extend(_check_repo_side_text(author["url"], "/template/author/url"))
            if "name" in author:
                problems.extend(_check_repo_side_text(author["name"], "/template/author/name"))
    return problems


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
            message = _truncate(_readable_message(error, path))
            if message in seen_messages:
                continue
            seen_messages.add(message)
            problems.append(Problem(pointer=_pointer(path), message=message))

    problems.extend(_repo_side_problems(data))
    return problems


def validate_file(path: pathlib.Path) -> list[Problem]:
    data, error = parse_yaml(path)
    if error is not None:
        return [Problem(pointer="/", message=_truncate(error), file=path)]
    problems = validate_data(data)
    for problem in problems:
        problem.file = path
    return problems


# ---------------------------------------------------------------------------
# The app's own "lenient" readings — used by build_index.py to normalise a
# schema-valid but loosely-typed value (a quoted order, a numeric title)
# before it reaches index.json.
# ---------------------------------------------------------------------------


_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1
_ASCII_INTEGER_RE = re.compile(r"[+-]?[0-9]+")


def _int64(value: int) -> int | None:
    return value if _INT64_MIN <= value <= _INT64_MAX else None


def read_lenient_integer(value: Any) -> int | None:
    """`common.json#/$defs/lenient-integer`'s own reading, bounded the way a
    Swift client decoding `Int` is: an integer, a whole-number double, or a
    string of ASCII digits with an optional sign (`[+-]?[0-9]+`, no padding,
    no exponent, no underscores, no non-ASCII digits), and only within
    Int64. A fractional or out-of-range value, or anything else, has no
    reading — returns `None` rather than raising, so the caller can omit the
    field the way the app itself would."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return _int64(value)
    if isinstance(value, float):
        return _int64(int(value)) if value.is_integer() else None
    if isinstance(value, str):
        if _ASCII_INTEGER_RE.fullmatch(value) is None:
            return None
        return _int64(int(value))
    return None


def read_lenient_text(value: Any) -> str | None:
    """`common.json#/$defs/lenient-text`'s own reading: any scalar reads as
    the text the author typed."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value)
    return None
