#!/usr/bin/env python3
"""Generate index.json from templates/*.lanework-template.

Run by the index workflow after every merge to main (see
.github/workflows/index.yml), and locally to preview the output. Refuses to
index a descriptor that fails validation — the validate job should already
have caught that on the PR, so this is a second, independent check, not the
first one. Also re-checks the directory itself (slug grammar, case-unique,
no symlinks or stray files) for the same reason.

Output shape (documented in CONTRIBUTING.md) — the contract the Gallery
client reads:

    {"version": 1, "templates": [ {...one entry per template...} ]}

Each entry: `slug`, `path`, `schema`, `title`, plus the chooser's own keys
`order` and `author` when the descriptor sets them under `template:`. Kept
minimal — the Gallery client fetches each raw descriptor for everything
else (icon, body, lanes, ...).

Every value is normalised to the app's own "lenient" reading before it
reaches the index — `order: "100"` and `order: 100` produce the same `100`,
and a fractional or otherwise unreadable `order` (`1.5`) is omitted rather
than emitted raw or used to crash the sort. See
`lanework_templates.read_lenient_integer`/`read_lenient_text`.

    python3 scripts/build_index.py                 # print to stdout
    python3 scripts/build_index.py --out index.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import lanework_templates as lt  # noqa: E402

INDEX_VERSION = 1


def entry_for(path: pathlib.Path) -> dict:
    data, error = lt.parse_yaml(path)
    if error is not None:
        raise SystemExit(f"error: {lt.relpath(path)} refusing to index it: {error}")

    problems = lt.validate_data(data)
    if problems:
        lines = "\n".join(f"  {p.pointer}: {p.message}" for p in problems)
        raise SystemExit(f"error: {lt.relpath(path)} fails validation, refusing to index it:\n{lines}")

    slug = path.stem
    schema_value = lt.read_lenient_integer(data["schema"])
    if schema_value is None:
        # Can't actually happen once validate_data has passed: `schema` is
        # common.json#/$defs/schema-version, a plain JSON Schema "integer"
        # (which already admits a whole-number double like 1.0). Guarded
        # anyway rather than emitting a non-integer into the index.
        raise SystemExit(f"error: {lt.relpath(path)} has an unreadable `schema` value, refusing to index it")

    title_value = lt.read_lenient_text(data.get("title", slug))
    if title_value is None:
        title_value = slug

    entry = {
        "slug": slug,
        "path": f"templates/{path.name}",
        "schema": schema_value,
        "title": title_value,
    }

    template_meta = data.get("template")
    if isinstance(template_meta, dict):
        if "order" in template_meta:
            order_value = lt.read_lenient_integer(template_meta["order"])
            if order_value is not None:
                entry["order"] = order_value
            # else: a fractional or unreadable order has no reading (same
            # as the app's own lenient-integer semantics) — omitted, not
            # emitted raw and not a reason to refuse the whole descriptor.

        author = template_meta.get("author")
        if isinstance(author, dict) and author:
            trimmed = {}
            if "name" in author:
                name_value = lt.read_lenient_text(author["name"])
                if name_value is not None:
                    trimmed["name"] = name_value
            if isinstance(author.get("url"), str):
                trimmed["url"] = author["url"]
            if trimmed:
                entry["author"] = trimmed

    return entry


def build(templates_dir: pathlib.Path) -> list[dict]:
    dir_problems = lt.check_templates_directory(templates_dir)
    if dir_problems:
        lines = "\n".join(f"  {lt.relpath(p.file)}: {p.message}" for p in dir_problems)
        raise SystemExit(f"error: {templates_dir} fails its directory rules, refusing to index it:\n{lines}")

    files = sorted(templates_dir.glob("*.lanework-template"))
    entries = [entry_for(f) for f in files]

    collisions = lt.find_case_collisions([e["slug"] for e in entries])
    if collisions:
        lines = "\n".join(f"  {dup!r} collides case-insensitively with {first!r}" for dup, first in collisions.items())
        raise SystemExit(f"error: duplicate slugs, refusing to index:\n{lines}")

    # Deterministic, diff-friendly order: matches the chooser's own tie-break
    # (Board Templates Discovery, chooser card: template.order then title).
    # `order` is now always a plain int or absent (normalised above), so this
    # sort key is never a mix of str and int.
    entries.sort(key=lambda e: (e.get("order", 1 << 30), e["title"]))
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--templates-dir", default=str(lt.TEMPLATES_DIR))
    parser.add_argument("--out", default="-", help="Output path, or - for stdout (default)")
    args = parser.parse_args(argv)

    entries = build(pathlib.Path(args.templates_dir))
    document = {"version": INDEX_VERSION, "templates": entries}
    text = json.dumps(document, indent=2) + "\n"

    if args.out == "-":
        sys.stdout.write(text)
    else:
        pathlib.Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {len(entries)} entries to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
