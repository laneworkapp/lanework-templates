#!/usr/bin/env python3
"""Regression check for the validator itself, not for a contributor's PR.

Confirms the four real templates stay green and six known-bad fixtures
(`tests/fixtures/bad/`) stay red, each with its own rule named in the
message. Run this after touching `scripts/lanework_templates.py` or
`schema/1/` (e.g. after `scripts/sync-schema.sh`) to catch a rule silently
going soft.

    python3 scripts/self_test.py
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import lanework_templates as lt  # noqa: E402

FIXTURES_DIR = lt.REPO_ROOT / "tests" / "fixtures" / "bad"

# fixture file -> a substring that must appear in its error message(s).
EXPECTED_BAD = {
    "missing-schema.lanework-template": "missing `schema`",
    "bad-author-url.lanework-template": "must be a GitHub profile",
    "forbidden-id.lanework-template": "is not allowed in a template descriptor",
    "bad-lane-title.lanework-template": "plain text on a single line",
    "wrong-nesting.lanework-template": "is not allowed at the descriptor root",
    "bad-yaml.lanework-template": "invalid YAML",
}


def main() -> int:
    failures: list[str] = []
    good_files = sorted(lt.TEMPLATES_DIR.glob("*.lanework-template"))

    for f in good_files:
        problems = lt.validate_file(f)
        if problems:
            failures.append(f"templates/{f.name}: expected valid, got {[p.message for p in problems]}")
        else:
            print(f"PASS  templates/{f.name} validates clean, as expected")

    for name, needle in EXPECTED_BAD.items():
        path = FIXTURES_DIR / name
        if not path.exists():
            failures.append(f"{name}: fixture file missing at {path}")
            continue
        problems = lt.validate_file(path)
        if not problems:
            failures.append(f"{name}: expected to fail validation, but it passed")
            continue
        messages = " | ".join(p.message for p in problems)
        if needle not in messages:
            failures.append(f"{name}: expected a message containing {needle!r}, got: {messages}")
        else:
            print(f"PASS  tests/fixtures/bad/{name} fails as expected: {messages}")

    if failures:
        print("\nFAILURES:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print(f"\n{len(good_files)} good template(s) and {len(EXPECTED_BAD)} bad fixture(s), all as expected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
