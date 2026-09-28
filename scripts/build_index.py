#!/usr/bin/env python3
"""Generate index.json from templates/*.lanework-template.

Run by the index workflow after every merge to main (see
.github/workflows/index.yml), and locally to preview the output. Refuses to
index a descriptor that fails validation — the validate job should already
have caught that on the PR, so this is a second, independent check, not the
first one.

Entry shape (documented in CONTRIBUTING.md): `slug`, `path`, `schema`,
`title`, plus the chooser's own keys `order` and `author` when the
descriptor sets them under `template:`. Kept minimal — the Gallery client
fetches each raw descriptor for everything else (icon, body, lanes, ...).

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


def entry_for(path: pathlib.Path) -> dict:
    data, yaml_error = lt.parse_yaml(path)
    if yaml_error is not None:
        raise SystemExit(f"error: {lt.relpath(path)} has invalid YAML, refusing to index it: {yaml_error}")

    problems = lt.validate_data(data)
    if problems:
        lines = "\n".join(f"  {p.pointer}: {p.message}" for p in problems)
        raise SystemExit(f"error: {lt.relpath(path)} fails validation, refusing to index it:\n{lines}")

    slug = path.stem
    entry = {
        "slug": slug,
        "path": f"templates/{path.name}",
        "schema": data["schema"],
        "title": data.get("title", slug),
    }

    template_meta = data.get("template")
    if isinstance(template_meta, dict):
        if "order" in template_meta:
            entry["order"] = template_meta["order"]
        author = template_meta.get("author")
        if isinstance(author, dict) and author:
            trimmed = {k: v for k, v in author.items() if k in ("name", "url")}
            if trimmed:
                entry["author"] = trimmed

    return entry


def build(templates_dir: pathlib.Path) -> list[dict]:
    files = sorted(templates_dir.glob("*.lanework-template"))
    entries = [entry_for(f) for f in files]
    # Deterministic, diff-friendly order: matches the chooser's own tie-break
    # (Board Templates Discovery, chooser card: template.order then title).
    entries.sort(key=lambda e: (e.get("order", 1 << 30), e["title"]))
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--templates-dir", default=str(lt.TEMPLATES_DIR))
    parser.add_argument("--out", default="-", help="Output path, or - for stdout (default)")
    args = parser.parse_args(argv)

    entries = build(pathlib.Path(args.templates_dir))
    text = json.dumps(entries, indent=2) + "\n"

    if args.out == "-":
        sys.stdout.write(text)
    else:
        pathlib.Path(args.out).write_text(text)
        print(f"wrote {len(entries)} entries to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
