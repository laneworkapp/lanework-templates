# Contributing a template

Thanks for adding a board template. Here's the format, how to check it before
opening a PR, and what review looks for.

## The format

A template is one file, `templates/<slug>.lanework-template` — plain YAML,
under Lanework's own `.lanework-template` type (ADR 0012). The file name
*is* the slug: it's the stable id the app, the Gallery cache and this repo's
`index.json` all key on, so don't rename a file once it's shipped.

A descriptor is shaped like the board it will build: the board's own
frontmatter keys, a `body`, and an ordered `lanes:` list. A lane carries its
own keys the same way, plus an optional `cards:` list of starter cards in
the same shape.

```yaml
schema: 1
title: Bug Tracker
icon: {glyph: ant, color: carnation}
template: {order: 1000, author: {name: Your Name, url: "https://github.com/you"}}
body: Chase bugs from first report to verified fix.
lanes:
  - title: Reported
    icon: {glyph: exclamationmark.bubble, color: carnation}
    body: Freshly filed, not yet looked at.
  - title: Closed
    icon: {glyph: checkmark.seal, color: fern}
```

Rules the schema enforces (`schema/1/`, vendored from the Lanework app —
see `schema/1/SOURCE.md`):

- **`schema: 1`** is required at the root. Nowhere else in the format is
  it required, but a descriptor is checked stand-alone, with no app and no
  board around it to imply a version.
- **No `id`, `created`, `modified` or `order`**, anywhere — at the root, on
  a lane, or on a card. Those are minted only once the app turns this
  descriptor into a real board; a descriptor has no identity and no
  history of its own, and a lane's or card's position is its index in the
  list, not a key it carries.
- **No `cards:` at the root**, and **no `lanes:` inside a lane** or
  **`cards:` inside a card** — nesting only goes as deep as
  `lanes: [ { cards: [ ... ] } ]`.
- Every other key on the root, a lane or a card is checked against the
  real board/lane/card schema, so e.g. a lane's `title` has to be plain
  text on one line, same as a real board.

### `template:`

The chooser's own metadata, read by the app (not carried onto the board it
builds):

- `order` — an integer, the template's position in the chooser.
- `author: {name, url}` — shown on the template's Gallery row and in the
  chooser's footer. **`url` must be a GitHub profile link**,
  `https://github.com/<user>` — nothing else has a reading here, since the
  chooser opens it and shows the GitHub handle beside your name. Both CI
  and the lint script reject anything else.

## `index.json`

Generated, not hand-written — see **CI**, below. One entry per template,
kept minimal because the Gallery client fetches each raw descriptor for
everything else (icon, body, lanes, ...). Don't hand-edit it; a PR that
touches it will be asked to drop that hunk.

```json
{
  "slug": "bug-tracker",
  "path": "templates/bug-tracker.lanework-template",
  "schema": 1,
  "title": "Bug Tracker",
  "order": 1000,
  "author": {"name": "Your Name", "url": "https://github.com/you"}
}
```

`slug` and `path` are always present (derived from the file). `schema` and
`title` come from the descriptor. `order` and `author` are included only
when the descriptor's `template:` block sets them.

## Before opening a PR

```
pip install -r requirements.txt
scripts/lint.sh
```

This runs the exact same check as CI (`scripts/validate_templates.py`, the
one validator both call), so a green `lint.sh` means a green PR check. It
prints the file, the JSON pointer of the failing value and the rule broken
for anything red, e.g.:

```
FAIL  templates/my-template.lanework-template /template/author/url: author url must be a GitHub profile (https://github.com/<user>) — got 'https://example.com/me'
```

## What CI does

- **On every PR** (`.github/workflows/validate.yml`): validates every
  descriptor under `templates/` against `schema/1/template.json` — same
  code as `scripts/lint.sh` — and fails the check with a readable message
  per problem. Runs with read-only permissions and no secrets, including
  on PRs from forks.
- **On merge to `main`** (`.github/workflows/index.yml`): regenerates
  `index.json` from `templates/` and commits it straight to `main`. No
  manual step. This is the only workflow with write access, and it only
  ever touches `index.json`.

## What review looks for

CI passing is necessary, not sufficient — the owner reviews every merged
PR by hand for:

- The slug is a good stable name (short, lowercase, hyphenated) you're
  comfortable never renaming.
- The board this template builds actually matches what it claims: lane
  names and order make sense for the stated purpose, icons aren't
  copy-pasted from an unrelated template.
- `template.author.name` is a real name or handle, and the GitHub URL is
  actually yours.
- No template is a near-duplicate of one already in `templates/`.

## Updating the vendored schema

`schema/1/` is a checked-in copy of the Lanework app's own descriptor
schema (that repo is private, so CI here can't fetch it live). If you're a
maintainer with a Lanework checkout, refresh it with:

```
scripts/sync-schema.sh /path/to/Lanework
```

then re-run `scripts/lint.sh` — a new rule upstream can turn an existing
template red, which is exactly what you want to catch before it reaches
`main`.
