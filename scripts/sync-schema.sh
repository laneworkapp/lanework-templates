#!/usr/bin/env bash
# Refresh schema/1/ from a Lanework app checkout's Schema/1/.
#
# Usage: scripts/sync-schema.sh /path/to/Lanework
#
# The Lanework app repo is private, so CI here can't fetch its schema
# directly — this repo keeps a checked-in copy under schema/1/, and this
# script is how a maintainer with a local checkout refreshes it.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 /path/to/Lanework" >&2
  exit 2
fi

lanework_checkout=$1
src="$lanework_checkout/Schema/1"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dest="$repo_root/schema/1"

if [[ ! -d "$src" ]]; then
  echo "error: $src does not look like a Lanework checkout (no Schema/1/)" >&2
  exit 1
fi

files=(board.json lane.json card.json common.json template.json)
for f in "${files[@]}"; do
  if [[ ! -f "$src/$f" ]]; then
    echo "error: $src/$f is missing" >&2
    exit 1
  fi
done

commit=$(git -C "$lanework_checkout" rev-parse HEAD 2>/dev/null || echo "UNKNOWN")
dirty=""
if ! git -C "$lanework_checkout" diff --quiet -- Schema/1 2>/dev/null; then
  dirty=" (with uncommitted changes to Schema/1/ — commit them first)"
fi

for f in "${files[@]}"; do
  cp "$src/$f" "$dest/$f"
done

cat > "$dest/SOURCE.md" <<EOF
# Schema source

\`board.json\`, \`lane.json\`, \`card.json\`, \`common.json\` and \`template.json\` in
this directory are a vendored copy of \`Schema/1/\` from the Lanework app repo
(private — CI here cannot fetch it directly, so the copy is checked in).

- **Source commit**: \`${commit}\`${dirty}
- **Source path**: \`Schema/1/\`
- **Synced**: $(date -u +%Y-%m-%d)

Refresh with \`scripts/sync-schema.sh <path-to-a-Lanework-checkout>\`, which
copies the five files from \`<path>/Schema/1/\` and rewrites the two lines
above. Re-run \`pip install -r requirements.txt && scripts/lint.sh\` after a
sync — a new descriptor rule upstream can turn an existing template red.
EOF

echo "Synced schema/1/ from $src at commit ${commit}${dirty}"
echo "Now run: pip install -r requirements.txt && scripts/lint.sh"
