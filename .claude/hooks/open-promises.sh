#!/usr/bin/env bash
# Prints the open-promises list so a session that starts, resumes or was just compacted sees what it committed to.
root="$(cd "$(dirname "$0")/../.." && pwd)"
file="$root/docs/project/open-promises.md"
echo "Before other work: compare the conversation with this list and the roadmap. Anything decided or promised that is"
echo "missing from both is written down now (docs/project/open-promises.md, or the roadmap's checklist)."
echo
[ -f "$file" ] && cat "$file" || echo "(docs/project/open-promises.md is missing; recreate it.)"
