# Lanework Templates

Board templates for [Lanework](https://github.com/laneworkapp), the Mac kanban app whose boards are plain folders of Markdown. The New Board chooser lists these templates as the **Gallery**, and the app bundles a few of them so they work offline.

## Key features

- One YAML file per template, `templates/<slug>.yaml`. The file name is the template's stable slug.
- A descriptor is shaped like the board it makes: the board's own frontmatter keys, a `body`, and `lanes:` in order. A lane lists its own keys and can carry an optional `cards:` list in the same shape.
- `template:` holds the chooser's keys: `order`, and `author` as `{name, url}`, where `url` is a GitHub profile.
- The app writes every byte of a new board itself. A template carries no attachments, comments or other files.

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

Seeded 2026-09-28 from the app's original templates. Not yet in place: the CI workflow that validates templates and regenerates `index.json`, the pre-PR lint script, the JSON Schema for descriptors, and a contributor guide. The design record is the Board Templates Discovery board in the Lanework app repo.
