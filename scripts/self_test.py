#!/usr/bin/env python3
"""Regression check for the validator and index generator, not for a
contributor's PR.

Confirms: the four real templates stay green; the known-bad fixtures under
`tests/fixtures/bad/` stay red, each with its own rule named; the known-good
edge-case fixtures under `tests/fixtures/good/` stay green; build_index.py
normalises a schema-valid-but-loosely-typed value (a quoted order, a
numeric title) instead of crashing or emitting it raw; and the
directory-level rules (slug grammar, case-unique, no symlinks or stray
files) fire on a synthetic bad directory and stay quiet on the real one.

Run this after touching scripts/lanework_templates.py, scripts/build_index.py
or schema/1/ (e.g. after scripts/sync-schema.sh) to catch a rule silently
going soft.

    python3 scripts/self_test.py
"""
import shutil
import sys
import pathlib
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import lanework_templates as lt  # noqa: E402
import build_index as bi  # noqa: E402

BAD_FIXTURES_DIR = lt.REPO_ROOT / "tests" / "fixtures" / "bad"
GOOD_FIXTURES_DIR = lt.REPO_ROOT / "tests" / "fixtures" / "good"

# fixture file -> a substring that must appear in its error message(s).
EXPECTED_BAD = {
    "missing-schema.lanework-template": "missing `schema`",
    "bad-author-url.lanework-template": "must be a GitHub profile",
    "forbidden-id.lanework-template": "is not allowed in a template descriptor",
    "bad-lane-title.lanework-template": "plain text on a single line",
    "wrong-nesting.lanework-template": "is not allowed at the descriptor root",
    "bad-yaml.lanework-template": "invalid YAML",
    "duplicate-key.lanework-template": "duplicate key",
    "trailing-newline-author-url.lanework-template": "must not end in whitespace or a newline",
}

# good (schema-valid) edge-case fixtures that must validate clean.
GOOD_EDGE_CASES = (
    "quoted-order.lanework-template",
    "numeric-title.lanework-template",
    "fractional-order.lanework-template",
)


def check_seeds_and_fixtures() -> list[str]:
    failures: list[str] = []

    for f in sorted(lt.TEMPLATES_DIR.glob("*.lanework-template")):
        problems = lt.validate_file(f)
        if problems:
            failures.append(f"templates/{f.name}: expected valid, got {[p.message for p in problems]}")
        else:
            print(f"PASS  templates/{f.name} validates clean, as expected")

    for name in GOOD_EDGE_CASES:
        path = GOOD_FIXTURES_DIR / name
        if not path.exists():
            failures.append(f"tests/fixtures/good/{name}: fixture file missing")
            continue
        problems = lt.validate_file(path)
        if problems:
            failures.append(f"tests/fixtures/good/{name}: expected valid, got {[p.message for p in problems]}")
        else:
            print(f"PASS  tests/fixtures/good/{name} validates clean, as expected")

    for name, needle in EXPECTED_BAD.items():
        path = BAD_FIXTURES_DIR / name
        if not path.exists():
            failures.append(f"tests/fixtures/bad/{name}: fixture file missing")
            continue
        problems = lt.validate_file(path)
        if not problems:
            failures.append(f"tests/fixtures/bad/{name}: expected to fail validation, but it passed")
            continue
        messages = " | ".join(p.message for p in problems)
        if needle not in messages:
            failures.append(f"tests/fixtures/bad/{name}: expected a message containing {needle!r}, got: {messages}")
        else:
            print(f"PASS  tests/fixtures/bad/{name} fails as expected: {messages}")

    return failures


def check_build_index_normalization() -> list[str]:
    """Review round 1, BLOCKING 1: a quoted order or a numeric title used to
    crash build_index.py's sort (str vs int), and schema/order/title values
    reached the index raw. Runs the mix through build_index itself, not
    only through the validator."""
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        for f in lt.TEMPLATES_DIR.glob("*.lanework-template"):
            shutil.copy(f, tmp_path / f.name)
        for name in GOOD_EDGE_CASES:
            shutil.copy(GOOD_FIXTURES_DIR / name, tmp_path / name)

        try:
            entries = bi.build(tmp_path)
        except TypeError as exc:
            failures.append(f"build_index.build() crashed on mixed lenient order/title values: {exc}")
            return failures

    by_slug = {e["slug"]: e for e in entries}

    quoted = by_slug.get("quoted-order")
    if quoted is None or quoted.get("order") != 100 or not isinstance(quoted.get("order"), int):
        failures.append(f"quoted-order: expected order 100 (int), got {quoted!r}")
    else:
        print("PASS  build_index normalises template.order: \"100\" (quoted) -> 100 (int)")

    numeric_title = by_slug.get("numeric-title")
    if numeric_title is None or numeric_title.get("title") != "1984":
        failures.append(f"numeric-title: expected title '1984' (str), got {numeric_title!r}")
    elif "order" in numeric_title:
        failures.append(f"numeric-title: expected no order key (none set), got {numeric_title.get('order')!r}")
    else:
        print("PASS  build_index normalises title: 1984 (int) -> \"1984\" (str), no order key")

    fractional = by_slug.get("fractional-order")
    if fractional is not None and "order" in fractional:
        failures.append(f"fractional-order: expected order omitted (fractional, unreadable), got {fractional.get('order')!r}")
    else:
        print("PASS  build_index omits a fractional order (1.5) rather than emitting it raw")

    for entry in entries:
        if not isinstance(entry["schema"], int):
            failures.append(f"{entry['slug']}: expected schema as int, got {entry['schema']!r}")

    return failures


