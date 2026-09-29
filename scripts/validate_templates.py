#!/usr/bin/env python3
"""Validate .lanework-template descriptors against schema/1/template.json.

This is the one entry point both the pre-PR lint script (`scripts/lint.sh`)
and CI's validation job call, so a local run and CI always agree. See
CONTRIBUTING.md for the format and what review looks for.

    python3 scripts/validate_templates.py            # checks templates/
    python3 scripts/validate_templates.py some.file   # checks one file
"""
from __future__ import annotations

import argparse
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import lanework_templates as lt  # noqa: E402


def _escape_annotation_data(text: str) -> str:
    """GitHub workflow commands escape %, CR and LF the same way in the
    message/data portion of a command."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_annotation_property(text: str) -> str:
    """A command's key=value properties (here, `file=`) additionally escape
    `:` and `,`, per GitHub's own workflow-command escaping rule."""
    return _escape_annotation_data(text).replace(":", "%3A").replace(",", "%2C")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "paths",
        nargs="*",
        default=["templates"],
        help="Files or directories of *.lanework-template descriptors to check (default: templates/)",
    )
    parser.add_argument(
        "--annotate",
        action="store_true",
        help="Also emit GitHub Actions ::error annotations (used by CI, cheap to add locally too)",
    )
    args = parser.parse_args(argv)

    files = lt.collect_files(args.paths)
    if not files:
        print("no *.lanework-template files found", file=sys.stderr)
        return 1

    all_ok = True

    # Directory-level rules (slug grammar, case-unique, no symlinks or
    # stray files) — only meaningful for a directory argument, and only
    # once per directory, not once per file inside it.
    for raw in args.paths:
        p = pathlib.Path(raw)
        if not p.is_dir():
            continue
        for problem in lt.check_templates_directory(p):
            all_ok = False
            rel = lt.relpath(problem.file) if problem.file else lt.relpath(p)
            print(f"FAIL  {rel} {problem.pointer}: {problem.message}", file=sys.stderr)
            if args.annotate:
                file_prop = _escape_annotation_property(rel)
                data = _escape_annotation_data(f"{problem.pointer}: {problem.message}")
                print(f"::error file={file_prop}::{data}")

    for f in files:
        problems = lt.validate_file(f)
        rel = lt.relpath(f)
        if not problems:
            print(f"OK    {rel}")
            continue
        all_ok = False
        for problem in problems:
            line = f"{rel} {problem.pointer}: {problem.message}"
            print(f"FAIL  {line}", file=sys.stderr)
            if args.annotate:
                file_prop = _escape_annotation_property(rel)
                data = _escape_annotation_data(f"{problem.pointer}: {problem.message}")
                print(f"::error file={file_prop}::{data}")

    if all_ok:
        print(f"{len(files)} template(s) valid")
        return 0

    print("descriptor validation failed — see FAIL lines above", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
