# Lanework Templates

Board templates for [Lanework](https://github.com/laneworkapp), the Mac kanban app whose boards are plain folders of Markdown. The New Board chooser lists these templates as the **Gallery**, and the app bundles a few of them so they work offline.

## Key features

- One YAML file per template, `templates/<slug>.lanework-template`. The file name is the template's stable slug, and the extension is Lanework's template type, the same one Save as Template writes.
- A descriptor is shaped like the board it makes: the board's own frontmatter keys, a `body`, and `lanes:` in order. A lane lists its own keys and can carry an optional `cards:` list in the same shape.
- `template:` holds the chooser's keys: `order`, and `author` as `{name, url}`, where `url` is a GitHub profile.
- The app writes every byte of a new board itself. A template carries no attachments, comments or other files.
- Every PR is checked by CI against a vendored copy of the real descriptor schema (`schema/1/`, see `schema/1/SOURCE.md`) — the same check `scripts/lint.sh` runs locally — with a readable message naming the file, the failing value and the rule broken.
- A merge to `main` regenerates `index.json` and commits it automatically; nothing hand-maintains it. Entry shape: `slug`, `path`, `schema`, `title`, plus `order`/`author` when the descriptor sets them — documented in `CONTRIBUTING.md`.
- `CONTRIBUTING.md` covers the format, the lint script, the GitHub-profile-only author link rule, and what review looks for.

## Example

```yaml
schema: 1
title: Bug Tracker
icon: {glyph: ant, color: carnation}
template: {order: 1000, author: {name: Lanework, url: "https://github.com/laneworkapp"}}
body: Chase bugs from first report to verified fix.
lanes:
  - title: Reported
    icon: {glyph: exclamationmark.bubble, color: carnation}
  - title: Closed
    icon: {glyph: checkmark.seal, color: fern}
```

## Status

Seeded 2026-09-28 from the app's original templates. CI validation, the
generated `index.json`, the pre-PR lint script, the vendored JSON Schema and
`CONTRIBUTING.md` landed the same day. See `CONTRIBUTING.md` for how to add
a template. The design record is the Board Templates Discovery board in the
Lanework app repo.