def check_directory_rules() -> list[str]:
    failures: list[str] = []

    real = lt.check_templates_directory(lt.TEMPLATES_DIR)
    if real:
        failures.append(f"templates/ itself: expected no directory problems, got {[p.message for p in real]}")
    else:
        print("PASS  templates/ has no directory-level problems, as expected")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        (tmp_path / "ok.lanework-template").write_text("schema: 1\n", encoding="utf-8")
        (tmp_path / "README.md").write_text("# templates\n", encoding="utf-8")
        (tmp_path / "Bad Name.lanework-template").write_text("schema: 1\n", encoding="utf-8")
        (tmp_path / "stray.txt").write_text("not a template\n", encoding="utf-8")
        (tmp_path / "linked.lanework-template").symlink_to(tmp_path / "ok.lanework-template")

        problems = {p.file.name: p.message for p in lt.check_templates_directory(tmp_path)}

    expectations = {
        "Bad Name.lanework-template": "slug grammar",
        "stray.txt": "slug grammar",
        "linked.lanework-template": "symlink",
    }
    for name, needle in expectations.items():
        if name not in problems:
            failures.append(f"synthetic bad dir: expected a problem on {name}, found none")
        elif needle not in problems[name]:
            failures.append(f"synthetic bad dir: expected {name}'s problem to mention {needle!r}, got: {problems[name]}")
        else:
            print(f"PASS  synthetic templates/ dir: {name} -> {problems[name]}")
    for name in ("ok.lanework-template", "README.md"):
        if name in problems:
            failures.append(f"synthetic bad dir: expected no problem on {name}, got: {problems[name]}")

    collisions = lt.find_case_collisions(["basic.lanework-template", "Basic.lanework-template", "other.lanework-template"])
    if collisions != {"Basic.lanework-template": "basic.lanework-template"}:
        failures.append(f"find_case_collisions: unexpected result {collisions!r}")
    else:
        print("PASS  find_case_collisions flags a case-only duplicate (untestable via real files on APFS)")

    return failures


def check_size_cap_and_encoding() -> list[str]:
    """N5 (size cap) and N6 (explicit UTF-8) — generated at test time rather
    than committed as fixtures, so a 64 KiB-plus file and a non-UTF-8 byte
    string don't have to live in the repo."""
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)

        big = tmp_path / "big.lanework-template"
        big.write_text("schema: 1\ntitle: " + ("x" * (lt.MAX_DESCRIPTOR_BYTES + 100)) + "\n", encoding="utf-8")
        problems = lt.validate_file(big)
        messages = " | ".join(p.message for p in problems)
        if not problems or "KiB" not in messages:
            failures.append(f"oversized descriptor: expected a size-limit message, got: {messages or '(none)'}")
        else:
            print(f"PASS  a {big.stat().st_size:,}-byte descriptor is refused: {messages}")

        bad_utf8 = tmp_path / "bad-utf8.lanework-template"
        bad_utf8.write_bytes(b"schema: 1\ntitle: \xff\xfe not utf-8\n")
        problems = lt.validate_file(bad_utf8)
        messages = " | ".join(p.message for p in problems)
        if not problems or "UTF-8" not in messages:
            failures.append(f"non-UTF-8 descriptor: expected a readable UTF-8 message, got: {messages or '(none)'}")
        else:
            print(f"PASS  a non-UTF-8 descriptor gets a readable message, not a traceback: {messages}")

    return failures


def main() -> int:
    failures: list[str] = []
    failures += check_seeds_and_fixtures()
    failures += check_build_index_normalization()
    failures += check_directory_rules()
    failures += check_size_cap_and_encoding()

    if failures:
        print("\nFAILURES:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    good_count = len(list(lt.TEMPLATES_DIR.glob("*.lanework-template"))) + len(GOOD_EDGE_CASES)
    print(f"\n{good_count} good descriptor(s), {len(EXPECTED_BAD)} bad fixture(s), "
          "build_index normalization and directory rules — all as expected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
