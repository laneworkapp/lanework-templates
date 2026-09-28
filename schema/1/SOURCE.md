# Schema source

`board.json`, `lane.json`, `card.json`, `common.json` and `template.json` in
this directory are a vendored copy of `Schema/1/` from the Lanework app repo
(private — CI here cannot fetch it directly, so the copy is checked in).

- **Source commit**: `c013d1d39d115521de73c253830f67756bc903d4`
- **Source path**: `Schema/1/`
- **Synced**: 2026-09-28

Refresh with `scripts/sync-schema.sh <path-to-a-Lanework-checkout>`, which
copies the five files from `<path>/Schema/1/` and rewrites the two lines
above. Re-run `pip install -r requirements.txt && scripts/lint.sh` after a
sync — a new descriptor rule upstream can turn an existing template red.
