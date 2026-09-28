#!/usr/bin/env bash
# Pre-PR check: run this before opening a pull request.
#
# Calls the exact same validator as CI's validation job
# (.github/workflows/validate.yml) — scripts/validate_templates.py — so a
# green run here means a green PR check. See CONTRIBUTING.md.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python3 -c "import jsonschema, referencing, yaml" 2>/dev/null || {
  echo "Missing dependencies. Run: pip install -r requirements.txt" >&2
  exit 1
}

python3 scripts/validate_templates.py templates "$@"
