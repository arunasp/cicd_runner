#!/usr/bin/env bash
# Packs desktop-extension/ (index.js, manifest.json, node_modules/)
# into dist/cicd-runner-<version>.mcpb via the published
# @anthropic-ai/mcpb CLI. Output filename is derived from
# manifest.json's own "version" field -- not hardcoded -- so a version
# bump there can never silently drift out of sync with what actually
# gets built (confirmed as a real gap 2026-08-08: an earlier fixed
# "cicd-runner.mcpb" name meant the file itself carried no version
# info at all, independent of whatever the manifest said).
#
# Tolerates a missing/unreachable npm registry when a local
# node_modules/ cache already exists (--prefer-offline avoids
# unnecessary network calls when the cache already satisfies the
# lockfile; if npm install still fails outright -- e.g. genuinely
# offline -- this WARNS and continues using the existing cache rather
# than hard-failing, since a previously-successful install is still a
# valid thing to pack). Only a hard requirement when there is no cache
# to fall back on at all.
set -euo pipefail

if ! command -v npm &>/dev/null; then
    echo "error: 'npm' not found -- install Node.js/npm first" >&2
    exit 1
fi
if ! command -v npx &>/dev/null; then
    echo "error: 'npx' not found -- install Node.js/npm first" >&2
    exit 1
fi
if ! command -v python3 &>/dev/null; then
    echo "error: 'python3' not found -- needed to read manifest.json's version" >&2
    exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${script_dir}"

if [[ -d node_modules ]]; then
    echo "Installing dependencies (--prefer-offline, cache already present)..." >&2
    if ! npm install --prefer-offline --no-audit --no-fund; then
        echo "warning: npm install failed (likely offline) -- continuing with the" >&2
        echo "  existing node_modules/ cache as-is. Delete node_modules/ and re-run" >&2
        echo "  if you specifically need a fresh install." >&2
    fi
else
    echo "Installing dependencies (no cache present, network required)..." >&2
    npm install --no-audit --no-fund
fi

version="$(python3 -c 'import json; print(json.load(open("manifest.json"))["version"])')"
output="dist/cicd-runner-${version}.mcpb"
mkdir -p "$(dirname "${output}")"

echo "Packing ${output}..." >&2
npx --yes @anthropic-ai/mcpb pack . "${output}"
echo "Built ${output}" >&2

# Remove any OTHER .mcpb build left in dist/ from a previous version --
# only ${output} (the one just built, matching manifest.json's current
# version) is kept. Real gap found live 2026-08-09: three superseded
# builds (1.1.0/1.2.0/1.3.0) from earlier version bumps had silently
# accumulated in dist/ with nothing to clean them up, requiring a
# manual `rm` before committing. Runs only after a successful pack
# above, so a failed build never leaves dist/ without a working .mcpb.
find dist -maxdepth 1 -name 'cicd-runner-*.mcpb' ! -name "$(basename "${output}")" -delete
