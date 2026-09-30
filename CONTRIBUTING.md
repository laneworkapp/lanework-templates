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

### File names

The file name must match `^[a-z0-9]+(-[a-z0-9]+)*\.lanework-template$`:
lowercase letters, digits and single hyphens, no leading or trailing
hyphen. Slugs are unique case-insensitively — `basic` and `Basic` can't
both exist, even though that's only enforced by CI, not by your own
filesystem if it happens to be case-insensitive (APFS, the default on a
Mac, silently treats them as the same file; Linux, where CI runs, does
not). `templates/` may hold only `*.lanework-template` files and, if you
want one, a `README.md`; a symlink or any other stray file is refused.

### Rules the schema enforces

`schema/1/`, vendored from the Lanework app — see `schema/1/SOURCE.md`,
kept byte-identical to its source (nothing here is a hand-edit of it):

- **`schema: 1`** is required at the root. Nowhere else in the format is
  it required, but a descriptor is checked stand-alone, with no app and no
  board around it to imply a version. `1` is the only version this repo's
  tooling knows about today; the schema itself only checks that the value
  is a whole number, so `schema: 2` would technically pass CI, and then
  sit in `index.json` hidden from every app that only knows schema 1
  (ADR 0009's filter) — there's no reason to write anything but `1` yet.
- **No `id`, `created` or `modified`**, anywhere — at the root, on a lane,
  or on a card. Those are minted only once the app turns this descriptor
  into a real board; a descriptor has no identity and no history of its
  own.
- **No `order`, on a lane or a card** — a lane's or card's position is its
  index in the `lanes:`/`cards:` list, not a key it carries. (`order` at
  the descriptor *root* is a different, currently-open gap: the schema
  doesn't yet forbid it there, so it's silently accepted as an inert extra
  key. It does nothing — don't rely on it; it's filed upstream to close.)
- **No `cards:` at the root**, and **no `lanes:` inside a lane** or
  **`cards:` inside a card** — nesting only goes as deep as
  `lanes: [ { cards: [ ... ] } ]`.
- Every other key on the root, a lane or a card is checked against the
  real board/lane/card schema, so e.g. a lane's `title` has to be plain
  text on one line, same as a real board.
- **No mapping may repeat a key** (two `title:` keys in the same lane, say).
  Plain YAML allows this and silently keeps the last one; the app's own
  reader refuses it, so this repo's validator does too, even though the
  vendored schema itself has no way to express it.

### `template:`

The chooser's own metadata, read by the app (not carried onto the board it
builds):

- `order` — the template's position in the chooser. Accepted loosely
  (an integer, a whole-number double, or a string of ASCII digits with an
  optional sign — `100`, `100.0` and `"100"` all read as `100`), but
  normalised to a plain integer before it reaches `index.json`. Anything
  else has no reading and is omitted from the index rather than causing an
  error: a fractional value (`1.5`), a value outside the 64-bit signed
  range, a padded string (`" 100 "`), an exponent (`"1e20"`) or non-ASCII
  digits.
- `author: {name, url}` — shown on the template's Gallery row and in the
  chooser's footer. **`url` must be a GitHub profile link**,
  `https://github.com/<user>`, with no control characters and no trailing
  whitespace or newline — nothing else has a reading here, since the
  chooser opens it and shows the GitHub handle beside your name. `name`
  also may not end in whitespace or contain a control character. Both CI
  and the lint script reject anything else.

### No anchors or aliases

YAML anchors and aliases (`&name`, `*name`, and the `<<:` merge that uses
them) are refused, with the line they appear on: a descriptor has no use
for them, and a reader that expands them can be made to hang on a few KiB
of nesting. Write the value out in full.

### Size

A descriptor over 64 KiB is refused outright — no legitimate template
needs to be anywhere near that big, and it bounds how much a single file
can make the validator parse and report on.

## `index.json`

Generated, not hand-written — see **CI**, below. This is the contract the
Gallery client reads, so its shape is documented here rather than left to
be reverse-engineered:

```json
{
  "version": 1,
  "templates": [
    {
      "slug": "bug-tracker",
      "path": "templates/bug-tracker.lanework-template",
      "schema": 1,
      "title": "Bug Tracker",
      "order": 1000,
      "author": {"name": "Your Name", "url": "https://github.com/you"}
    }
  ]
}
```

A top-level object, not a bare array, so it can grow a new top-level key
later without breaking an older app's reader — `version` is the index
format's own version (currently always `1`, independent of a descriptor's
own `schema`). `templates` is one entry per template, kept minimal because
the Gallery client fetches each raw descriptor for everything else (icon,
body, lanes, ...). `slug` and `path` are always present (derived from the
file). `schema` and `title` come from the descriptor, normalised to an
integer and text respectively (see `template:` above). `order` and
`author` are included only when the descriptor's `template:` block sets
them and they have a reading. Don't hand-edit `index.json`; a PR that
touches it will be asked to drop that hunk.

## Before opening a PR

```
pip install -r requirements.txt
scripts/lint.sh
```

This runs the exact same check as CI (`scripts/validate_templates.py`, the
one validator both call), so a green `lint.sh` means a green PR check. It
checks the files git tracks under `templates/` (as CI's clean checkout
does), so a stray `.DS_Store` doesn't turn it red, but a new template must
be `git add`ed before it is linted. Outside a git repo it checks the whole
directory. It
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
  ever touches `index.json`. Runs serialized (`concurrency: index-json`)
  so two merges landing close together can't race to push.
- Both jobs have a `timeout-minutes` cap and read the vendored schema and
  descriptor YAML as data only — nothing here ever executes a descriptor's
  content.

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
