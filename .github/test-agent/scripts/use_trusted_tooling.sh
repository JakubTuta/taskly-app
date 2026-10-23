#!/usr/bin/env bash
set -euo pipefail

checkout=".trusted-checkout"
destination="${TRUSTED:?TRUSTED must point outside the workspace}"

rm -rf "$destination"
mv "$checkout" "$destination"

rm -rf .claude .mcp.json
find . -path ./.git -prune -o -type f \( -name CLAUDE.md -o -name CLAUDE.local.md \) -print0 | xargs -0 -r rm -f
cp -R "$destination/.claude" .claude

mkdir -p .git/info
printf '%s\n' '.test-agent/' >> .git/info/exclude

echo "Agent definition, skills and settings come from the base branch; repository-provided Claude configuration was removed."
